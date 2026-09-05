"""Source-bound prospective experiment evidence for the improvement digest."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path

Record = Mapping[str, object]

_ROUTE = "range_onset_bidirectional_v1|SOL"
_EXPERIMENT = "collect_route_native_one_blocker_shadow"
_MODE = "v51_sol_route_native_one_blocker_shadow"
_CANDIDATE = "sol_hourly_cross_relaxed_route_native_shadow_v1"


@dataclass(frozen=True)
class ObserverIdentity:
    """Exact live-run identity required for prospective observer evidence."""

    run_id: str
    profile_id: str
    profile_fingerprint: str

    def __post_init__(self) -> None:
        """Reject incomplete or non-SHA profile identity."""
        _text(self.run_id, "observer run identity")
        _text(self.profile_id, "observer profile identity")
        _digest(self.profile_fingerprint, "observer profile fingerprint")


@dataclass(frozen=True)
class ProspectiveExperimentEvidence:
    """Validated observer summary and exact source-file evidence."""

    identity: ObserverIdentity
    summary: dict[str, object]
    source: dict[str, object] | None


def load_sol_route_native_observer(
    path: Path,
    identity: ObserverIdentity,
    *,
    observed_at: datetime,
    maximum_age_seconds: float,
) -> ProspectiveExperimentEvidence:
    """Load one exact SOL observer or return an explicit unavailable state."""
    _validate_freshness_inputs(observed_at, maximum_age_seconds)
    if not path.exists():
        return ProspectiveExperimentEvidence(
            identity,
            _unavailable_summary("unavailable_missing", None, None),
            None,
        )
    raw = path.read_bytes()
    payload = _mapping(json.loads(raw), "SOL prospective observer")
    source_run_id = _validate_observer(payload, identity)
    observer_time = _timestamp(payload.get("observed_at_utc"), "observer time")
    age = (observed_at.astimezone(UTC) - observer_time).total_seconds()
    if age < 0.0:
        raise ValueError("SOL prospective observer time is in the future")
    source = _source_evidence(path, raw)
    status = _text(payload.get("status"), "observer status")
    if source_run_id != identity.run_id:
        summary = _unavailable_summary(
            "unavailable_previous_run", status, observer_time.isoformat()
        )
        summary["source_run_id"] = source_run_id
        return ProspectiveExperimentEvidence(identity, summary, source)
    if age > maximum_age_seconds:
        summary = _unavailable_summary(
            "unavailable_stale", status, observer_time.isoformat()
        )
    else:
        summary = _available_summary(payload, observer_time, status)
    return ProspectiveExperimentEvidence(identity, summary, source)


def attach_prospective_experiment_evidence(
    digest: Record,
    evidence: ProspectiveExperimentEvidence,
) -> dict[str, object]:
    """Attach observer maturity without converting it into realized paths."""
    _validate_digest_identity(digest, evidence.identity)
    queue = _records(digest.get("experiment_queue"), "experiment queue")
    matches = [row for row in queue if row.get("route") == _ROUTE]
    if len(matches) != 1:
        raise ValueError("SOL prospective observer requires one exact queue route")
    if matches[0].get("next_experiment") != _EXPERIMENT:
        raise ValueError("SOL prospective observer experiment identity mismatch")
    updated = [_attach_row(row, evidence) for row in queue]
    return {
        **dict(digest),
        "experiment_queue": updated,
        "prospective_experiment_evidence": [dict(evidence.summary)],
    }


def _attach_row(
    row: Record, evidence: ProspectiveExperimentEvidence
) -> dict[str, object]:
    if row.get("route") != _ROUTE:
        return dict(row)
    output = {**dict(row), "prospective_observation": dict(evidence.summary)}
    if evidence.source is not None:
        paths = _text_list(row.get("supporting_evidence", []), "supporting evidence")
        source_path = _text(evidence.source.get("path"), "observer source path")
        output["supporting_evidence"] = [*paths, source_path]
    return output


def _available_summary(
    payload: Record, observer_time: datetime, observer_status: str
) -> dict[str, object]:
    coverage = _mapping(payload.get("coverage"), "observer coverage")
    attempts = _records(payload.get("attempts"), "observer attempts")
    executions = _records(payload.get("executions"), "observer executions")
    raw_counts = _validated_counts(coverage, attempts, executions)
    expected_status = _expected_status(raw_counts, attempts)
    if observer_status != expected_status:
        raise ValueError("SOL prospective observer status does not reconcile")
    counts = {
        **raw_counts,
        **_portfolio_counts(payload, raw_counts),
    }
    return {
        "route": _ROUTE,
        "experiment": _EXPERIMENT,
        "availability_status": "available",
        "observer_status": observer_status,
        "observed_at_utc": observer_time.isoformat(),
        "capture_start_utc": _timestamp(
            payload.get("capture_start_utc"), "observer capture start"
        ).isoformat(),
        **counts,
        "economic_verdict": (
            "available_resolved_lifecycles"
            if counts["resolved_lifecycles"]
            else "unavailable_until_resolved_lifecycle"
        ),
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _portfolio_counts(payload: Record, raw: Record) -> dict[str, object]:
    """Return deployable maturity from the causal shared-portfolio journal."""
    journal = _mapping(payload.get("portfolio_journal"), "portfolio journal")
    if journal.get("schema_version") != 1 or journal.get("mode") != (
        "candidate_portfolio_compatibility_journal"
    ):
        raise ValueError("SOL prospective portfolio journal is invalid")
    _validate_portfolio_contract(
        _mapping(journal.get("contract"), "portfolio contract")
    )
    summary = _mapping(journal.get("summary"), "portfolio summary")
    attempted = _count(raw.get("attempts"), "raw attempt count")
    resolved = _count(raw.get("resolved_lifecycles"), "raw resolved count")
    if _count(summary.get("attempts"), "portfolio attempts") != attempted:
        raise ValueError("SOL portfolio attempt count does not reconcile")
    if _count(summary.get("resolved"), "portfolio resolved") != resolved:
        raise ValueError("SOL portfolio resolved count does not reconcile")
    return _deployable_counts(summary, raw, attempted)


def _validate_portfolio_contract(contract: Record) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "source_strategy_id": _ROUTE.split("|", 1)[0],
        "candidate_strategy_id": _CANDIDATE,
        "symbol": "SOL",
        "position_policy": "flat_entry_only",
        "portfolio_pnl_claimed": False,
        "simulated_outcomes_are_non_additive": True,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("SOL prospective portfolio contract is invalid")
    _count(contract.get("maximum_positions"), "portfolio maximum positions")


def _deployable_counts(
    summary: Record, raw: Record, attempted: int
) -> dict[str, object]:
    deployable = _count(summary.get("deployable"), "deployable attempts")
    classes = {
        "existing_symbol_position_attempts": "existing_symbol_position",
        "portfolio_capacity_attempts": "portfolio_capacity",
        "same_cycle_symbol_action_attempts": "same_cycle_symbol_action",
        "portfolio_state_unavailable_attempts": "portfolio_state_unavailable",
    }
    excluded = {
        output: _count(summary.get(source), output)
        for output, source in classes.items()
    }
    if deployable + sum(excluded.values()) != attempted:
        raise ValueError("SOL portfolio classifications do not reconcile")
    return {
        "deployable_attempts": deployable,
        "resolved_lifecycles": _count(
            summary.get("deployable_resolved"), "deployable resolved"
        ),
        "active_pending_lifecycles": _count(
            summary.get("deployable_active_pending"), "deployable pending"
        ),
        "technically_unresolved_attempts": _count(
            summary.get("deployable_technically_unresolved"),
            "deployable technically unresolved",
        ),
        "raw_resolved_lifecycles": raw["resolved_lifecycles"],
        "raw_active_pending_lifecycles": raw["active_pending_lifecycles"],
        "portfolio_excluded_attempts": attempted - deployable,
        **excluded,
        "observed_sides": _sides(summary.get("deployable_observed_sides")),
    }


def _sides(value: object) -> list[str]:
    sides = value
    if not isinstance(sides, list) or any(
        side not in {"long", "short"} for side in sides
    ):
        raise ValueError("deployable observed sides are invalid")
    if sides != sorted(set(sides)):
        raise ValueError("deployable observed sides must be unique and ordered")
    return list(sides)


def _validated_counts(
    coverage: Record,
    attempts: Sequence[Record],
    executions: Sequence[Record],
) -> dict[str, int]:
    attempted = _count(coverage.get("attempts"), "attempt count")
    resolved = _count(coverage.get("resolved_executions"), "resolved count")
    unresolved = _count(coverage.get("pending_or_unresolved"), "unresolved count")
    if attempted != len(attempts):
        raise ValueError("SOL prospective observer attempt count does not reconcile")
    if resolved != len(executions):
        raise ValueError(
            "SOL prospective observer resolved lifecycle count does not reconcile"
        )
    if unresolved != attempted - resolved:
        raise ValueError("SOL prospective observer unresolved count does not reconcile")
    resolved_attempts = sum(row.get("status") == "resolved" for row in attempts)
    if resolved_attempts != resolved:
        raise ValueError("SOL prospective observer resolved attempts do not reconcile")
    active = sum(row.get("status") == "exit_pending" for row in attempts)
    return {
        "raw_exact_evaluations": _count(
            coverage.get("raw_exact_evaluations"), "raw exact evaluations"
        ),
        "independent_onsets": _count(
            coverage.get("exact_candidates"), "independent onsets"
        ),
        "attempts": attempted,
        "resolved_lifecycles": resolved,
        "active_pending_lifecycles": active,
        "technically_unresolved_attempts": unresolved - active,
    }


def _expected_status(counts: Record, attempts: Sequence[Record]) -> str:
    if _count(counts.get("independent_onsets"), "independent onsets") == 0:
        return "waiting_future_exact_candidate"
    if _count(counts.get("resolved_lifecycles"), "resolved lifecycles") > 0:
        return "resolved_evidence_available"
    if any(row.get("status") == "exit_pending" for row in attempts):
        return "candidate_lifecycle_pending"
    return "candidate_technically_unresolved"


def _validate_observer(payload: Record, identity: ObserverIdentity) -> str:
    """Validate observer safety/profile identity and return its source run."""
    if payload.get("schema_version") != 1 or payload.get("mode") != _MODE:
        raise ValueError("SOL prospective observer schema or mode is invalid")
    contract = _mapping(payload.get("contract"), "observer contract")
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("SOL prospective observer contract is invalid")
    source_run_id = _validate_observer_identity(contract, identity)
    execution = _mapping(contract.get("execution"), "observer execution contract")
    if execution.get("strategy_id") != _ROUTE.split("|", 1)[0]:
        raise ValueError("SOL prospective observer strategy identity mismatch")
    if execution.get("symbol") != "SOL":
        raise ValueError("SOL prospective observer symbol identity mismatch")
    return source_run_id


def _validate_observer_identity(contract: Record, identity: ObserverIdentity) -> str:
    """Reject foreign profiles while allowing an explicit previous-run state."""
    source_run_id = _text(contract.get("source_run_id"), "observer source run")
    expected = {
        "source_profile_id": (identity.profile_id, "profile identity mismatch"),
        "source_profile_fingerprint": (
            identity.profile_fingerprint,
            "fingerprint mismatch",
        ),
    }
    for field, (value, message) in expected.items():
        if contract.get(field) != value:
            raise ValueError(f"SOL prospective observer {message}")
    return source_run_id


def _validate_digest_identity(digest: Record, identity: ObserverIdentity) -> None:
    source = _mapping(digest.get("source"), "digest source")
    values = (
        source.get("run_id"),
        source.get("profile_id"),
        source.get("profile_fingerprint"),
    )
    expected = (identity.run_id, identity.profile_id, identity.profile_fingerprint)
    if values != expected:
        raise ValueError("SOL prospective observer digest identity mismatch")


def _unavailable_summary(
    status: str, observer_status: str | None, observed_at_utc: str | None
) -> dict[str, object]:
    output: dict[str, object] = {
        "route": _ROUTE,
        "experiment": _EXPERIMENT,
        "availability_status": status,
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }
    if observer_status is not None:
        output["observer_status"] = observer_status
    if observed_at_utc is not None:
        output["observed_at_utc"] = observed_at_utc
    return output


def _source_evidence(path: Path, raw: bytes) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _validate_freshness_inputs(
    observed_at: datetime, maximum_age_seconds: float
) -> None:
    if observed_at.tzinfo is None:
        raise ValueError("observer comparison time must include a timezone")
    if not math.isfinite(maximum_age_seconds) or maximum_age_seconds <= 0.0:
        raise ValueError("observer maximum age must be positive and finite")


def _records(value: object, label: str) -> list[Record]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_mapping(row, f"{label} row") for row in value]


def _side(row: Record) -> str:
    side = _text(row.get("side"), "observer side")
    if side not in {"long", "short"}:
        raise ValueError("SOL prospective observer side is invalid")
    return side


def _timestamp(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _digest(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{label} must be lowercase SHA-256")
    return text


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return [_text(item, label) for item in value]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
