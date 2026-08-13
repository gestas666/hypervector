"""Tests for the predeclared shared-portfolio screening script."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pandas as pd
import pytest

from hypervector.research.shared_portfolio_models import SharedPortfolioTrade

SCRIPT = Path(__file__).parents[1] / "scripts" / "shared_strategy_screen.py"
SPEC = spec_from_file_location("shared_strategy_screen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_screen_cohorts_are_small_predeclared_and_not_a_hidden_grid() -> None:
    assert len(MODULE.LEGACY_CANDIDATES) == 5
    assert len(MODULE.SOURCE_CANDIDATES) == 5
    assert len(MODULE.SOURCE_MANAGED_V1_CANDIDATES) == 3
    assert len(MODULE.PROFILES) == 4
    assert len(MODULE.LEGACY_CANDIDATES) * len(MODULE.PROFILES) == 20
    assert len(MODULE.SOURCE_CANDIDATES) * len(MODULE.PROFILES) == 20
    candidates, profiles = MODULE._trial_design("source-managed-v1")
    assert len(candidates) == 3
    assert [profile.name for profile in profiles] == ["managed_60bps_stop"]
    candidates, profiles = MODULE._trial_design("zero-lag-short-managed-v1")
    assert len(candidates) == 1
    assert candidates[0].long_strategy is None
    assert candidates[0].short_strategy == "zero_lag_reclaim_short"
    assert [profile.name for profile in profiles] == ["managed_60bps_stop"]
    candidates, profiles = MODULE._trial_design("liquidity-sweep-long-managed-v1")
    assert len(candidates) == 1
    assert candidates[0].name == "liquidity_sweep_long"
    assert candidates[0].long_strategy == "liquidity_sweep_long"
    assert candidates[0].short_strategy is None
    assert [profile.name for profile in profiles] == ["managed_60bps_stop"]
    candidates, profiles = MODULE._trial_design("liquidity-sweep-long-hv-v1")
    assert [candidate.name for candidate in candidates] == ["liquidity_sweep_long"]
    assert [profile.name for profile in profiles] == ["hypervelocity_long_35_30_24h"]
    candidates, profiles = MODULE._trial_design("liquidity-sweep-long-hv-wick-v1")
    assert [candidate.name for candidate in candidates] == ["liquidity_sweep_long_wick"]
    assert [profile.name for profile in profiles] == ["hypervelocity_long_35_30_24h"]
    candidates, profiles = MODULE._trial_design("liquidity-sweep-long-hv-stop60-v1")
    assert [candidate.name for candidate in candidates] == ["liquidity_sweep_long"]
    assert [profile.name for profile in profiles] == [
        "hypervelocity_long_35_30_24h_stop60"
    ]
    candidates, profiles = MODULE._trial_design("regime-router")
    assert [candidate.name for candidate in candidates] == ["regime_trend_router"]
    assert len(profiles) == 4
    candidates, profiles = MODULE._trial_design("regime-router-long-managed-v1")
    assert [candidate.name for candidate in candidates] == ["regime_trend_router_long"]
    assert candidates[0].long_strategy == "regime_trend_router_long"
    assert candidates[0].short_strategy is None
    assert [profile.name for profile in profiles] == ["managed_60bps_stop"]
    candidates, profiles = MODULE._trial_design("source-long-isolation-v1")
    assert [candidate.name for candidate in candidates] == [
        "donchian_trend_long",
        "squeeze_breakout_long",
        "liquidity_sweep_long",
        "zero_lag_reclaim_long",
        "regime_trend_router_long",
    ]
    assert all(candidate.long_strategy is not None for candidate in candidates)
    assert all(candidate.short_strategy is None for candidate in candidates)
    assert [profile.name for profile in profiles] == ["managed_60bps_stop"]


def test_source_cohort_and_hourly_execution_are_explicit_cli_options() -> None:
    parser = MODULE.build_parser()

    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--execution-timeframe",
            "1h",
            "--cohort",
            "source",
            "--output",
            "report.json",
        ]
    )

    assert parsed.execution_timeframe == "1h"
    assert parsed.cohort == "source"


def test_screen_artifact_identifies_non_btc_symbol(tmp_path: Path) -> None:
    """A non-BTC screen must not publish a BTC portfolio contract."""
    index = pd.date_range("2026-01-01", periods=24 * 60, freq="1min", tz="UTC")
    close = pd.Series(range(10_000, 10_000 + len(index)), dtype=float)
    bars = pd.DataFrame(
        {
            "timestamp": index,
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
            "source": "hl",
        }
    )
    funding = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=24, freq="1h", tz="UTC"),
            "funding_rate": 0.0,
        }
    )
    bars_path = tmp_path / "ETH_1m.parquet"
    funding_path = tmp_path / "ETH_funding.parquet"
    bars.to_parquet(bars_path, index=False)
    funding.to_parquet(funding_path, index=False)

    report = MODULE.run_screen(
        symbol="eth",
        bars_path=bars_path,
        funding_paths=[funding_path],
        start=index[0].to_pydatetime(),
        end=(index[-1] + pd.Timedelta(minutes=1)).to_pydatetime(),
        execution_timeframe="1h",
        cohort="liquidity-sweep-long-managed-v1",
    )

    assert report["symbol"] == "ETH"
    assert report["portfolio_contract"].endswith("one_eth_position")
    assert report["data_evidence"]["symbol"] == "ETH"


def test_liquidity_sweep_long_cohort_is_an_explicit_cli_option() -> None:
    """Long isolation must remain an explicit report-only research choice."""
    parser = MODULE.build_parser()

    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--execution-timeframe",
            "1h",
            "--cohort",
            "liquidity-sweep-long-managed-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed.cohort == "liquidity-sweep-long-managed-v1"

    parsed_hv = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--cohort",
            "liquidity-sweep-long-hv-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed_hv.cohort == "liquidity-sweep-long-hv-v1"

    parsed_wick = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--cohort",
            "liquidity-sweep-long-hv-wick-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed_wick.cohort == "liquidity-sweep-long-hv-wick-v1"

    parsed_stop = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--cohort",
            "liquidity-sweep-long-hv-stop60-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed_stop.cohort == "liquidity-sweep-long-hv-stop60-v1"


def test_regime_router_long_cohort_is_an_explicit_cli_option() -> None:
    """Regime-router long isolation must remain report-only and explicit."""
    parser = MODULE.build_parser()

    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--execution-timeframe",
            "1h",
            "--cohort",
            "regime-router-long-managed-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed.cohort == "regime-router-long-managed-v1"


def test_source_long_isolation_cohort_is_an_explicit_cli_option() -> None:
    """The full source-derived long cohort must be explicit and bounded."""
    parser = MODULE.build_parser()

    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--execution-timeframe",
            "1h",
            "--cohort",
            "source-long-isolation-v1",
            "--output",
            "report.json",
        ]
    )

    assert parsed.cohort == "source-long-isolation-v1"


def test_canonical_hypervelocity_risk_surface_is_predeclared() -> None:
    """Canonical entries must test the promoted sizing against its own stream."""
    parser = MODULE.build_parser()
    parsed = parser.parse_args(
        [
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-01T00:00:00Z",
            "--end",
            "2026-01-02T00:00:00Z",
            "--cohort",
            "hypervelocity-risk-surface",
            "--output",
            "report.json",
        ]
    )
    candidates, profiles = MODULE._trial_design(parsed.cohort)

    assert [candidate.name for candidate in candidates] == ["hypervelocity_control"]
    assert [profile.name for profile in profiles] == [
        "hypervelocity_50_30",
        "hypervelocity_70_30",
        "hypervelocity_70_40_control",
    ]
    assert [(profile.margin_fraction, profile.leverage) for profile in profiles] == [
        (0.5, 30.0),
        (0.7, 30.0),
        (0.7, 40.0),
    ]


def test_canonical_direction_isolation_is_predeclared() -> None:
    """Long and short economics must be measured as standalone portfolios."""
    candidates, profiles = MODULE._trial_design("hypervelocity-direction-surface")

    assert [candidate.name for candidate in candidates] == [
        "hypervelocity_long_only",
        "hypervelocity_short_only",
    ]
    assert [profile.name for profile in profiles] == [
        "hypervelocity_50_30",
        "hypervelocity_70_30",
    ]


def test_hypervelocity_direction_isolation_disables_only_opposite_entries() -> None:
    """Direction isolation must preserve timestamps and exit telemetry."""
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    signals = pd.DataFrame(
        {
            "long_entry": [True, False],
            "short_entry": [False, True],
            "long_exit": [False, True],
            "short_exit": [True, False],
        },
        index=index,
    )

    long_only = MODULE._isolate_hypervelocity_direction(
        signals, "hypervelocity_long_only"
    )
    short_only = MODULE._isolate_hypervelocity_direction(
        signals, "hypervelocity_short_only"
    )

    assert long_only.index.equals(index)
    assert long_only["long_entry"].tolist() == [True, False]
    assert long_only["short_entry"].tolist() == [False, False]
    assert long_only["short_exit"].tolist() == [True, False]
    assert short_only["long_entry"].tolist() == [False, False]
    assert short_only["short_entry"].tolist() == [False, True]
    assert short_only["long_exit"].tolist() == [False, True]


def test_price_barrier_bps_translate_to_leveraged_margin_return() -> None:
    profile = MODULE.ScreenProfile("original-shape", 0.70, 40.0, 20.0, None, None)

    config = MODULE.profile_config(profile)

    assert config.initial_equity == 15_000.0
    assert config.target_margin_pct == pytest.approx(8.0)
    assert config.stop_margin_pct is None
    assert config.venue_max_leverage == 40.0


def test_non_btc_profile_uses_asset_venue_leverage_contract() -> None:
    """Cross-asset liquidation math must use the asset's venue maximum."""
    profile = MODULE.ScreenProfile("managed", 0.25, 10.0, 80.0, 40.0, 1_440)

    config = MODULE.profile_config(profile, symbol="hype")

    assert config.symbol == "HYPE"
    assert config.venue_max_leverage == 10.0


def test_hypervelocity_control_uses_faithful_contract_and_maker_friction() -> None:
    candidates, profiles = MODULE._trial_design("hypervelocity-control")

    config = MODULE.profile_config(profiles[0])

    assert [candidate.name for candidate in candidates] == ["hypervelocity_control"]
    assert config.initial_equity == 15_000.0
    assert config.margin_fraction == 0.70
    assert config.leverage == 40.0
    assert config.target_margin_pct == 8.0
    assert config.stop_margin_pct is None
    assert config.entry_fee_rate == 0.00015
    assert config.target_fee_rate == 0.00015
    assert config.entry_slippage_bps == 0.0
    assert not config.close_on_opposite_signal
    assert not config.reverse_on_opposite_signal


def test_hypervelocity_risk_profile_keeps_eight_percent_margin_target() -> None:
    """Changing leverage must translate the price target without friction drift."""
    profile = MODULE.ScreenProfile(
        "hypervelocity_70_30",
        0.70,
        30.0,
        8.0 / 30.0 * 100.0,
        None,
        None,
    )

    config = MODULE.profile_config(profile)

    assert config.initial_equity == 15_000.0
    assert config.margin_fraction == 0.70
    assert config.leverage == 30.0
    assert config.target_margin_pct == pytest.approx(8.0)
    assert config.venue_max_leverage == 40.0
    assert config.entry_fee_rate == pytest.approx(0.00015)
    assert config.target_fee_rate == pytest.approx(0.00015)
    assert not config.close_on_opposite_signal
    assert not config.reverse_on_opposite_signal


def test_long_challenger_uses_current_risk_contract_with_24_hour_hold() -> None:
    """The source long signal must be challenged without an implicit risk grid."""
    _, profiles = MODULE._trial_design("liquidity-sweep-long-hv-v1")

    config = MODULE.profile_config(profiles[0], bar_minutes=60)

    assert config.initial_equity == 15_000.0
    assert config.margin_fraction == pytest.approx(0.35)
    assert config.leverage == pytest.approx(30.0)
    assert config.target_margin_pct == pytest.approx(8.0)
    assert config.stop_margin_pct is None
    assert config.max_hold_bars == 24
    assert config.same_direction_reentry_requires_reset
    assert not config.close_on_opposite_signal


def test_long_fixed_stop_challenger_preserves_target_and_hold_contract() -> None:
    """The bounded stop challenge changes only the predeclared 60 bps stop."""
    _, profiles = MODULE._trial_design("liquidity-sweep-long-hv-stop60-v1")

    config = MODULE.profile_config(profiles[0], bar_minutes=60)

    assert config.margin_fraction == pytest.approx(0.35)
    assert config.leverage == pytest.approx(30.0)
    assert config.target_margin_pct == pytest.approx(8.0)
    assert config.stop_margin_pct == pytest.approx(18.0)
    assert config.max_hold_bars == 24


def test_long_wick_challenger_attaches_only_causal_signal_bar_low() -> None:
    """A bullish sweep stop may use its completed signal wick, not future lows."""
    index = pd.date_range("2026-01-01", periods=3, freq="1h", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [98.0, 99.0, 100.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [1.0, 1.0, 1.0],
        },
        index=index,
    )
    signals = pd.DataFrame(
        {
            "long_entry": [False, True, False],
            "short_entry": [False, False, False],
            "long_exit": [False, False, False],
            "short_exit": [False, False, False],
        },
        index=index,
    )

    result = MODULE._attach_long_signal_wick_stop(bars, signals)

    assert pd.isna(result["stop_price"].iloc[0])
    assert result["stop_price"].iloc[1] == pytest.approx(99.0)
    assert pd.isna(result["stop_price"].iloc[2])
    assert "stop_price" not in signals


def test_execution_resample_is_causal_and_preserves_hourly_funding() -> None:
    index = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": range(100, 110),
            "high": range(101, 111),
            "low": range(99, 109),
            "close": range(100, 110),
            "volume": [1.0] * 10,
            "funding_rate": [0.001] + [0.0] * 9,
        },
        index=index,
    )

    result = MODULE.resample_execution_bars(bars, "5min")

    assert len(result) == 2
    assert result.iloc[0]["open"] == 100
    assert result.iloc[0]["close"] == 104
    assert result.iloc[0]["high"] == 105
    assert result.iloc[0]["low"] == 99
    assert result.iloc[0]["volume"] == 5.0
    assert result.iloc[0]["funding_rate"] == pytest.approx(0.001)


def test_maximum_hold_minutes_scale_to_execution_timeframe() -> None:
    profile = MODULE.ScreenProfile("five-minute", 0.25, 5.0, 80.0, 40.0, 360)

    config = MODULE.profile_config(profile, bar_minutes=5)

    assert config.max_hold_bars == 72


def test_trade_attribution_separates_direction_and_exit_reasons() -> None:
    trades = (
        _trade("long", 15.0, "target", fees=2.0),
        _trade("long", -5.0, "stop", fees=1.0),
        _trade("short", -4.0, "liquidation", fees=3.0),
    )

    result = MODULE._trade_attribution(trades)

    assert result["long"] == {
        "completed_trades": 2,
        "wins": 1,
        "losses": 1,
        "net_pnl_usd": pytest.approx(10.0),
        "gross_profit_usd": pytest.approx(15.0),
        "gross_loss_usd": pytest.approx(5.0),
        "profit_factor": pytest.approx(3.0),
        "fees_usd": pytest.approx(3.0),
        "funding_cashflow_usd": pytest.approx(0.0),
    }
    assert result["short"]["completed_trades"] == 1
    assert result["short"]["profit_factor"] == pytest.approx(0.0)
    assert result["exit_reasons"] == {"liquidation": 1, "stop": 1, "target": 1}


def _trade(
    direction: str,
    net_pnl_usd: float,
    exit_reason: str,
    *,
    fees: float,
) -> SharedPortfolioTrade:
    """Build the minimum complete trade record needed for attribution tests."""
    return SharedPortfolioTrade(
        signal_name=f"test_{direction}",
        direction=direction,
        signal_time_utc="2026-01-01T00:00:00+00:00",
        entry_time_utc="2026-01-01T00:01:00+00:00",
        exit_time_utc="2026-01-01T00:02:00+00:00",
        signal_position=0,
        entry_position=1,
        exit_position=2,
        entry_price=100.0,
        exit_price=101.0,
        target_price=None,
        stop_price=None,
        liquidation_price=50.0,
        quantity=1.0,
        margin_usd=10.0,
        notional_usd=100.0,
        leverage=10.0,
        gross_pnl_usd=net_pnl_usd + fees,
        fees_usd=fees,
        funding_cashflow_usd=0.0,
        net_pnl_usd=net_pnl_usd,
        equity_before_usd=100.0,
        equity_after_usd=100.0 + net_pnl_usd,
        exit_reason=exit_reason,
        same_bar_ambiguous=False,
    )
