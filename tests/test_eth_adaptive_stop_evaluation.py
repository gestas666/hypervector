"""Tests for equal-risk ETH adaptive-stop evaluation and promotion gates."""

from __future__ import annotations

import pytest

from hypervector.research.eth_adaptive_stop_evaluation import (
    compare_equal_risk,
    evaluate_eth_promotion,
    summarize_equal_risk,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade


def _trade(
    *,
    side: str = "long",
    month: str = "2026-01",
    stop_bps: float = 60.0,
    net_bps: float = 100.0,
) -> HypeExitTrade:
    entry = 100.0
    stop = entry * (
        1.0 - stop_bps / 10_000.0 if side == "long" else 1.0 + stop_bps / 10_000.0
    )
    return HypeExitTrade(
        side=side,
        signal_time_utc=f"{month}-02T00:00:00+00:00",
        entry_time_utc=f"{month}-02T00:01:00+00:00",
        exit_time_utc=f"{month}-02T00:02:00+00:00",
        entry_price=entry,
        exit_price=101.0,
        stop_price=stop,
        gross_return_bps=net_bps + 9.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=net_bps,
        hold_minutes=1,
        maximum_favorable_excursion_bps=120.0,
        maximum_adverse_excursion_bps=20.0,
        exit_reason="maximum_hold",
    )


def test_equal_risk_summary_scales_each_trade_by_resolved_stop() -> None:
    """A 120-bps stop receives half the notional of the 60-bps control."""
    summary = summarize_equal_risk(
        (
            _trade(stop_bps=60.0, net_bps=-20.0),
            _trade(stop_bps=120.0, net_bps=100.0),
        )
    )

    assert summary["equal_risk_net_return_bps"] == pytest.approx(30.0)
    assert summary["equal_risk_net_excluding_largest_winner_bps"] == pytest.approx(
        -20.0
    )
    assert summary["resolved_stop_bps"]["maximum"] == pytest.approx(120.0)


def test_comparison_reports_monthly_and_drawdown_deltas() -> None:
    """Partition comparison must expose every preregistered robustness input."""
    control = (
        _trade(month="2026-01", net_bps=-40.0),
        _trade(side="short", month="2026-02", net_bps=20.0),
    )
    candidate = (
        _trade(month="2026-01", net_bps=-10.0),
        _trade(side="short", month="2026-02", net_bps=50.0),
    )

    comparison = compare_equal_risk(control, candidate)

    assert comparison["delta"]["net_return_bps"] == pytest.approx(60.0)
    assert comparison["delta"]["worst_monthly_fold_bps"] == pytest.approx(30.0)
    assert comparison["candidate"]["maximum_drawdown_bps"] == pytest.approx(10.0)


def test_promotion_requires_every_preregistered_gate() -> None:
    """One failing robustness condition must retain the V61 control."""
    comparison = compare_equal_risk(
        (
            _trade(net_bps=-10.0),
            _trade(side="short", net_bps=-10.0),
        ),
        (
            _trade(net_bps=20.0),
            _trade(side="short", net_bps=20.0),
        ),
    )
    partitions = {
        "construction": comparison,
        "confirmation": comparison,
        "opened_final_audit": comparison,
    }

    passed = evaluate_eth_promotion(partitions, source_signal_parity=True)
    failed = evaluate_eth_promotion(partitions, source_signal_parity=False)

    assert passed["passed"] is True
    assert passed["decision"] == "eligible_for_live_implementation_review"
    assert failed["passed"] is False
    assert failed["decision"] == "retain_v61_eth_control"
    assert failed["criteria"]["exact_entry_signal_timestamp_parity"] is False
