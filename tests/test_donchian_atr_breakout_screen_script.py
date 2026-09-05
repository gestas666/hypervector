"""Tests for the immutable V75 Donchian/ATR screen command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "donchian_atr_breakout_screen.py"
SPEC = spec_from_file_location("donchian_atr_breakout_screen", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_profiles_match_preregistered_nominal_and_stress_costs() -> None:
    """V75 must run two cost profiles without a hidden parameter grid."""
    assert [(profile.name, profile.slippage_bps) for profile in MODULE.PROFILES] == [
        ("nominal_14bps_rt", 2.5),
        ("stress_20bps_rt", 5.5),
    ]


def test_portfolio_config_uses_fixed_risk_and_verified_zec_leverage() -> None:
    """The aggressive contract risks equity, not an arbitrary fixed notional."""
    config = MODULE.portfolio_config("ZEC", MODULE.PROFILES[1])

    assert config.initial_equity == pytest.approx(5_000.0)
    assert config.margin_fraction == pytest.approx(0.15)
    assert config.leverage == pytest.approx(5.0)
    assert config.venue_max_leverage == pytest.approx(10.0)
    assert config.risk_fraction_per_position == pytest.approx(0.0075)
    assert config.maximum_notional_usd == pytest.approx(5_000.0)
    assert config.target_margin_pct is None
    assert config.target_r_multiple is None
    assert config.max_hold_seconds == 2_592_000


def test_parser_requires_explicit_inputs_and_supports_native_zec_bars() -> None:
    """A report must bind exact data, cadence, chronology, and output."""
    parsed = MODULE.build_parser().parse_args(
        [
            "--symbol",
            "ZEC",
            "--bars",
            "bars.parquet",
            "--bars-timeframe",
            "15min",
            "--funding",
            "funding.parquet",
            "--start",
            "2026-01-28T00:00:00Z",
            "--score-start",
            "2026-02-02T00:00:00Z",
            "--end",
            "2026-05-01T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert parsed.symbol == "ZEC"
    assert parsed.bars_timeframe == "15min"
    assert parsed.output == Path("report.json")
