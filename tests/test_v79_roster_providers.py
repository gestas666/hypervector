"""Execution contracts for the V79 seven-asset roster additions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
    SOL_RANGE_SHORT_STRATEGY,
    DirectionalRangeOnsetCollector,
)
from hypervector.live.hype_compression_alignment_provider import (
    HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
    HypeCompressionAlignmentCollector,
)
from hypervector.live.hip3_fresh15_journal_provider import (
    Hip3Fresh15JournalCollector,
)
from hypervector.live.multi_asset_default_collectors import build_default_collector
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_read_only_preflight import (
    maximum_executable_margin_fraction,
)
from hypervector.live.multi_asset_polling_contract import (
    READINESS_SEED_LOOKBACK_MINUTES,
)
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.multi_asset_strategy_evidence import strategy_research_evidence
from hypervector.live.spcx_cash_session_breakout_provider import (
    SPCX_CASH_SESSION_LONG_STRATEGY,
    SpcxCashSessionBreakoutCollector,
)
from hypervector.live.zec_donchian_provider import (
    ZEC_DONCHIAN_LONG_STRATEGY,
    ZecDonchianLongCollector,
)
from hypervector.research.range_onset_observation import (
    prepare_completed_range_onset_frames,
)

_BASE = pd.Timestamp("2026-08-07T14:00:00Z")
_BASE_MS = int(_BASE.timestamp() * 1_000)
_V79 = Path("configs/multi_asset_growth_first_5000_seven_asset_all_active_v79.toml")


def test_v79_roster_order_and_execution_authority_are_exact() -> None:
    """All five crypto and two non-crypto assets must be visibly executable."""
    config = load_multi_asset_live_config(_V79, mode="observe")

    assert config.symbols == (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "ZEC",
        "xyz:SPCX",
        "xyz:SNDK",
    )
    executable = {symbol for _strategy, symbol in config.executable_provider_symbols}
    assert executable == set(config.symbols)
    assert all(
        provider.entry_sizing(symbol) is not None
        for provider in config.providers
        for symbol in provider.execution_symbols
    )
    assert maximum_executable_margin_fraction(config) == 0.24


def test_v79_new_provider_factories_use_causal_production_collectors() -> None:
    """The runtime must materialize every new identity and corrected SPCX v3."""
    config = load_multi_asset_live_config(_V79, mode="observe")
    selected = {
        provider.strategy_id: build_default_collector(
            provider,
            config,
            Path("../backtest-lab/backtest_lab"),
        )
        for provider in config.providers
        if provider.strategy_id
        in {
            ETH_RANGE_LONG_STRATEGY,
            SOL_RANGE_SHORT_STRATEGY,
            HYPE_COMPRESSION_ALIGNMENT_STRATEGY,
            ZEC_DONCHIAN_LONG_STRATEGY,
            SPCX_CASH_SESSION_LONG_STRATEGY,
        }
    }

    assert isinstance(selected[ETH_RANGE_LONG_STRATEGY], DirectionalRangeOnsetCollector)
    assert isinstance(
        selected[SOL_RANGE_SHORT_STRATEGY], DirectionalRangeOnsetCollector
    )
    hype = selected[HYPE_COMPRESSION_ALIGNMENT_STRATEGY]
    assert isinstance(hype, HypeCompressionAlignmentCollector)
    assert hype.execution_sides == frozenset({"long"})
    assert isinstance(selected[ZEC_DONCHIAN_LONG_STRATEGY], ZecDonchianLongCollector)
    spcx = selected[SPCX_CASH_SESSION_LONG_STRATEGY]
    assert isinstance(spcx, SpcxCashSessionBreakoutCollector)
    assert isinstance(spcx.source_collector, Hip3Fresh15JournalCollector)


def test_v79_spcx_execution_honors_its_cash_session_exit() -> None:
    """The provider's session boundary must have explicit close authority."""
    config = load_multi_asset_live_config(_V79, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == SPCX_CASH_SESSION_LONG_STRATEGY
    )

    assert provider.execution.provider_recipe_exit_policy == "honor"


def test_v79_hype_execution_honors_its_opposite_alignment_exit() -> None:
    """A short-only signal must be able to terminate the executable long."""
    config = load_multi_asset_live_config(_V79, mode="observe")
    provider = next(
        row
        for row in config.providers
        if row.strategy_id == HYPE_COMPRESSION_ALIGNMENT_STRATEGY
    )

    assert provider.execution.provider_recipe_exit_policy == "honor"


def test_v79_restart_exit_scans_request_each_recipe_exit_lifecycle_horizon() -> None:
    """Restart recovery must search the full possible recipe-exit lifecycle."""
    config = load_multi_asset_live_config(_V79, mode="observe")
    honored = (
        provider
        for provider in config.providers
        if provider.execution.provider_recipe_exit_policy == "honor"
    )

    for provider in honored:
        execution = provider.execution
        terminal_seconds = (
            execution.hard_maximum_hold_seconds
            if execution.maximum_hold_policy == "extend_while_regime_supported"
            else execution.maximum_hold_seconds
        )
        assert terminal_seconds is not None
        assert READINESS_SEED_LOOKBACK_MINUTES[provider.strategy_id] * 60 >= (
            terminal_seconds
        )


def test_v79_new_routes_report_exact_evidence_without_claiming_proven_edge() -> None:
    """The TUI evidence must disclose selection limits and probation status."""
    mappings = (
        (ETH_RANGE_LONG_STRATEGY, "ETH"),
        (SOL_RANGE_SHORT_STRATEGY, "SOL"),
        (ZEC_DONCHIAN_LONG_STRATEGY, "ZEC"),
        (SPCX_CASH_SESSION_LONG_STRATEGY, "xyz:SPCX"),
    )
    evidence = [strategy_research_evidence(*mapping) for mapping in mappings]

    assert all(row.research_state != "unreviewed_exact_mapping" for row in evidence)
    assert all(row.confidence in {"low", "medium"} for row in evidence)
    assert all(
        "zero exact" in row.cadence
        or "zero resolved" in row.cadence
        or "1 exact v4 live close" in row.cadence
        for row in evidence
    )
    assert "largest-winner" in evidence[2].summary
    assert evidence[3].research_state == "exact_live_n1_positive_unrepeated"
    assert "1 exact v4 live close" in evidence[3].cadence
    assert "+$5.940383 net" in evidence[3].cadence
    assert "$5.988774 gross" in evidence[3].summary
    assert "$0.057607 fees" in evidence[3].summary
    assert "+$0.009216 funding" in evidence[3].summary
    assert "one winner" in evidence[3].summary
    assert evidence[3].evidence_source.endswith(
        "v85_spcx_v4_exact_live_lifecycle_20260903_v1.json"
    )


def test_v79_btc_tuned_evidence_uses_only_exact_btc_rows() -> None:
    """The TUI must not present pooled SOL outcomes as BTC route evidence."""
    evidence = strategy_research_evidence("hulk_expansion_short_tuned_v2", "BTC")

    assert evidence.research_state == "exact_btc_partitions_mixed_live_probation"
    assert evidence.cadence == (
        "59 exact BTC historical trades / 338 covered days; 3 exact live closes"
    )
    assert "pseudo-holdout 9 trades, -$111.49, PF 0.6570" in evidence.summary
    assert "SOL rows excluded" in evidence.summary
    assert "106 completed trades" not in evidence.cadence


@pytest.mark.parametrize(
    "strategy,symbol,state,cadence_fragment,summary_fragment",
    [
        (
            "hulk_expansion_short_robust_v3",
            "BTC",
            "historical_mixed_exact_live_n2_negative",
            "2 exact live closes",
            "-$113.13",
        ),
        (
            "hulk_expansion_short_tuned_v2",
            "BTC",
            "exact_btc_partitions_mixed_live_probation",
            "3 exact live closes",
            "-$63.04",
        ),
        (
            "liquidity_sweep_long_1h_stop60_target60_v2",
            "BTC",
            "historical_candidate_current_20bp_entry_contract_unmeasured",
            "0 current 20-bps-contract closes",
            "-$8.37",
        ),
        (
            "hype_breakout_compression_alignment_bidirectional_v2",
            "HYPE",
            "development_promising_exact_live_n2_mixed",
            "2 exact live closes",
            "+$6.34",
        ),
        (
            "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3",
            "xyz:SNDK",
            "predecessor_n2_positive_exact_v3_n0",
            "zero exact v3 closes",
            "semantic predecessor",
        ),
    ],
)
def test_v79_retained_routes_disclose_latest_exact_live_sample(
    strategy: str,
    symbol: str,
    state: str,
    cadence_fragment: str,
    summary_fragment: str,
) -> None:
    """Every retained route must distinguish current and predecessor evidence."""
    evidence = strategy_research_evidence(strategy, symbol)

    assert evidence.research_state == state
    assert cadence_fragment in evidence.cadence
    assert summary_fragment in evidence.summary


def test_directional_range_admits_only_configured_side_and_maps_opposite_to_exit() -> (
    None
):
    """ETH long and SOL short authority must retain opposite-onset exits."""
    eth = DirectionalRangeOnsetCollector(
        strategy_id=ETH_RANGE_LONG_STRATEGY,
        source_collector=_range_source("ETH", "long", "short"),
    )(_minute_bars(), symbol="ETH", observed_at=_BASE, after_decision_time_ms=0)
    sol = DirectionalRangeOnsetCollector(
        strategy_id=SOL_RANGE_SHORT_STRATEGY,
        source_collector=_range_source("SOL", "short", "long"),
    )(_minute_bars(), symbol="SOL", observed_at=_BASE, after_decision_time_ms=0)

    assert [(row.strategy_id, row.side) for row in eth.intents] == [
        (ETH_RANGE_LONG_STRATEGY, "long")
    ]
    assert eth.evaluations[1].exit_sides == frozenset({"long"})
    assert eth.evaluations[1].decision_action == "close_long"
    assert [(row.strategy_id, row.side) for row in sol.intents] == [
        (SOL_RANGE_SHORT_STRATEGY, "short")
    ]
    assert sol.evaluations[1].exit_sides == frozenset({"short"})


def test_v79_hype_short_alignment_closes_long_without_opening_short() -> None:
    """The disabled HYPE side must retain opposite-signal exit authority."""
    collector = HypeCompressionAlignmentCollector(
        canonical_collector=_hype_aligned_source("short"),
        execution_enabled=True,
        execution_sides=frozenset({"long"}),
    )

    result = collector(
        _minute_bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1),
        after_decision_time_ms=_BASE_MS - 60_000,
    )

    assert result.intents == ()
    assert result.evaluations[0].eligible is False
    assert result.evaluations[0].decision_action == "close_long"
    assert result.evaluations[0].exit_sides == frozenset({"long"})
    assert result.evaluations[0].exit_reason == "opposite_hype_alignment"


def test_zec_donchian_emits_long_entry_stop_and_long_channel_exit() -> None:
    """The ZEC route must expose its structural stop and recipe exit."""
    collector = ZecDonchianLongCollector(signal_builder=_zec_signals)
    result = collector(
        _quarter_hour_bars(),
        symbol="ZEC",
        observed_at=pd.Timestamp("2026-08-07T15:00:01Z"),
        after_decision_time_ms=_BASE_MS,
    )

    assert [(row.strategy_id, row.side) for row in result.intents] == [
        (ZEC_DONCHIAN_LONG_STRATEGY, "long")
    ]
    assert result.intents[0].stop_anchor == 96.0
    assert result.evaluations[-2].exit_sides == frozenset({"long"})
    assert result.evaluations[-2].decision_action == "close_long"


def test_zec_readiness_retains_last_completed_four_hour_state() -> None:
    """Later 15m rows must show ready state without inventing another entry."""
    bars = _zec_ready_quarter_hour_bars()
    last_signal_row = pd.Timestamp(bars["timestamp"].iloc[-5])
    boundary_ms = int((last_signal_row + pd.Timedelta(minutes=15)).timestamp() * 1_000)

    result = ZecDonchianLongCollector()(
        bars,
        symbol="ZEC",
        observed_at=(
            pd.Timestamp(bars["timestamp"].iloc[-1])
            + pd.Timedelta(minutes=15, seconds=1)
        ),
        after_decision_time_ms=boundary_ms,
    )

    latest = result.evaluations[-1]
    assert result.intents == ()
    assert latest.decision_action == "hold"
    assert latest.reason == "entry_condition_absent"
    assert latest.readiness.conditions_met == 2
    assert latest.readiness.metrics["prior_entry_high"] is not None
    assert latest.readiness.metrics["atr"] is not None
    assert "donchian_history_unready" not in latest.readiness.blockers
    assert "atr_unready" not in latest.readiness.blockers


def test_zec_readiness_does_not_bridge_a_missing_quarter_hour_bar() -> None:
    """A source gap must reset prior Donchian/ATR readiness telemetry."""
    bars = _zec_ready_quarter_hour_bars()
    last_signal_row = pd.Timestamp(bars["timestamp"].iloc[-5])
    bars = bars.drop(index=bars.index[-4]).reset_index(drop=True)
    boundary_ms = int((last_signal_row + pd.Timedelta(minutes=15)).timestamp() * 1_000)

    result = ZecDonchianLongCollector()(
        bars,
        symbol="ZEC",
        observed_at=(
            pd.Timestamp(bars["timestamp"].iloc[-1])
            + pd.Timedelta(minutes=15, seconds=1)
        ),
        after_decision_time_ms=boundary_ms,
    )

    latest = result.evaluations[-1]
    assert result.intents == ()
    assert latest.reason == "indicator_history_unready"
    assert latest.readiness.conditions_met == 0
    assert "donchian_history_unready" in latest.readiness.blockers
    assert "atr_unready" in latest.readiness.blockers


def test_spcx_requires_long_breakout_inside_regular_cash_session() -> None:
    """SPCX may execute long only on weekdays from 09:30 through 15:59 ET."""
    source = _spcx_source()
    collector = SpcxCashSessionBreakoutCollector(source_collector=source)
    cash = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T14:31:00Z"),
        after_decision_time_ms=0,
    )
    overnight = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T01:01:00Z"),
        after_decision_time_ms=0,
    )

    assert [(row.strategy_id, row.side) for row in cash.intents] == [
        (SPCX_CASH_SESSION_LONG_STRATEGY, "long")
    ]
    assert overnight.intents == ()
    assert overnight.evaluations[0].reason == "outside_us_regular_cash_session"


def test_spcx_does_not_duplicate_an_existing_source_blocker() -> None:
    """The cash-session wrapper must preserve a canonical blocker set."""
    reason = "fresh_breakout_onset_absent"
    source_row = ProviderEvaluation(
        strategy_id="source",
        symbol="xyz:SPCX",
        decision_time_ms=int(pd.Timestamp("2026-08-07T14:15:00Z").timestamp() * 1_000),
        reference_price=100.0,
        decision_action="hold",
        eligible=False,
        reason=reason,
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=0,
            conditions_required=1,
            blockers=(reason,),
            indicators=("FRESH BREAKOUT NO",),
        ),
    )

    def source(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del symbol, observed_at, after_decision_time_ms
        return IntentBatch((), source_row.decision_time_ms, (source_row,))

    result = SpcxCashSessionBreakoutCollector(source_collector=source)(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T14:16:00Z"),
        after_decision_time_ms=0,
    )

    assert result.evaluations[0].readiness.blockers == (reason,)


def test_spcx_short_signal_cannot_gain_execution_authority() -> None:
    """A source short remains diagnostic under the V79 long-only contract."""
    collector = SpcxCashSessionBreakoutCollector(
        source_collector=_spcx_source(side="short")
    )
    result = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T14:31:00Z"),
        after_decision_time_ms=0,
    )

    assert result.intents == ()
    assert result.evaluations[0].reason == "spcx_long_only"


def test_spcx_regular_session_close_emits_a_long_recipe_exit() -> None:
    """The completed closing bar must terminate any surviving SPCX long."""
    collector = SpcxCashSessionBreakoutCollector(source_collector=_spcx_source())

    result = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T20:00:01Z"),
        after_decision_time_ms=0,
    )

    assert result.intents == ()
    assert result.evaluations[0].decision_action == "close_long"
    assert result.evaluations[0].exit_sides == frozenset({"long"})
    assert result.evaluations[0].exit_reason == "spcx_cash_session_close"


def test_spcx_rejects_a_preopen_bar_decision_at_0930_new_york() -> None:
    """A 09:30 boundary contains no completed regular-session price bar."""
    collector = SpcxCashSessionBreakoutCollector(source_collector=_spcx_source())

    result = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T13:30:01Z"),
        after_decision_time_ms=0,
    )

    assert result.intents == ()
    assert result.evaluations[0].reason == "cash_session_bar_incomplete"


def test_spcx_rejects_entries_on_a_declared_market_holiday() -> None:
    """A weekday is not sufficient evidence that the cash session exists."""
    collector = SpcxCashSessionBreakoutCollector(source_collector=_spcx_source())

    result = collector(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-09-07T14:00:01Z"),
        after_decision_time_ms=0,
    )

    assert result.intents == ()
    assert result.evaluations[0].exit_sides == frozenset({"long"})
    assert result.evaluations[0].exit_reason == "spcx_cash_session_closed"


def test_spcx_serializes_a_missed_close_before_a_restart_reentry() -> None:
    """A missed close and later entry must not share execution authority."""
    close_ms = int(pd.Timestamp("2026-08-07T20:00:00Z").timestamp() * 1_000)
    resumed_ms = int(pd.Timestamp("2026-08-10T14:00:00Z").timestamp() * 1_000)

    def source(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del observed_at, after_decision_time_ms
        rows = (
            _evaluation(symbol, "long", close_ms),
            _evaluation(symbol, "long", resumed_ms),
        )
        return IntentBatch((), resumed_ms, rows)

    result = SpcxCashSessionBreakoutCollector(source_collector=source)(
        _quarter_hour_bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-10T14:00:01Z"),
        after_decision_time_ms=close_ms - 900_000,
    )

    assert result.intents == ()
    assert result.evaluations[-1].eligible is False
    assert result.evaluations[-1].decision_action == "close_long"
    assert result.evaluations[-1].exit_sides == frozenset({"long"})
    assert result.evaluations[-1].exit_reason == "spcx_cash_session_close_recovery"


def test_range_source_uses_only_latest_complete_segment_after_archive_gap() -> None:
    """Historical holes must be crossed by reset, never by fabricated candles."""
    bars = _bars(pd.date_range(_BASE, periods=1_000, freq="1min")).drop(index=99)

    complete, signals, regimes = prepare_completed_range_onset_frames(
        bars,
        observed_at=_BASE + pd.Timedelta(minutes=1_001),
        signal_builder=lambda frame: frame.copy(),
        regime_builder=lambda frame: frame.copy(),
    )

    expected_start = _BASE + pd.Timedelta(minutes=100)
    assert complete.index[0] == expected_start
    assert signals.index.equals(complete.index)
    assert regimes.index.equals(complete.index)


def _range_source(
    symbol: str,
    entry_side: str,
    opposite_side: str,
) -> Callable[..., IntentBatch]:
    evaluations = (
        _evaluation(symbol, entry_side, _BASE_MS + 60_000),
        _evaluation(symbol, opposite_side, _BASE_MS + 120_000),
    )

    def collect(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del observed_at, after_decision_time_ms
        return IntentBatch((), evaluations[-1].decision_time_ms, evaluations)

    return collect


def _spcx_source(side: str = "long") -> Callable[..., IntentBatch]:
    def collect(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del after_decision_time_ms
        decision_ms = int(observed_at.timestamp() * 1_000) - 1_000
        row = _evaluation(symbol, side, decision_ms)
        return IntentBatch((), decision_ms, (row,))

    return collect


def _hype_aligned_source(side: str) -> Callable[..., IntentBatch]:
    def collect(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del observed_at, after_decision_time_ms
        readiness = SignalReadiness(
            side=side,
            conditions_met=4,
            conditions_required=4,
            blockers=(),
            indicators=("SOURCE READY",),
            metrics={
                "authoritative_5m_bbwp_percentile": 20.0,
                "prior_bbwp_min_15m": 20.0,
                "directional_bar_body_bps": -1.0,
                "breakout_side_relation": "aligned",
            },
        )
        evaluation = ProviderEvaluation(
            strategy_id="source",
            symbol=symbol,
            decision_time_ms=_BASE_MS,
            reference_price=100.0,
            decision_action=f"enter_{side}",
            eligible=True,
            reason="entry_signal_present",
            side=side,
            readiness=readiness,
            trigger="source_entry",
        )
        intent = StrategyIntent(
            "source",
            symbol,
            side,
            _BASE_MS,
            100.0,
            "source_entry",
        )
        return IntentBatch((intent,), _BASE_MS, (evaluation,))

    return collect


def _evaluation(symbol: str, side: str, decision_ms: int) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id="source",
        symbol=symbol,
        decision_time_ms=decision_ms,
        reference_price=100.0,
        decision_action=f"enter_{side}",
        eligible=True,
        reason="entry_signal_present",
        side=side,
        readiness=SignalReadiness(
            side=side,
            conditions_met=2,
            conditions_required=2,
            blockers=(),
            indicators=("SOURCE READY",),
        ),
        trigger="source_entry",
    )


def _zec_signals(
    bars: pd.DataFrame,
    _config: object,
) -> pd.DataFrame:
    output = pd.DataFrame(index=bars.index)
    output["long_entry"] = False
    output.loc[output.index[-1], "long_entry"] = True
    output["short_entry"] = False
    output["long_exit"] = False
    output.loc[output.index[-2], "long_exit"] = True
    output["short_exit"] = False
    output["prior_entry_high"] = 103.0
    output["prior_entry_low"] = 97.0
    output["prior_exit_high"] = 102.0
    output["prior_exit_low"] = 98.0
    output["atr"] = 2.0
    output["stop_price"] = float("nan")
    output.loc[output.index[-1], "stop_price"] = 96.0
    return output


def _quarter_hour_bars() -> pd.DataFrame:
    timestamps = pd.date_range(_BASE, periods=4, freq="15min")
    return _bars(timestamps)


def _zec_ready_quarter_hour_bars() -> pd.DataFrame:
    completed_four_hour_bars = 21
    trailing_quarter_hour_bars = 4
    periods = completed_four_hour_bars * 16 + trailing_quarter_hour_bars
    timestamps = pd.date_range("2026-01-01", periods=periods, freq="15min", tz="UTC")
    return _bars(timestamps)


def _minute_bars() -> pd.DataFrame:
    return _bars(pd.date_range(_BASE, periods=3, freq="1min"))


def _bars(timestamps: pd.DatetimeIndex) -> pd.DataFrame:
    closes = [100.0 + position for position in range(len(timestamps))]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0] * len(timestamps),
        }
    )
