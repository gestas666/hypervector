"""Causal post-soft protective-trail challenger evidence."""

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_post_soft_trail_challenger import (
    build_post_soft_trail_challenger,
)
from hypervector.research import cohort_post_soft_trail_challenger as trail_module


@dataclass(frozen=True)
class _Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def test_post_soft_trail_uses_prior_completed_peak_for_next_bar() -> None:
    """A candle cannot form a new peak and hit its resulting trail itself."""
    report = build_post_soft_trail_challenger(
        [_outcome(actual_exit_ms=310_000)],
        [_trade(actual_exit_ms=310_000)],
        {
            "HYPE": {
                180_000: _Candle(180_000, 111.6, 112.0, 111.5, 111.8),
                240_000: _Candle(240_000, 111.6, 111.7, 111.0, 111.1),
            }
        },
        {"HYPE": {120_000: -0.01, 240_000: -0.02}},
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_strategy_changes"] is False
    result = report["latest_results"][0]["policies"]["30bps"]
    assert result["status"] == "triggered"
    assert result["trigger_timestamp_ms"] == 240_000
    assert result["trigger_reference_price"] == pytest.approx(111.6)
    assert result["best_completed_price_before_trigger"] == pytest.approx(112.0)
    assert result["estimated_exit_price"] == pytest.approx(111.4884)
    summary = report["summary_by_giveback_bps"]["30"]
    assert summary["triggered"] == 1
    assert summary["actual_net_pnl_usd"] == pytest.approx(5.87)
    assert summary["estimated_soft_net_pnl_usd"] == pytest.approx(9.79)


def test_post_soft_trail_does_not_use_same_bar_hindsight() -> None:
    """A trail first derived at a completed bar applies only to later bars."""
    report = build_post_soft_trail_challenger(
        [_outcome(actual_exit_ms=230_000)],
        [_trade(actual_exit_ms=230_000)],
        {
            "HYPE": {
                180_000: _Candle(180_000, 111.6, 112.0, 111.5, 111.8),
            }
        },
        {"HYPE": {120_000: -0.01}},
    )

    result = report["latest_results"][0]["policies"]["30bps"]
    assert result["status"] == "not_triggered_before_actual_exit"
    assert result["trigger_timestamp_ms"] is None
    assert result["estimated_net_pnl_usd"] == pytest.approx(5.87)
    summary = report["summary_by_giveback_bps"]["30"]
    assert summary["triggered"] == 0
    assert summary["not_triggered"] == 1


def test_open_post_soft_trail_reports_causal_trigger_without_authority() -> None:
    """An open extension exposes frozen trail state without changing the trade."""
    builder = getattr(trail_module, "build_open_post_soft_trail_status", None)
    assert callable(builder), "open post-soft trail builder is missing"

    report = builder(
        {
            120_000: _Candle(120_000, 109.0, 110.2, 108.9, 110.0),
            180_000: _Candle(180_000, 111.6, 112.0, 111.5, 111.8),
            240_000: _Candle(240_000, 111.6, 111.7, 111.0, 111.1),
        },
        "long",
        soft_deadline_ms=180_000,
        as_of_ms=310_000,
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert report["status"] == "observed"
    assert report["baseline_price"] == pytest.approx(110.0)
    policy = report["policies"]["30bps"]
    assert policy["status"] == "triggered"
    assert policy["trigger_timestamp_ms"] == 240_000
    assert policy["trigger_reference_price"] == pytest.approx(111.6)
    assert policy["best_completed_price_before_trigger"] == pytest.approx(112.0)


def test_open_post_soft_trail_never_uses_same_bar_hindsight() -> None:
    """The completed bar that establishes a peak cannot hit its new trail."""
    builder = getattr(trail_module, "build_open_post_soft_trail_status", None)
    assert callable(builder), "open post-soft trail builder is missing"

    report = builder(
        {
            120_000: _Candle(120_000, 109.0, 110.2, 108.9, 110.0),
            180_000: _Candle(180_000, 111.6, 112.0, 110.0, 111.8),
        },
        "long",
        soft_deadline_ms=180_000,
        as_of_ms=250_000,
    )

    policy = report["policies"]["30bps"]
    assert policy["status"] == "armed_not_triggered"
    assert policy["trigger_timestamp_ms"] is None
    assert policy["best_completed_price"] == pytest.approx(112.0)
    assert policy["active_trail_price"] == pytest.approx(111.664)


def _outcome(*, actual_exit_ms: int) -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "side": "long",
        "soft_deadline_timestamp_ms": 180_000,
        "actual_exit_timestamp_ms": actual_exit_ms,
        "soft_reference_price": 110.0,
        "estimated_soft_exit_price": 109.89,
        "entry_fee_usd": 0.045,
        "actual_exit_fee_usd": 0.0477,
        "actual_net_pnl_usd": 5.87,
        "estimated_soft_net_pnl_usd": 9.79,
    }


def _trade(*, actual_exit_ms: int) -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "side": "long",
        "entry": {
            "price": 100.0,
            "size": 1.0,
            "venue_timestamp_ms": 70_000,
        },
        "exit": {
            "price": 106.0,
            "size": 1.0,
            "venue_timestamp_ms": actual_exit_ms,
        },
    }
