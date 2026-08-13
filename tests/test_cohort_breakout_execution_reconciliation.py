"""Tests for actual-versus-proxy breakout execution reconciliation."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_breakout_execution_reconciliation import (
    reconcile_breakout_execution,
)
from hypervector.research.cohort_breakout_policy_models import (
    BreakoutPolicyForwardSpec,
)

_RUN_ID = "breakout-source-run"
_STRATEGY = "hype_breakout_onset_bidirectional_v1"


def test_reconciliation_binds_exact_entry_and_closed_lifecycle_costs() -> None:
    """Actual fills must remain distinct from modeled reference-price outcomes."""
    lifecycle = _lifecycle(status="resolved", estimated_net_return_bps=-93.0)
    records = [_snapshot(_entry_fill()), _snapshot(_entry_fill(), _close_fill())]

    lifecycles, summary = reconcile_breakout_execution(
        records,
        [lifecycle],
        spec=_spec(),
    )

    actual = lifecycles[0]["actual_execution"]
    assert actual["status"] == "resolved"
    assert actual["entry_price"] == 100.1
    assert actual["exit_price"] == 99.17
    assert actual["exit_reason"] == "protective_stop"
    assert actual["fees_usd"] == 0.07
    assert actual["funding_usd"] == -0.01
    assert actual["net_pnl_usd"] == -0.69
    assert actual["net_return_bps"] == pytest.approx(-91.9080919)
    assert actual["net_return_delta_vs_proxy_bps"] == pytest.approx(1.0919081)
    assert summary == {
        "matched_entries": 1,
        "resolved_actual": 1,
        "open_actual": 0,
        "not_executed_source_profile": 0,
        "not_executed_or_withheld": 0,
    }


def test_reconciliation_marks_unclosed_entry_open_without_inventing_a_fill() -> None:
    """A recorded entry without a close is open, not a resolved proxy outcome."""
    lifecycles, summary = reconcile_breakout_execution(
        [_snapshot(_entry_fill())],
        [_lifecycle(status="pending")],
        spec=_spec(),
    )

    actual = lifecycles[0]["actual_execution"]
    assert actual["status"] == "open"
    assert actual["entry_oid"] == 11
    assert "net_pnl_usd" not in actual
    assert summary["open_actual"] == 1


def test_reconciliation_labels_unexecuted_counterfactual_explicitly() -> None:
    """A staged-symbol proxy must not be presented as a missing live fill."""
    lifecycles, summary = reconcile_breakout_execution(
        [],
        [_lifecycle(symbol="BTC", status="resolved")],
        spec=_spec(),
    )

    assert lifecycles[0]["actual_execution"] == {
        "status": "not_executed_source_profile"
    }
    assert summary["not_executed_source_profile"] == 1


def _spec() -> BreakoutPolicyForwardSpec:
    return BreakoutPolicyForwardSpec(
        source_strategy_id=_STRATEGY,
        source_run_id=_RUN_ID,
        cutoff_time_ms=1,
        symbols=("BTC", "HYPE"),
        source_execution_symbols=("HYPE",),
        competing_execution_providers_by_symbol={},
        stop_bps=80.0,
        soft_hold_minutes=480,
        hard_hold_minutes=1_440,
        maximum_entry_delay_seconds=60,
        modeled_round_trip_friction_bps=13.0,
        notional_usd_by_symbol={"BTC": 25.0, "HYPE": 75.0},
    )


def _lifecycle(**updates: object) -> dict[str, object]:
    base: dict[str, object] = {
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
        "side": "long",
        "signal_time_ms": 60_000,
        "entry_time_ms": 60_000,
        "entry_price": 100.0,
        "status": "resolved",
        "estimated_net_return_bps": -93.0,
    }
    return base | updates


def _entry_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": _STRATEGY,
        "origin_run_id": _RUN_ID,
        "operation": "entry",
        "trade_id": 1,
        "oid": 11,
        "venue_timestamp_ms": 60_500,
        "price": 100.1,
        "size": 0.75,
        "direction": "Open Long",
        "fee_usd": 0.03,
        "expected_price": 100.0,
        "slippage_bps": -10.0,
    }


def _close_fill() -> dict[str, object]:
    return {
        "symbol": "HYPE",
        "strategy_id": _STRATEGY,
        "origin_run_id": _RUN_ID,
        "operation": "protective_stop",
        "trade_id": 2,
        "oid": 22,
        "venue_timestamp_ms": 120_500,
        "price": 99.17,
        "size": 0.75,
        "direction": "Close Long",
        "fee_usd": 0.04,
        "entry_price": 100.1,
        "entry_venue_timestamp_ms": 60_500,
        "lifecycle_fees_usd": 0.07,
        "lifecycle_funding_usd": -0.01,
        "net_pnl_usd": -0.69,
        "holding_time_ms": 60_000,
        "exit_reason": "protective_stop",
    }


def _snapshot(*fills: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": "cohort_snapshot",
        "run_id": _RUN_ID,
        "payload": {"recent_fills": list(fills)},
    }
