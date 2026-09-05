"""Exact order-submission outcome projection tests."""

from __future__ import annotations

import pytest

from hypervector.research import cohort_live_audit_execution
from hypervector.research.cohort_live_audit_execution import execution_summary
from hypervector.research.cohort_order_submission_outcomes import (
    build_order_submission_outcomes,
)


def test_submission_outcomes_preserve_acceptance_rejection_and_operation() -> None:
    """Every normalized venue acknowledgement remains attributable."""
    assets = {
        "BTC": [
            _row("order_acknowledgement", "entry", True, "filled"),
            _row("stop_order", "protective_stop", True, "resting"),
        ],
        "ETH": [
            _row(
                "order_acknowledgement",
                "entry",
                False,
                "error",
                error="insufficient margin",
                oid=None,
            ),
            _row("close", "reduce_only_close", True, "filled"),
            {"event_type": "close", "payload": {"reason": "protective_stop"}},
        ],
    }

    summary = build_order_submission_outcomes(assets, scope="current_run")

    assert summary == {
        "scope": "current_run",
        "status": "measured",
        "outcomes": 4,
        "accepted": 3,
        "rejected": 1,
        "source_events": {
            "close": 1,
            "order_acknowledgement": 2,
            "stop_order": 1,
        },
        "by_operation": {
            "entry": {
                "outcomes": 2,
                "accepted": 1,
                "rejected": 1,
                "by_status": {"error": 1, "filled": 1},
            },
            "protective_stop": {
                "outcomes": 1,
                "accepted": 1,
                "rejected": 0,
                "by_status": {"resting": 1},
            },
            "reduce_only_close": {
                "outcomes": 1,
                "accepted": 1,
                "rejected": 0,
                "by_status": {"filled": 1},
            },
        },
        "rejection_reasons": {"insufficient margin": 1},
    }


def test_no_acknowledgements_is_measured_zero() -> None:
    """A quiet ledger is distinct from an unavailable ledger."""
    summary = build_order_submission_outcomes(
        {"BTC": [{"event_type": "position", "payload": {}}]},
        scope="current_run",
    )

    assert summary["status"] == "measured_zero"
    assert summary["outcomes"] == 0
    assert summary["rejected"] == 0


def test_malformed_acknowledgement_fails_closed() -> None:
    """Truth-like strings cannot become accepted exchange outcomes."""
    row = _row("order_acknowledgement", "entry", True, "filled")
    row["payload"]["accepted"] = "true"

    with pytest.raises(ValueError, match="accepted must be boolean"):
        build_order_submission_outcomes({"BTC": [row]}, scope="current_run")


def test_execution_summary_projects_current_and_compatible_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live audit exposes acknowledgements from both evidence windows."""
    prior = _row("order_acknowledgement", "entry", True, "filled")
    current = _row("stop_order", "protective_stop", True, "resting")
    journals = {
        "BTC": {
            "summary": {
                "closed_trades": 0,
                "open_lifecycles": 0,
                "fees_usd": 0.0,
                "funding_usd": 0.0,
            },
            "trades": [],
        }
    }
    monkeypatch.setattr(
        cohort_live_audit_execution,
        "build_friction_parity",
        lambda identity, fills: {},
    )
    monkeypatch.setattr(
        cohort_live_audit_execution,
        "open_position_summary",
        lambda cohort, values: [],
    )
    monkeypatch.setattr(
        cohort_live_audit_execution,
        "fill_payloads",
        lambda symbol, rows: [],
    )

    execution = execution_summary(
        [],
        {"BTC": [current]},
        {"BTC": [prior, current]},
        journals,
        {"payload": {}},
    )

    assert execution["current_run_submission_outcomes"]["outcomes"] == 1
    assert execution["submission_outcomes"]["outcomes"] == 2


def _row(
    event_type: str,
    operation: str,
    accepted: bool,
    status: str,
    *,
    error: str | None = None,
    oid: int | None = 101,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": "run-v58",
        "payload": {
            "operation": operation,
            "accepted": accepted,
            "oid": oid,
            "status": status,
            "error": error,
        },
    }
