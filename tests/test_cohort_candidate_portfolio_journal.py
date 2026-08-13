"""Tests for causal portfolio compatibility of report-only signal attempts."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_candidate_portfolio_journal import (
    CandidatePortfolioJournalSpec,
    build_candidate_portfolio_journal,
)


RUN_ID = "live-run-1"
SOURCE = "canonical_hype"
CANDIDATE = "relaxed_hype"


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    run_id: str = RUN_ID,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "run_id": run_id,
        "observed_at_utc": f"2026-08-04T16:52:{sequence:02d}+00:00",
        "payload": payload,
    }


def _snapshot(
    sequence: int,
    *,
    hype_state: str = "FLAT",
    open_positions: int = 1,
) -> dict[str, object]:
    return _event(
        sequence,
        "cohort_snapshot",
        {
            "open_position_count": open_positions,
            "assets": [
                {
                    "symbol": "HYPE",
                    "state": hype_state,
                    "position_side": "long" if hype_state == "OPEN" else None,
                    "execution_plan": (
                        {"strategy_id": "other_hype"} if hype_state == "OPEN" else None
                    ),
                }
            ],
        },
    )


def _routing(
    sequence: int,
    *,
    decision_time_ms: int = 1_000,
    actions: list[dict[str, object]] | None = None,
    withheld: list[dict[str, object]] | None = None,
    run_id: str = RUN_ID,
) -> dict[str, object]:
    return _event(
        sequence,
        "intent_routing",
        {
            "evaluations": [
                {
                    "strategy_id": SOURCE,
                    "symbol": "HYPE",
                    "decision_time_ms": decision_time_ms,
                }
            ],
            "actions": actions or [],
            "withheld": withheld or [],
        },
        run_id=run_id,
    )


def _replay(
    *,
    status: str = "resolved",
    run_id: str = RUN_ID,
) -> dict[str, object]:
    attempt = {
        "source_run_id": run_id,
        "strategy_id": SOURCE,
        "symbol": "HYPE",
        "side": "long",
        "decision_time_ms": 1_000,
        "available_time_ms": 2_000,
        "status": status,
    }
    execution = attempt | {
        "entry_time_ms": 2_100,
        "exit_time_ms": 62_100,
        "net_return_bps": 12.5,
        "simulated_net_pnl_usd": 0.03125,
    }
    return {
        "schema_version": 1,
        "mode": "one_blocker_execution_feasibility",
        "attempts": [attempt],
        "executions": [execution] if status == "resolved" else [],
    }


def _spec() -> CandidatePortfolioJournalSpec:
    return CandidatePortfolioJournalSpec(
        source_strategy_id=SOURCE,
        candidate_strategy_id=CANDIDATE,
        symbol="HYPE",
        maximum_positions=4,
    )


def test_flat_attempt_is_deployable_and_attaches_simulated_outcome() -> None:
    journal = build_candidate_portfolio_journal(
        [_snapshot(1), _routing(2)], _replay(), spec=_spec()
    )

    assert journal["summary"] == {
        "attempts": 1,
        "deployable": 1,
        "deployable_resolved": 1,
        "deployable_wins": 1,
        "deployable_losses": 0,
        "deployable_total_net_return_bps": 12.5,
        "deployable_profit_factor": None,
        "deployable_largest_abs_contribution_fraction": 1.0,
        "existing_symbol_position": 0,
        "portfolio_capacity": 0,
        "same_cycle_symbol_action": 0,
        "portfolio_state_unavailable": 0,
        "resolved": 1,
        "pending": 0,
    }
    row = journal["latest_attempts"][0]
    assert row["portfolio_classification"] == "deployable_flat_entry"
    assert row["open_position_count"] == 1
    assert row["available_position_slots"] == 3
    assert row["net_return_bps"] == 12.5
    assert row["simulated_net_pnl_usd"] == 0.03125


def test_conflicting_winner_does_not_rescue_deployable_performance() -> None:
    first = _replay()
    second_attempt = {
        "source_run_id": RUN_ID,
        "strategy_id": SOURCE,
        "symbol": "HYPE",
        "side": "long",
        "decision_time_ms": 3_000,
        "available_time_ms": 4_000,
        "status": "resolved",
    }
    second_execution = second_attempt | {
        "entry_time_ms": 4_100,
        "exit_time_ms": 64_100,
        "net_return_bps": 50.0,
        "simulated_net_pnl_usd": 0.125,
    }
    replay = {
        **first,
        "attempts": [*first["attempts"], second_attempt],
        "executions": [*first["executions"], second_execution],
    }
    records = [
        _snapshot(1),
        _routing(2),
        _snapshot(3, hype_state="OPEN"),
        _routing(4, decision_time_ms=3_000),
    ]

    journal = build_candidate_portfolio_journal(records, replay, spec=_spec())

    summary = journal["summary"]
    assert summary["resolved"] == 2
    assert summary["deployable_resolved"] == 1
    assert summary["deployable_wins"] == 1
    assert summary["deployable_total_net_return_bps"] == 12.5


@pytest.mark.parametrize(
    ("snapshot", "actions", "expected"),
    [
        (_snapshot(1, hype_state="OPEN"), [], "existing_symbol_position"),
        (_snapshot(1, open_positions=4), [], "portfolio_capacity"),
        (
            _snapshot(1),
            [{"strategy_id": "other_hype", "symbol": "HYPE"}],
            "same_cycle_symbol_action",
        ),
    ],
)
def test_attempt_conflicts_are_classified(
    snapshot: dict[str, object],
    actions: list[dict[str, object]],
    expected: str,
) -> None:
    journal = build_candidate_portfolio_journal(
        [snapshot, _routing(2, actions=actions)],
        _replay(status="exit_missing"),
        spec=_spec(),
    )

    assert journal["latest_attempts"][0]["portfolio_classification"] == expected


def test_withheld_symbol_route_is_reported_without_claiming_deployability() -> None:
    withheld = [
        {
            "strategy_id": "other_hype",
            "symbol": "HYPE",
            "reason": "lower_priority",
        }
    ]
    journal = build_candidate_portfolio_journal(
        [_snapshot(1), _routing(2, withheld=withheld)],
        _replay(status="exit_missing"),
        spec=_spec(),
    )

    row = journal["latest_attempts"][0]
    assert row["portfolio_classification"] == "deployable_flat_entry"
    assert row["same_cycle_symbol_withheld"] == [
        {
            "strategy_id": "other_hype",
            "reason": "lower_priority",
        }
    ]


def test_attempt_requires_prior_snapshot_from_the_same_run() -> None:
    records = [
        _snapshot(1),
        _routing(2, run_id="live-run-2"),
    ]

    with pytest.raises(ValueError, match="routing publication unavailable"):
        build_candidate_portfolio_journal(records, _replay(), spec=_spec())

    records = [
        _snapshot(1, open_positions=0),
        _routing(2),
    ]
    records[0]["run_id"] = "different-run"
    journal = build_candidate_portfolio_journal(records, _replay(), spec=_spec())
    assert (
        journal["latest_attempts"][0]["portfolio_classification"]
        == "portfolio_state_unavailable"
    )


def test_duplicate_or_post_routing_snapshot_fails_closed() -> None:
    duplicate = [_snapshot(1), _routing(2), _routing(3)]
    with pytest.raises(ValueError, match="ambiguous routing publication"):
        build_candidate_portfolio_journal(duplicate, _replay(), spec=_spec())

    journal = build_candidate_portfolio_journal(
        [_routing(1), _snapshot(2, open_positions=0)], _replay(), spec=_spec()
    )
    assert (
        journal["latest_attempts"][0]["portfolio_classification"]
        == "portfolio_state_unavailable"
    )


def test_contract_is_explicitly_non_authoritative_and_non_additive() -> None:
    journal = build_candidate_portfolio_journal(
        [_snapshot(1), _routing(2)], _replay(), spec=_spec()
    )

    assert journal["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "source_strategy_id": SOURCE,
        "candidate_strategy_id": CANDIDATE,
        "symbol": "HYPE",
        "position_policy": "flat_entry_only",
        "maximum_positions": 4,
        "portfolio_pnl_claimed": False,
        "simulated_outcomes_are_non_additive": True,
    }
