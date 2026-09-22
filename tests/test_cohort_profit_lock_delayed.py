"""Validate causal completed-minute profit-lock economics without stop fills."""

from dataclasses import replace

import pytest

from hypervector.cohort_profit_lock_policy import ProfitLockPolicy
from hypervector.research.cohort_profit_lock_results import ProfitLockEconomics
from hypervector.research.cohort_trade_reflection_index import Candle

POLICY = ProfitLockPolicy("a100_floor25_trail50", 100.0, 25.0, 50.0)
ECONOMICS = ProfitLockEconomics(
    10_000, 190_000, 100.0, 99.0, 2.0, 0.1, 0.001, 1.1, -0.2, -2.498
)


def _result(
    side: str, bars: tuple[Candle, ...], *, adverse_bps: float = 5.0
) -> dict[str, object]:
    from hypervector.research.cohort_profit_lock_delayed import (
        build_delayed_profit_lock_result,
    )

    return build_delayed_profit_lock_result(
        POLICY,
        side,
        bars,
        ECONOMICS,
        {180_000: -0.2, 180_001: -3.0},
        adverse_bps=adverse_bps,
    )


@pytest.mark.parametrize("side", ["long", "short"])
def test_exit_uses_completed_close_costs_and_completion_time(side: str) -> None:
    """A stop crossing is not filled at a favorable intraminute stop price."""
    bars = (
        (
            Candle(60_000, 100.0, 102.0, 100.0, 102.0),
            Candle(120_000, 102.0, 102.0, 100.0, 100.1),
        )
        if side == "long"
        else (
            Candle(60_000, 100.0, 100.0, 98.0, 98.0),
            Candle(120_000, 98.0, 100.0, 98.0, 99.9),
        )
    )
    result = _result(side, bars)
    direction = 1 if side == "long" else -1
    exit_price = bars[-1].close * (1 - direction * 5 / 10_000)
    expected = direction * (exit_price - 100) * 2 - 0.1 - exit_price * 2 * 0.001 - 0.2
    assert result["estimated_exit_price"] == pytest.approx(exit_price)
    assert result["estimated_net_pnl_usd"] == pytest.approx(expected)
    assert result["decision_time_ms"] == 180_000
    assert result["trigger_timestamp_ms"] == 120_000
    assert result["fill_model"] == "completed_trigger_close_adverse_bps_proxy"


def test_gap_withholds_instead_of_ignoring_an_unobserved_crossing() -> None:
    """One missing required minute prevents a success-shaped counterfactual."""
    result = _result("long", (Candle(120_000, 102, 102, 100, 100.1),))
    assert result["status"] == "withheld_incomplete_candle_coverage"
    assert result["estimated_net_pnl_usd"] is None


def test_untriggered_policy_retains_actual_economics() -> None:
    """Fees and stress do not alter a trade when its lock never triggers."""
    result = _result(
        "long",
        (Candle(60_000, 100, 100.5, 99, 100), Candle(120_000, 100, 100.5, 99, 100)),
    )
    assert result["estimated_net_pnl_usd"] == ECONOMICS.actual_net_pnl_usd
    assert result["estimated_minus_actual_net_usd"] == 0


def test_armed_policy_without_crossing_retains_actual_exit() -> None:
    """Activation alone does not justify closing a continuing profitable trade."""
    result = _result(
        "long",
        (
            Candle(60_000, 100, 102, 100, 102),
            Candle(120_000, 102, 102.1, 101.8, 102),
        ),
    )
    assert result["status"] == "armed_not_triggered_before_actual_exit"
    assert result["estimated_net_pnl_usd"] == ECONOMICS.actual_net_pnl_usd


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), 10_000.0])
def test_invalid_slippage_fails_explicitly(bad: float) -> None:
    """Invalid execution stress cannot be reported as valid evidence."""
    with pytest.raises(ValueError, match="adverse_bps"):
        _result("long", (), adverse_bps=bad)


def test_entry_minute_is_excluded_even_at_exact_boundary() -> None:
    """Match the live controller's first fully post-entry candle convention."""
    from hypervector.research.cohort_profit_lock_delayed import (
        build_delayed_profit_lock_result,
    )

    result = build_delayed_profit_lock_result(
        POLICY,
        "long",
        (
            Candle(0, 100, 200, 50, 100),
            Candle(60_000, 100, 100, 100, 100),
            Candle(120_000, 100, 100, 100, 100),
        ),
        replace(ECONOMICS, entry_timestamp_ms=0),
        {},
        adverse_bps=5,
    )
    assert result["status"] == "not_activated_before_actual_exit"
