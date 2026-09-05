"""Tests for the frozen HIP-3 opening-range development replay."""

from hypervector.research.hip3_opening_range_breakout_candidate import (
    hip3_opening_range_breakout_portfolio_config,
)
from hypervector.research.hip3_opening_range_breakout_signals import (
    Hip3OpeningRangeBreakoutConfig,
)
from hypervector.research.mu_hip3_archive_candidate import MuArchiveExecution


def _execution() -> MuArchiveExecution:
    return MuArchiveExecution(
        effective_taker_fee_rate=0.0000864,
        notional_usd=5000.0,
        venue_max_leverage=20.0,
        nominal_latency_bps_per_side=1.0,
        stress_latency_bps_per_side=2.0,
        stress_visible_tail_bps_per_side=7.164181705351157,
        fixed_stop_bps=80.0,
        maximum_hold_bars=24,
        risk_high_column="risk_high",
        risk_low_column="risk_low",
        entry_risk_high_column="risk_entry_high",
        entry_risk_low_column="risk_entry_low",
        symbol="xyz:SPCX",
    )


def test_portfolio_contract_matches_frozen_v53_sizing_and_six_hour_ceiling() -> None:
    execution = _execution()
    signal = Hip3OpeningRangeBreakoutConfig(clearance_bps=54.84179701463096)

    nominal = hip3_opening_range_breakout_portfolio_config(
        execution, signal, stress=False
    )
    stress = hip3_opening_range_breakout_portfolio_config(
        execution, signal, stress=True
    )

    assert nominal.initial_equity == 5000.0
    assert nominal.margin_fraction == 0.1
    assert nominal.leverage == 10.0
    assert nominal.max_hold_bars == 24
    assert nominal.max_hold_seconds == 21600
    assert nominal.maximum_stop_distance_bps == 80.0
    assert nominal.entry_fee_rate == 0.0000864
    assert nominal.entry_slippage_bps == 1.0
    assert stress.entry_slippage_bps == 9.164181705351158
