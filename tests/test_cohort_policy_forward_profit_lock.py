"""Profit-lock telemetry for exact config-bound forward lifecycles."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_policy_forward_profit_lock import (
    build_policy_forward_profit_lock_report,
)


@dataclass(frozen=True)
class _Candle:
    """One completed candle in the causal forward path."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def test_pending_short_reports_causal_lock_trigger_and_current_comparison() -> None:
    """A completed post-activation bar can trigger the frozen short lock."""
    report = build_policy_forward_profit_lock_report(
        _candles(), _exact_depth_report(), taker_fee_rate=0.00045
    )

    row = report["latest_results"][0]
    policy = row["policies"]["a25_floor15_trail10"]
    assert report["contract"]["execution_authority"] == "none"
    assert report["summary"]["lifecycles"] == 1
    assert policy["status"] == "triggered_before_current_boundary"
    assert policy["trigger_timestamp_ms"] == 120_000
    economics = policy["counterfactual_economics"]
    assert economics["estimated_net_pnl_excluding_funding_usd"] == pytest.approx(
        0.110390135
    )
    assert row["current_exact_net_excluding_funding_bps"] == pytest.approx(11.009)


def test_no_exact_attempts_produces_an_explicit_empty_report() -> None:
    """Absence of an eligible lifecycle cannot look like a zero-return trade."""
    report = build_policy_forward_profit_lock_report(
        {}, {"latest_attempts": []}, taker_fee_rate=0.00045
    )

    assert report["summary"] == {"lifecycles": 0, "pending": 0, "resolved": 0}
    assert report["latest_results"] == []


def _candles() -> dict[int, _Candle]:
    return {
        60_000: _Candle(60_000, 100.0, 100.05, 99.70, 99.80),
        120_000: _Candle(120_000, 99.75, 99.82, 99.75, 99.80),
    }


def _exact_depth_report() -> dict[str, object]:
    return {
        "latest_attempts": [
            {
                "candidate_strategy_id": "range_onset_sol_v49_config_bound_forward_v1",
                "source_run_id": "observe-v49",
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "SOL",
                "side": "short",
                "status": "exit_pending",
                "entry_time_ms": 10_000,
                "entry_price": 100.0,
                "entry_notional_usd": 100.0,
                "position_quantity": 1.0,
                "current_exit_time_ms": 250_000,
                "current_exit_price": 99.8,
                "current_gross_return_bps": 20.0,
                "current_fee_bps": 8.991,
                "current_funding_bps": 0.0,
                "current_net_return_bps": 11.009,
            }
        ]
    }
