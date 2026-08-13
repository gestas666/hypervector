"""Report-only mature-profit floor mechanism tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_mature_profit_floor import (
    MATURE_PROFIT_FLOOR_POLICIES,
    build_mature_profit_floor_mechanism,
    build_open_mature_profit_floor_challenger,
)
from hypervector.research.cohort_profit_lock_policy import evaluate_profit_lock_path
from hypervector.research.cohort_trade_reflection_index import Candle


def test_floor_only_policy_preserves_a_fixed_floor_after_larger_peak() -> None:
    """A later peak must not turn the mature-profit floor into a tight trail."""
    policy = MATURE_PROFIT_FLOOR_POLICIES[0]
    bars = (
        Candle(60_000, 100.0, 101.2, 99.8, 101.0),
        Candle(120_000, 102.0, 110.0, 101.0, 109.0),
        Candle(180_000, 100.4, 100.5, 100.2, 100.3),
    )

    state = evaluate_profit_lock_path(policy, "long", bars, 100.0)

    assert state.activation_timestamp_ms == 60_000
    assert state.trigger is not None
    assert state.trigger.trigger_timestamp_ms == 180_000
    assert state.trigger.stop_price == pytest.approx(100.25)
    assert state.trigger.best_completed_price == pytest.approx(110.0)


def test_mature_profit_floor_report_is_explicitly_non_authoritative() -> None:
    """The new challenger must remain report-only and expose frozen hypotheses."""
    report = build_mature_profit_floor_mechanism(
        _cohort_rows(
            _bar(60_000, 100.0, 101.2, 99.8, 101.0),
            _bar(120_000, 102.0, 110.0, 101.0, 109.0),
            _bar(180_000, 100.4, 100.5, 100.2, 100.3),
        ),
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    assert report["mode"] == "cohort_mature_profit_floor_mechanism_v1"
    assert report["mechanism"] == "floor_only_after_completed_bar_activation"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_strategy_changes"] is False
    assert report["continuous_trailing_enabled"] is False
    assert [row["policy_id"] for row in report["policies"]] == [
        "a100_floor25_only",
        "a250_floor25_only",
        "a500_floor25_only",
    ]
    summary = report["summary_by_policy"]["a100_floor25_only"]
    assert summary["eligible_lifecycles"] == 1
    assert summary["triggered"] == 1
    assert summary["mean_estimated_net_return_bps"] == pytest.approx(14.98875)


def test_open_mature_profit_floor_reports_fixed_active_stop() -> None:
    """Open evidence must expose a non-trailing floor without execution authority."""
    report = build_open_mature_profit_floor_challenger(
        {
            60_000: Candle(60_000, 100.0, 101.2, 99.8, 101.0),
            120_000: Candle(120_000, 102.0, 110.0, 101.0, 109.0),
        },
        "long",
        {"price": 100.0, "size": 1.0, "venue_timestamp_ms": 10_000},
        {
            "mark_price": 110.0,
            "fees_usd": 0.045,
            "funding_usd": 0.0,
            "active_lifecycle_marked_net_pnl_usd": 9.955,
        },
        240_000,
    )

    assert report["mode"] == "cohort_open_mature_profit_floor_challenger_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["continuous_trailing_enabled"] is False
    policy = report["policies"]["a100_floor25_only"]
    assert policy["status"] == "armed_not_triggered"
    assert policy["active_stop_price"] == pytest.approx(100.25)
    assert policy["best_completed_price"] == pytest.approx(110.0)


def _cohort_rows(*bars: dict[str, object]) -> list[dict[str, object]]:
    return [
        {
            "event_type": "market_candles",
            "run_id": "run-current",
            "payload": {"timeframe": "1m", "bars": {"HYPE": list(bars)}},
        }
    ]


def _bar(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _asset_rows() -> list[dict[str, object]]:
    return [
        _event(
            "fill",
            oid=11,
            trade_id=101,
            venue_timestamp_ms=10_000,
            price=100.0,
            size=1.0,
            fee_usd=0.045,
        ),
        _event("funding", venue_timestamp_ms=120_000, usdc_delta=-0.01),
        _event(
            "fill",
            oid=12,
            trade_id=102,
            venue_timestamp_ms=250_000,
            price=100.0,
            size=1.0,
            fee_usd=0.045,
        ),
    ]


def _event(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_type": event_type, "payload": payload}


def _trade() -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "source_run_id": "run-current",
        "source_profile_fingerprint": "profile-current",
        "symbol": "HYPE",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "side": "long",
        "entry_oid": 11,
        "exit_oid": 12,
        "entry": {"price": 100.0, "size": 1.0, "venue_timestamp_ms": 10_000},
        "exit": {
            "price": 100.0,
            "size": 1.0,
            "venue_timestamp_ms": 250_000,
            "expected_reference_price": 100.0,
        },
        "fees_usd": 0.09,
        "funding_usd": -0.01,
        "net_pnl_usd": -0.10,
    }
