from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_archive_sidecars import (
    build_archive_source_frame,
    build_archive_trade_frame,
)
from hypervector.research.mu_hip3_archive_candidate import (
    MuArchiveExecution,
    MuArchiveFamilyResult,
    MuArchiveTrial,
    _breakout_builder,
    canonical_mu_archive_windows,
    evaluate_hip3_archive_candidates,
    evaluate_mu_archive_candidates,
    evaluate_mu_archive_track_partition,
    mu_archive_portfolio_config,
    select_mu_archive_trial,
    select_mu_development_track,
)
from hypervector.research.mu_hip3_archive_reporting import (
    family_assessment,
    final_track_evaluation,
    partition_trade_path_quality,
    track_identity,
    trade_path_quality,
    validation_assessment,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig


def _bars(count: int = 800, *, timeframe: str = "15min") -> pd.DataFrame:
    index = pd.date_range("2026-02-26T18:00:00Z", periods=count, freq=timeframe)
    cycle = np.array([0.8] * 20 + [-0.9] * 30 + [0.9] * 30 + [-0.8] * 20)
    close = 100.0 + np.cumsum(np.resize(cycle, count))
    open_price = np.roll(close, 1)
    open_price[0] = close[0]
    direction = np.sign(pd.Series(close).diff().fillna(0.0)).to_numpy()
    spread = 0.0006
    bars = pd.DataFrame(
        {
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.05,
            "low": np.minimum(open_price, close) - 0.05,
            "close": close,
            "entry_bid": open_price * (1.0 - spread / 2.0),
            "entry_ask": open_price * (1.0 + spread / 2.0),
            "decision_bid": close * (1.0 - spread / 2.0),
            "decision_ask": close * (1.0 + spread / 2.0),
            "decision_imbalance_10": direction * 0.6,
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 500,
            "source_snapshot_count": 100,
            "gap_before_bars": 0,
            "funding_rate": 0.0,
        },
        index=index,
    )
    for name in ("open", "high", "low", "close"):
        bars[f"signal_{name}"] = bars[name]
    bars["signal_gap_before_bars"] = bars["gap_before_bars"]
    bars["signal_ohlc_source"] = "0xarchive_public_trade_ohlc_v1"
    bars["signal_ohlc_synthetic_no_trade"] = False
    return bars


def _execution() -> MuArchiveExecution:
    return MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=75.0,
        venue_max_leverage=10.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=1.5,
    )


def test_archive_breakout_suppresses_stale_preclose_pressure_only() -> None:
    """Archive pressure staleness is an adapter rule, not a live-provider rule."""
    bars = _bars(5)
    closes = [100.0, 100.0, 100.0, 101.0, 102.0]
    for column, values in {
        "signal_open": closes,
        "signal_high": [value + 0.1 for value in closes],
        "signal_low": [value - 0.1 for value in closes],
        "signal_close": closes,
    }.items():
        bars[column] = values
    bars["decision_imbalance_10"] = [0.0, 0.0, 0.0, 0.6, 0.7]
    bars.loc[bars.index[3], "end_boundary_age_ms"] = 20_000

    signals = _breakout_builder(
        bars,
        Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        "15m",
    )

    assert not signals["long_entry"].iloc[3]
    assert signals["long_entry"].iloc[4]


def _trade(direction: str, pnl: float) -> SharedPortfolioTrade:
    return SharedPortfolioTrade(
        "test",
        direction,
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:15:00+00:00",
        "2026-01-01T00:30:00+00:00",
        0,
        1,
        2,
        100.0,
        101.0,
        None,
        None,
        80.0,
        1.0,
        15.0,
        75.0,
        5.0,
        pnl,
        0.0,
        0.0,
        pnl,
        500.0,
        500.0 + pnl,
        "signal",
        False,
    )  # type: ignore[arg-type]


def _report(
    net: float, trades: tuple[SharedPortfolioTrade, ...]
) -> SharedPortfolioReport:
    gains = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    return SharedPortfolioReport(
        500.0,
        500.0 + net,
        net,
        net / 5.0,
        min(net / 5.0, 0.0),
        len(trades),
        sum(trade.net_pnl_usd > 0.0 for trade in trades),
        sum(trade.net_pnl_usd < 0.0 for trade in trades),
        gains,
        losses,
        gains / losses if losses else None,
        0,
        0.0,
        0.0,
        0,
        1,
        0,
        0,
        False,
        {},
        (),
        trades,
    )


def test_archive_candidate_evaluates_two_bidirectional_families() -> None:
    result = evaluate_mu_archive_candidates(
        _bars(),
        _execution(),
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert result.symbol == "xyz:MU"
    assert result.execution_authority == "none"
    assert result.automatic_promotion is False
    assert {family.family for family in result.families} == {
        "swing_ha",
        "breakout_pressure",
    }
    for family in result.families:
        assert [partition.name for partition in family.partitions] == ["development"]
        assert family.proposed_provider_id.startswith("hip3_mu_full_l2_")


def test_exact_cl_candidate_has_distinct_symbol_and_provider_identity() -> None:
    execution = replace(_execution(), symbol="xyz:CL", venue_max_leverage=20.0)

    result = evaluate_hip3_archive_candidates(
        _bars(),
        execution,
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert result.symbol == "xyz:CL"
    assert all(
        family.proposed_provider_id.startswith("hip3_cl_full_l2_")
        for family in result.families
    )
    for family in result.families:
        config = mu_archive_portfolio_config(
            execution, family=family.family, stress=False
        )
        assert config.symbol == "xyz:CL"

    trades = build_archive_trade_frame((result,))
    sources = build_archive_source_frame(
        {"15m": _bars(4)}, pd.DataFrame({"funding_rate": [0.0]}), "xyz:CL"
    )
    assert not trades.empty
    assert set(trades["symbol"]) == {"xyz:CL"}
    assert set(sources["symbol"]) == {"xyz:CL"}
    assert track_identity(select_mu_development_track((result,)))["symbol"] == "xyz:CL"


def test_archive_candidate_rejects_midpoint_only_signal_source() -> None:
    bars = _bars().drop(
        columns=[
            "signal_open",
            "signal_high",
            "signal_low",
            "signal_close",
            "signal_gap_before_bars",
            "signal_ohlc_source",
            "signal_ohlc_synthetic_no_trade",
        ]
    )

    with pytest.raises(ValueError, match="trade OHLC source"):
        evaluate_mu_archive_candidates(
            bars,
            _execution(),
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )


def test_archive_candidate_stress_cost_is_not_better_than_nominal() -> None:
    result = evaluate_mu_archive_candidates(
        _bars(),
        _execution(),
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    for family in result.families:
        for partition in family.partitions:
            assert partition.stress.net_pnl_usd <= partition.nominal.net_pnl_usd


def test_default_archive_evaluation_does_not_open_oos_partitions() -> None:
    result = evaluate_mu_archive_candidates(
        _bars(),
        _execution(),
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert all(
        [partition.name for partition in family.partitions] == ["development"]
        for family in result.families
    )


def test_archive_execution_models_live_80bps_stop_and_24h_ceiling() -> None:
    config = mu_archive_portfolio_config(_execution(), family="swing_ha", stress=False)

    assert config.stop_margin_pct == 4.0
    assert config.maximum_stop_distance_bps == 80.0
    assert config.max_hold_bars == 96
    assert config.max_hold_seconds == 86_400


def test_five_minute_challenger_has_distinct_identity_and_24h_ceiling() -> None:
    execution = MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=75.0,
        venue_max_leverage=10.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=1.5,
        maximum_hold_bars=288,
    )

    result = evaluate_mu_archive_candidates(
        _bars(timeframe="5min"),
        execution,
        timeframe="5m",
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    assert result.timeframe == "5m"
    assert all("_5m_" in family.proposed_provider_id for family in result.families)
    signal_names = {
        trade.signal_name
        for family in result.families
        for partition in family.partitions
        for trade in partition.nominal.trades
    }
    assert signal_names
    assert all(name.endswith("@5m") for name in signal_names)
    assert (
        mu_archive_portfolio_config(
            execution, family="swing_ha", stress=False
        ).max_hold_bars
        == 288
    )


def test_five_minute_challenger_rejects_fifteen_minute_cadence() -> None:
    execution = replace(_execution(), maximum_hold_bars=288)

    with pytest.raises(ValueError, match="5m cadence"):
        evaluate_mu_archive_candidates(
            _bars(),
            execution,
            timeframe="5m",
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("first_boundary_delay_ms", -1.0, "first_boundary_delay_ms"),
        ("first_boundary_delay_ms", 900_000.0, "first_boundary_delay_ms"),
        ("end_boundary_age_ms", float("nan"), "end_boundary_age_ms"),
        ("maximum_snapshot_interval_ms", -1.0, "maximum_snapshot_interval_ms"),
    ],
)
def test_archive_candidate_rejects_malformed_quote_timing(
    column: str, value: float, message: str
) -> None:
    bars = _bars()
    bars["first_boundary_delay_ms"] = 100.0
    bars["end_boundary_age_ms"] = 100.0
    bars.loc[bars.index[10], column] = value

    with pytest.raises(ValueError, match=message):
        evaluate_mu_archive_candidates(
            bars,
            _execution(),
            swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
            breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
        )


def test_archive_candidate_retains_long_and_short_diagnostics() -> None:
    result = evaluate_mu_archive_candidates(
        _bars(),
        _execution(),
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )

    directions = {
        trade.direction
        for family in result.families
        for partition in family.partitions
        for trade in partition.nominal.trades
    }

    assert directions == {"long", "short"}


def test_profitable_stable_one_side_trial_outranks_losing_bidirectional_trial() -> None:
    stable = SwingHaSignalConfig(7, 21, 3, "state", "ha_flip")
    losing = SwingHaSignalConfig(9, 26, 5, "onset", "alignment_loss")
    stable_trial = MuArchiveTrial(
        stable,
        _report(6.0, (_trade("long", 6.0),)),
        (_report(1.0, ()), _report(1.0, ()), _report(1.0, ())),
    )
    losing_both_trial = MuArchiveTrial(
        losing,
        _report(-2.0, (_trade("long", -1.0), _trade("short", -1.0))),
        (_report(-1.0, ()), _report(-1.0, ()), _report(-1.0, ())),
    )

    selected = select_mu_archive_trial((stable_trial, losing_both_trial))

    assert selected.config == stable


def test_family_assessment_counts_stress_liquidations() -> None:
    config = SwingHaSignalConfig(7, 21, 3, "state", "ha_flip")
    trades = (_trade("long", 2.0), _trade("short", 2.0))
    nominal = _report(4.0, trades)
    stress_with_liquidation = replace(nominal, liquidations=1)
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-02T00:00:00Z")
    family = MuArchiveFamilyResult(
        "swing_ha",
        "hip3_mu_swing_ha_bidirectional_v1",
        "mu_swing_ha_bidirectional_research_v1",
        (),
        config,
        (
            MuPartitionResult("development", start, end, nominal, nominal),
            MuPartitionResult(
                "validation", start, end, nominal, stress_with_liquidation
            ),
            MuPartitionResult("holdout", start, end, nominal, nominal),
        ),
    )

    checks = family_assessment(family)["checks"]

    assert checks["no_validation_or_holdout_liquidations"] is False


def test_family_breadth_can_span_validation_and_holdout() -> None:
    config = SwingHaSignalConfig(7, 21, 3, "state", "ha_flip")
    long_report = _report(2.0, (_trade("long", 2.0),))
    short_report = _report(2.0, (_trade("short", 2.0),))
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-02T00:00:00Z")
    family = MuArchiveFamilyResult(
        "swing_ha",
        "hip3_mu_swing_ha_bidirectional_v1",
        "mu_swing_ha_bidirectional_research_v1",
        (),
        config,
        (
            MuPartitionResult("development", start, end, long_report, long_report),
            MuPartitionResult("validation", start, end, long_report, long_report),
            MuPartitionResult("holdout", start, end, short_report, short_report),
        ),
    )

    assessment = family_assessment(family)

    assert assessment["checks"]["combined_out_of_sample_observed_both_sides"] is True
    assert set(assessment["side_assessments"]) == {"long", "short"}
    assert assessment["authoritative"] is False
    assert assessment["supportive"] is False


def test_path_evidence_is_mandatory_for_out_of_sample_decisions() -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-02T00:00:00Z")
    positive = _report(4.0, (_trade("long", 2.0), _trade("short", 2.0)))
    validation = MuPartitionResult("validation", start, end, positive, positive)
    holdout = MuPartitionResult("holdout", start, end, positive, positive)

    with pytest.raises(TypeError):
        validation_assessment(validation)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        final_track_evaluation(validation, holdout)


def test_mu_mark_risk_path_can_liquidate_when_midpoint_ohlc_looks_safe() -> None:
    bars = _bars(count=4)
    bars.loc[:, ["open", "high", "low", "close"]] = [100.0, 100.1, 99.9, 100.0]
    bars.loc[:, ["entry_bid", "entry_ask", "decision_bid", "decision_ask"]] = [
        99.99,
        100.01,
        99.99,
        100.01,
    ]
    bars["risk_high"] = 100.1
    bars["risk_low"] = [99.9, 1.0, 99.9, 99.9]
    signals = pd.DataFrame(
        {
            "entry_direction": ["long", None, None, None],
            "exit_signal": False,
            "signal_name": "mu_mark_path_test",
        },
        index=bars.index,
    )
    execution = replace(
        _execution(),
        risk_high_column="risk_high",
        risk_low_column="risk_low",
    )

    report = evaluate_shared_bar_portfolio(
        bars,
        signals,
        mu_archive_portfolio_config(execution, family="swing_ha", stress=False),
    )

    assert report.liquidations == 1
    assert report.trades[0].exit_reason == "liquidation"


def test_holdout_changes_cannot_change_selected_family_identities() -> None:
    baseline = _bars()
    altered = baseline.copy()
    holdout = altered.index[int(len(altered) * 0.80) :]
    price_columns = (
        "open",
        "high",
        "low",
        "close",
        "entry_bid",
        "entry_ask",
        "decision_bid",
        "decision_ask",
    )
    altered.loc[holdout, list(price_columns)] *= 1.75
    swing = (
        SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),
        SwingHaSignalConfig(9, 26, 5, "onset", "alignment_loss"),
    )
    breakout = (
        Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),
        Hip3BreakoutPressureConfig(16, 9, 21, 0.35, 120.0),
    )

    first = evaluate_mu_archive_candidates(
        baseline,
        _execution(),
        swing_configs=swing,
        breakout_configs=breakout,
    )
    second = evaluate_mu_archive_candidates(
        altered,
        _execution(),
        swing_configs=swing,
        breakout_configs=breakout,
    )

    first_identities = tuple(
        (family.proposed_provider_id, family.selected_config)
        for family in first.families
    )
    second_identities = tuple(
        (family.proposed_provider_id, family.selected_config)
        for family in second.families
    )
    assert second_identities == first_identities


def test_development_selects_one_track_before_validation_or_holdout() -> None:
    bars_15m = _bars()
    bars_5m = _bars(count=2_400, timeframe="5min")
    configs = (SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),)
    breakouts = (Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),)
    results = (
        evaluate_mu_archive_candidates(
            bars_15m,
            _execution(),
            partition_names=("development",),
            swing_configs=configs,
            breakout_configs=breakouts,
        ),
        evaluate_mu_archive_candidates(
            bars_5m,
            replace(_execution(), maximum_hold_bars=288),
            timeframe="5m",
            partition_names=("development",),
            swing_configs=configs,
            breakout_configs=breakouts,
        ),
    )

    selected = select_mu_development_track(results)

    assert selected.timeframe in {"5m", "15m"}
    assert selected.family in {"swing_ha", "breakout_pressure"}
    assert (
        sum(
            family.proposed_provider_id == selected.provider_id
            for result in results
            for family in result.families
        )
        == 1
    )
    assert all(
        [partition.name for partition in family.partitions] == ["development"]
        for result in results
        for family in result.families
    )


def test_validation_partition_does_not_read_holdout_rows() -> None:
    baseline = _bars()
    result = evaluate_mu_archive_candidates(
        baseline,
        _execution(),
        partition_names=("development",),
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )
    selected = select_mu_development_track((result,))
    altered = baseline.copy()
    altered.loc[
        altered.index >= result.windows.validation_end_utc,
        ["open", "high", "low", "close"],
    ] *= 10.0

    first = evaluate_mu_archive_track_partition(
        baseline, _execution(), result.windows, selected, "validation"
    )
    second = evaluate_mu_archive_track_partition(
        altered, _execution(), result.windows, selected, "validation"
    )

    assert second == first


def test_cross_timeframe_selection_uses_identical_wall_clock_windows_with_gaps() -> (
    None
):
    bars_15m = _bars()
    bars_5m = _bars(count=2_400, timeframe="5min").drop(
        _bars(count=2_400, timeframe="5min").index[500:506]
    )
    elapsed = bars_5m.index.to_series().diff().dt.total_seconds().div(300).sub(1)
    bars_5m["gap_before_bars"] = elapsed.fillna(0).round().astype(int)
    windows = canonical_mu_archive_windows(
        bars_15m.index[0], bars_15m.index[-1] + pd.Timedelta(minutes=15)
    )
    configs = (SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),)
    breakouts = (Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),)

    results = (
        evaluate_mu_archive_candidates(
            bars_15m,
            _execution(),
            windows=windows,
            swing_configs=configs,
            breakout_configs=breakouts,
        ),
        evaluate_mu_archive_candidates(
            bars_5m,
            replace(_execution(), maximum_hold_bars=288),
            timeframe="5m",
            windows=windows,
            swing_configs=configs,
            breakout_configs=breakouts,
        ),
    )

    select_mu_development_track(results)
    assert results[0].windows == results[1].windows == windows


def test_frozen_five_minute_partition_rejects_window_beyond_available_bars() -> None:
    bars = _bars(count=800, timeframe="5min")
    execution = replace(_execution(), maximum_hold_bars=288)
    result = evaluate_mu_archive_candidates(
        bars,
        execution,
        timeframe="5m",
        swing_configs=(SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
        breakout_configs=(Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),),
    )
    selected = select_mu_development_track((result,))
    invalid = replace(
        result.windows,
        holdout_end_utc=bars.index[-1] + pd.Timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="exceed available"):
        evaluate_mu_archive_track_partition(
            bars, execution, invalid, selected, "holdout"
        )


def test_naked_risk_path_boolean_cannot_resolve_l2_outage() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 899_000,
            "source_snapshot_count": 2,
            "risk_path_resolved": True,
        },
        index=index,
    )

    quality = trade_path_quality(
        bars,
        _report(2.0, (_trade("long", 2.0),)),
        timeframe="15m",
        family="swing_ha",
    )

    assert quality["status"] == "unresolved"


@pytest.mark.parametrize(
    ("mark_complete", "trade_complete", "maximum_interval"),
    [
        ("false", "false", -1.0),
        (True, True, -1.0),
        (True, True, float("nan")),
        (True, True, float("inf")),
    ],
)
def test_risk_path_resolution_rejects_untyped_or_invalid_evidence(
    mark_complete: object,
    trade_complete: object,
    maximum_interval: float,
) -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 899_000,
            "source_snapshot_count": 2,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": mark_complete,
            "maximum_mark_interval_ms": maximum_interval,
            "trade_bundle_complete": trade_complete,
        },
        index=index,
    )

    quality = trade_path_quality(
        bars,
        _report(2.0, (_trade("long", 2.0),)),
        timeframe="15m",
        family="swing_ha",
    )

    assert quality["status"] == "unresolved"


def test_path_quality_unions_nominal_and_stress_lifecycles() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": [100, 899_000, 100, 100],
            "source_snapshot_count": 2,
        },
        index=index,
    )
    partition = MuPartitionResult(
        "validation",
        index[0],
        index[-1] + pd.Timedelta(minutes=15),
        _report(2.0, (_trade("long", 2.0),)),
        _report(0.0, ()),
    )

    quality = partition_trade_path_quality(
        bars, partition, timeframe="15m", family="swing_ha"
    )

    assert quality["nominal"]["status"] == "unresolved"
    assert quality["stress"]["status"] == "resolved"
    assert quality["status"] == "unresolved"


def test_trade_path_requires_verified_mark_and_tape_even_when_l2_is_dense() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 100,
            "source_snapshot_count": 100,
        },
        index=index,
    )

    quality = trade_path_quality(
        bars,
        _report(2.0, (_trade("long", 2.0),)),
        timeframe="15m",
        family="swing_ha",
    )

    assert quality["status"] == "unresolved"


def test_trade_path_rejects_unresolved_post_entry_mark_slice() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 100,
            "source_snapshot_count": 100,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100,
            "trade_bundle_complete": True,
            "entry_mark_path_complete": False,
            "entry_maximum_mark_interval_ms": float("inf"),
        },
        index=index,
    )

    quality = trade_path_quality(
        bars,
        _report(2.0, (_trade("long", 2.0),)),
        timeframe="15m",
        family="swing_ha",
    )

    assert quality["status"] == "unresolved"
    assert quality["unresolved_entry_bar_risk_trades"] == 1


def test_breakout_path_rejects_stale_l2_pressure_despite_complete_mark_tape() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": 100,
            "end_boundary_age_ms": [299_000, 100, 100, 100],
            "maximum_snapshot_interval_ms": 100,
            "source_snapshot_count": 100,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100,
            "trade_bundle_complete": True,
        },
        index=index,
    )

    quality = trade_path_quality(
        bars,
        _report(2.0, (_trade("long", 2.0),)),
        timeframe="15m",
        family="breakout_pressure",
    )

    assert quality["status"] == "unresolved"
    assert quality["stale_l2_decision_trades"] == 1


def test_signal_exit_path_rejects_stale_executable_open_quote() -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=4, freq="15min")
    bars = pd.DataFrame(
        {
            "first_boundary_delay_ms": [100, 100, 899_000, 100],
            "end_boundary_age_ms": 100,
            "maximum_snapshot_interval_ms": 100,
            "source_snapshot_count": 100,
            "risk_path_source": "0xarchive_mark_price_with_public_trade_context_v1",
            "mark_path_complete": True,
            "maximum_mark_interval_ms": 100,
            "trade_bundle_complete": True,
        },
        index=index,
    )
    trade = replace(_trade("long", 2.0), exit_reason="signal")

    quality = trade_path_quality(
        bars,
        _report(2.0, (trade,)),
        timeframe="15m",
        family="swing_ha",
    )

    assert quality["status"] == "unresolved"
    assert quality["stale_l2_exit_trades"] == 1


def test_midpoint_ohlc_cannot_change_candidates_when_trade_ohlc_is_frozen() -> None:
    baseline = _bars()
    for name in ("open", "high", "low", "close"):
        baseline[f"signal_{name}"] = baseline[name]
    baseline["signal_gap_before_bars"] = baseline["gap_before_bars"]
    baseline["signal_ohlc_source"] = "0xarchive_public_trade_ohlc_v1"
    baseline["signal_ohlc_synthetic_no_trade"] = False
    baseline["risk_high"] = baseline["high"]
    baseline["risk_low"] = baseline["low"]
    altered = baseline.copy()
    altered["open"] = 300.0 - baseline["open"]
    altered["close"] = 300.0 - baseline["close"]
    altered["high"] = altered[["open", "close"]].max(axis=1) + 0.05
    altered["low"] = altered[["open", "close"]].min(axis=1) - 0.05
    swing = (SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),)
    breakout = (Hip3BreakoutPressureConfig(4, 3, 8, 0.2, 80.0),)
    execution = replace(
        _execution(),
        risk_high_column="risk_high",
        risk_low_column="risk_low",
    )

    original = evaluate_mu_archive_candidates(
        baseline,
        execution,
        swing_configs=swing,
        breakout_configs=breakout,
    )
    mutated = evaluate_mu_archive_candidates(
        altered,
        execution,
        swing_configs=swing,
        breakout_configs=breakout,
    )

    for original_family, mutated_family in zip(
        original.families, mutated.families, strict=True
    ):
        assert original_family.selected_config == mutated_family.selected_config
        assert original_family.trials[0].development == (
            mutated_family.trials[0].development
        )
