"""Tests for the immutable V73 SMA/ATR trend screen command."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pandas as pd
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "sma_atr_trend_screen.py"
SPEC = spec_from_file_location("sma_atr_trend_screen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_profiles_are_exactly_nominal_and_twenty_bps_round_trip() -> None:
    """The V73 command must not hide a parameter or friction grid."""
    assert [(profile.name, profile.slippage_bps) for profile in MODULE.PROFILES] == [
        ("nominal_14bps_rt", 2.5),
        ("stress_20bps_rt", 5.5),
    ]


def test_portfolio_config_preserves_fixed_risk_contract() -> None:
    """Sizing and exits must match the preregistration exactly."""
    config = MODULE.portfolio_config("SOL", MODULE.PROFILES[1])

    assert config.initial_equity == pytest.approx(5_000.0)
    assert config.margin_fraction == pytest.approx(0.20)
    assert config.leverage == pytest.approx(5.0)
    assert config.risk_fraction_per_position == pytest.approx(0.0075)
    assert config.maximum_notional_usd == pytest.approx(5_000.0)
    assert config.minimum_stop_distance_bps == pytest.approx(20.0)
    assert config.maximum_stop_distance_bps is None
    assert config.target_margin_pct is None
    assert config.target_r_multiple is None
    assert config.max_hold_seconds == 2_592_000
    assert config.entry_slippage_bps == pytest.approx(5.5)
    assert config.market_exit_slippage_bps == pytest.approx(5.5)
    assert config.close_on_opposite_signal
    assert config.reverse_on_opposite_signal


def test_zec_extension_uses_verified_venue_cap_and_v74_identity() -> None:
    """ZEC must be a distinct preregistered transfer, not a V73 roster rewrite."""
    config = MODULE.portfolio_config("ZEC", MODULE.PROFILES[1])

    assert config.venue_max_leverage == pytest.approx(10.0)
    assert MODULE.report_identity("ZEC") == (
        "v74_zec_sma_atr_extension_report_only",
        "v74-seven-asset-zec-sma-atr-extension-20260901",
    )
    assert MODULE.report_identity("BTC") == (
        "v73_sma_atr_trend_report_only",
        "v73-eight-asset-sma-atr-trend-20260901",
    )


def test_asset_report_records_largest_winner_robustness() -> None:
    """A no-trade window must report unsupported rather than success-shaped data."""
    index = pd.date_range("2026-01-01", periods=31 * 16, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "funding_rate": 0.0,
        },
        index=index,
    )

    report = MODULE.evaluate_asset("BTC", bars)

    assert report["signal_counts"] == {"long": 0, "short": 0}
    assert len(report["profiles"]) == 2
    assert not report["supported_in_partition"]
    assert all(row["metrics"]["completed_trades"] == 0 for row in report["profiles"])


def test_parser_requires_explicit_bounded_inputs() -> None:
    """The report command must remain execution-incapable and window-bounded."""
    parsed = MODULE.build_parser().parse_args(
        [
            "--symbol",
            "ETH",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--start",
            "2025-07-28T00:00:00Z",
            "--end",
            "2026-01-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert parsed.symbol == "ETH"
    assert parsed.output == Path("report.json")


def test_parser_accepts_native_fifteen_minute_zec_evidence() -> None:
    """The ZEC transfer must declare its source cadence explicitly."""
    parsed = MODULE.build_parser().parse_args(
        [
            "--symbol",
            "ZEC",
            "--bars",
            "bars.parquet",
            "--bars-timeframe",
            "15min",
            "--score-start",
            "2026-02-02T00:00:00Z",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-28T00:00:00Z",
            "--end",
            "2026-05-01T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert parsed.bars_timeframe == "15min"
    assert parsed.score_start == datetime(2026, 2, 2, tzinfo=UTC)


def test_scored_inputs_retain_warmup_but_exclude_prescore_entries() -> None:
    """Indicators may warm up before the partition without scoring old signals."""
    index = pd.date_range("2026-01-28", periods=8, freq="15min", tz="UTC")
    bars = pd.DataFrame({"close": range(8)}, index=index)
    signals = pd.DataFrame(
        {
            "long_entry": [False, True, False, False, False, True, False, False],
            "short_entry": False,
        },
        index=index,
    )

    scored_bars, scored_signals = MODULE.scored_inputs(
        bars,
        signals,
        datetime(2026, 1, 28, 1, tzinfo=UTC),
    )

    assert scored_bars.index[0] == index[4]
    assert scored_signals["long_entry"].tolist() == [False, True, False, False]
