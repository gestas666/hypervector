"""Contracts for durable continuous-improvement hypothesis states."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_hypothesis_ledger import merge_hypothesis_ledger


def test_closed_decision_is_retained_beside_current_experiment() -> None:
    active = [_active("route|BTC", "collect_live", "current-live")]
    historical = [
        _decision(
            "old-relaxation",
            "route|BTC",
            "relax_entry_gate",
            "rejected",
            reopen_condition="new causal mechanism evidence",
        )
    ]

    ledger = merge_hypothesis_ledger(active, historical)

    assert [row["hypothesis_id"] for row in ledger] == [
        "current-live",
        "old-relaxation",
    ]
    assert ledger[0]["status"] == "being_tested"
    assert ledger[1] == {
        "hypothesis_id": "old-relaxation",
        "route": "route|BTC",
        "status": "rejected",
        "experiment": "relax_entry_gate",
        "decision_reason": "measured evidence resolved the idea",
        "decision_source": "decision.json",
        "reopen_condition": "new causal mechanism evidence",
        "superseded_by": None,
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def test_current_experiment_cannot_reopen_a_closed_route_experiment() -> None:
    active = [_active("route|BTC", "relax_entry_gate", "current-renamed")]
    historical = [
        _decision(
            "old-relaxation",
            "route|BTC",
            "relax_entry_gate",
            "rejected",
            reopen_condition="new causal mechanism evidence",
        )
    ]

    with pytest.raises(ValueError, match="reopens a closed hypothesis"):
        merge_hypothesis_ledger(active, historical)


def test_rejected_or_deferred_decision_requires_reopen_condition() -> None:
    decision = _decision(
        "old-relaxation",
        "route|BTC",
        "relax_entry_gate",
        "rejected",
        reopen_condition="new evidence",
    )
    decision.pop("reopen_condition")

    with pytest.raises(ValueError, match="reopen condition"):
        merge_hypothesis_ledger([], [decision])


def test_superseded_decision_must_name_a_known_successor() -> None:
    active = [_active("route|BTC", "new_mechanism", "current-new")]
    decision = _decision(
        "old-mechanism",
        "route|BTC",
        "old_mechanism",
        "superseded",
        superseded_by="missing-successor",
    )

    with pytest.raises(ValueError, match="known successor"):
        merge_hypothesis_ledger(active, [decision])


def test_superseded_decision_may_name_a_closed_successor() -> None:
    """A completed correction may supersede an older closed decision."""
    prior = _decision(
        "old-screen",
        "screen|XYZ",
        "stale_window",
        "superseded",
        superseded_by="corrected-screen",
    )
    corrected = _decision(
        "corrected-screen",
        "screen|XYZ",
        "corrected_window",
        "accepted",
    )

    ledger = merge_hypothesis_ledger([], [prior, corrected])

    assert [row["hypothesis_id"] for row in ledger] == [
        "old-screen",
        "corrected-screen",
    ]


def test_closed_successor_chain_must_not_cycle() -> None:
    """Closed supersession history must remain a directed acyclic chain."""
    first = _decision(
        "first",
        "screen|XYZ",
        "first_window",
        "superseded",
        superseded_by="second",
    )
    second = _decision(
        "second",
        "screen|XYZ",
        "second_window",
        "superseded",
        superseded_by="first",
    )

    with pytest.raises(ValueError, match="successor cycle"):
        merge_hypothesis_ledger([], [first, second])


def test_duplicate_hypothesis_identity_fails_closed() -> None:
    historical = [
        _decision(
            "duplicate",
            "route|BTC",
            "old_a",
            "rejected",
            reopen_condition="new evidence",
        ),
        _decision(
            "duplicate",
            "route|ETH",
            "old_b",
            "deferred",
            reopen_condition="more live observations",
        ),
    ]

    with pytest.raises(ValueError, match="duplicate hypothesis identity"):
        merge_hypothesis_ledger([], historical)


def test_closed_decision_retains_exact_live_diagnostic_blockers() -> None:
    """A closed one-blocker experiment must remain machine-reconcilable."""
    decision = _decision(
        "closed-gate",
        "route|BTC",
        "remove_gate",
        "rejected",
        reopen_condition="a distinct preregistered window",
    )
    decision["closed_live_diagnostic_blockers"] = ["gate_absent"]

    row = merge_hypothesis_ledger([], [decision])[0]

    assert row["closed_live_diagnostic_blockers"] == ["gate_absent"]


def _active(route: str, experiment: str, hypothesis_id: str) -> dict[str, object]:
    return {
        "hypothesis_id": hypothesis_id,
        "route": route,
        "status": "being_tested",
        "experiment": experiment,
        "execution_effect": "report_only",
    }


def _decision(
    hypothesis_id: str,
    route: str,
    experiment: str,
    status: str,
    *,
    reopen_condition: str | None = None,
    superseded_by: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "hypothesis_id": hypothesis_id,
        "route": route,
        "experiment": experiment,
        "status": status,
        "decision_reason": "measured evidence resolved the idea",
        "decision_source": "decision.json",
    }
    if reopen_condition is not None:
        row["reopen_condition"] = reopen_condition
    if superseded_by is not None:
        row["superseded_by"] = superseded_by
    return row
