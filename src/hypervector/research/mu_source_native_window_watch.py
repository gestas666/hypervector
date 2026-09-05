"""Fail-closed status for the independent prospective MU lifecycle window."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = dict[str, object]

_SCHEMA = "v57_mu_source_native_independent_window_preregistration_v1"
_EVENT = "mu_hip3_breakout_shadow_decision"
_SIDES = ("long", "short")
_INTERVAL_MS = 900_000


def build_mu_source_native_window_status(
    preregistration: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
    *,
    observed_at_ms: int,
) -> Record:
    """Return an authority-none readiness status from a bounded journal prefix."""
    _require_safe_preregistration(preregistration)
    observed_at = _positive_integer(observed_at_ms, "observed at")
    independence = _mapping(
        preregistration.get("independence_contract"), "independence contract"
    )
    strategy = _mapping(
        preregistration.get("frozen_strategy_contract"), "strategy contract"
    )
    stopping = _mapping(preregistration.get("stopping_rule"), "stopping rule")
    start_ms = _positive_integer(independence.get("decision_start_ms"), "start")
    thresholds = _thresholds(stopping)
    included = _included_decisions(rows, strategy, start_ms, observed_at)
    coverage = _decision_coverage(included, strategy, start_ms, observed_at)
    side_counts = {
        side: sum(
            decision["side"] == side for decision in included if decision["eligible"]
        )
        for side in _SIDES
    }
    eligible = sum(side_counts.values())
    due = (
        coverage["complete"] is True
        and eligible >= thresholds[0]
        and min(side_counts.values()) >= thresholds[1]
    )
    deadline_reached = observed_at >= thresholds[2]
    return _status(
        observed_at,
        start_ms,
        included,
        side_counts,
        thresholds,
        coverage,
        due,
        deadline_reached,
    )


def _decision_coverage(
    included: Sequence[Mapping[str, object]],
    strategy: Mapping[str, object],
    start_ms: int,
    observed_at_ms: int,
) -> Record:
    grace_ms = _positive_integer(
        strategy.get("maximum_book_lateness_ms"), "maximum book lateness"
    )
    latest_due_ms = (observed_at_ms - grace_ms) // _INTERVAL_MS * _INTERVAL_MS
    latest_observed_ms = (
        start_ms - _INTERVAL_MS
        if not included
        else int(included[-1]["decision_time_ms"])
    )
    latest_expected_ms = max(latest_due_ms, latest_observed_ms)
    expected = range(start_ms, latest_expected_ms + _INTERVAL_MS, _INTERVAL_MS)
    observed = {int(decision["decision_time_ms"]) for decision in included}
    missing = [decision_ms for decision_ms in expected if decision_ms not in observed]
    expected_count = max(0, (latest_expected_ms - start_ms) // _INTERVAL_MS + 1)
    return {
        "expected_decisions": expected_count,
        "observed_decisions": len(included),
        "complete": not missing,
        "latest_expected_decision_time_ms": (
            latest_expected_ms if expected_count else None
        ),
        "missing_decision_time_ms": missing,
        "grace_ms": grace_ms,
    }


def _included_decisions(
    rows: Sequence[Mapping[str, object]],
    strategy: Mapping[str, object],
    start_ms: int,
    observed_at_ms: int,
) -> list[Record]:
    included: list[Record] = []
    seen: set[int] = set()
    for row in rows:
        decision = _mapping(row.get("decision"), "decision")
        decision_ms = _positive_integer(
            decision.get("decision_time_ms"), "decision time"
        )
        if decision_ms < start_ms:
            continue
        if decision_ms > observed_at_ms:
            raise ValueError("MU independent decision exceeds observed-at boundary")
        _require_exact_decision(row, decision, strategy, observed_at_ms)
        if decision_ms in seen:
            raise ValueError(
                "MU independent journal contains duplicate decision boundary"
            )
        seen.add(decision_ms)
        included.append(dict(decision))
    return sorted(included, key=lambda decision: int(decision["decision_time_ms"]))


def _require_exact_decision(
    row: Mapping[str, object],
    decision: Mapping[str, object],
    strategy: Mapping[str, object],
    observed_at_ms: int,
) -> None:
    identity = ("symbol", "provider_id", "profile_id")
    if row.get("event_type") != _EVENT or any(
        decision.get(field) != strategy.get(field) for field in identity
    ):
        raise ValueError("MU independent decision identity is invalid")
    if decision.get("prospective") is not True:
        raise ValueError("MU independent included decision must be prospective")
    if decision.get("execution_authority") != "none":
        raise ValueError("MU independent decision has execution authority")
    observed = _positive_integer(decision.get("observed_at_ms"), "decision observation")
    if observed > observed_at_ms:
        raise ValueError("MU independent decision observation exceeds status boundary")
    eligible = decision.get("eligible")
    if not isinstance(eligible, bool):
        raise ValueError("MU independent decision eligibility must be boolean")
    side = decision.get("side")
    if (eligible and side not in _SIDES) or (not eligible and side is not None):
        raise ValueError("MU independent decision side is inconsistent")


def _thresholds(stopping: Mapping[str, object]) -> tuple[int, int, int]:
    total = _positive_integer(
        stopping.get("minimum_eligible_onsets_before_replay"), "onset minimum"
    )
    per_side = _positive_integer(
        stopping.get("minimum_eligible_onsets_per_side_before_replay"),
        "side onset minimum",
    )
    deadline = _positive_integer(stopping.get("time_limit_ms"), "deadline")
    if total < per_side * 2:
        raise ValueError("MU independent pooled minimum is below both-side minimum")
    return total, per_side, deadline


def _status(
    observed_at_ms: int,
    start_ms: int,
    included: Sequence[Mapping[str, object]],
    side_counts: Mapping[str, int],
    thresholds: tuple[int, int, int],
    coverage: Mapping[str, object],
    due: bool,
    deadline_reached: bool,
) -> Record:
    state = "lifecycle_replay_candidate_due" if due else "collecting_minimum_onsets"
    if deadline_reached and not due:
        state = "collection_deadline_reached"
    if coverage["complete"] is not True:
        state = "technical_coverage_gap"
    scenario = _empty_scenario()
    return {
        "schema_version": "mu_source_native_independent_window_status_v1",
        "symbol": "xyz:MU",
        "observed_at_ms": observed_at_ms,
        "decision_start_ms": start_ms,
        "included_decisions": len(included),
        "eligible_onsets": sum(side_counts.values()),
        "eligible_onsets_by_side": dict(side_counts),
        "last_decision_time_ms": None
        if not included
        else included[-1]["decision_time_ms"],
        "minimum_eligible_onsets_before_replay": thresholds[0],
        "minimum_eligible_onsets_per_side_before_replay": thresholds[1],
        "collection_deadline_ms": thresholds[2],
        "collection_deadline_reached": deadline_reached,
        "lifecycle_replay_candidate_due": due,
        "watch_state": (
            "WAITING_ELIGIBLE_ONSET"
            if coverage["complete"] is True
            else "TECHNICAL_COVERAGE_GAP"
        ),
        "collection_state": state,
        "decision_coverage": dict(coverage),
        "source": {
            "observed_decisions": len(included),
            "eligible_decisions": sum(side_counts.values()),
        },
        "nominal": {"summary": dict(scenario)},
        "stress": {"summary": dict(scenario)},
        "technical_assessment": {
            "all_observed_paths_resolved": False,
            "decision_schedule_complete": coverage["complete"],
            "live_change_supported": False,
        },
        "technical_note": (
            "Lifecycle completion and economics require the frozen replay; "
            "missing prospective decision boundaries make this window non-supportive."
        ),
        "report_only": True,
        "execution_authority": "none",
        "orders_supported": False,
        "signing_client_constructed": False,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }


def _empty_scenario() -> Record:
    return {
        "resolved": 0,
        "censored": 0,
        "modeled_net_usd_excluding_funding": 0.0,
    }


def _require_safe_preregistration(preregistration: Mapping[str, object]) -> None:
    safe = (
        preregistration.get("schema_version") == _SCHEMA
        and preregistration.get("status") == "prospective_collecting"
        and preregistration.get("execution_authority") == "none"
        and preregistration.get("automatic_live_change") is False
        and preregistration.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("MU independent preregistration authority is invalid")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"MU independent {label} must be an object")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"MU independent {label} must be a positive integer")
    return value
