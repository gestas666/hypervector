"""Canonical identity selection for append-only report-only observer runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = Mapping[str, object]
_IDENTITY_FIELDS = (
    "profile_id",
    "profile_fingerprint",
    "run_fingerprint",
    "run_id",
    "execution_mode",
    "effective_mode",
    "live_armed",
    "execution_authority",
)


def canonical_observer_run(
    records: Sequence[Record], run_id: str
) -> tuple[tuple[Record, ...], Record]:
    """Return one run with equivalent identity restatements deduplicated."""
    selected = tuple(row for row in records if row.get("run_id") == run_id)
    identities = tuple(
        row for row in selected if row.get("event_type") == "configuration_identity"
    )
    if not identities:
        raise ValueError(f"run {run_id} requires a configuration identity")
    identity = identities[0]
    if any(not _same_contract(row, identity) for row in identities[1:]):
        raise ValueError(f"run {run_id} has conflicting configuration identity")
    deduplicated = tuple(
        row
        for row in selected
        if row is identity or row.get("event_type") != "configuration_identity"
    )
    return deduplicated, identity


def canonical_observer_identities(records: Sequence[Record]) -> tuple[Record, ...]:
    """Return one canonical identity per run in first-observed order."""
    run_ids: list[str] = []
    for row in records:
        if row.get("event_type") != "configuration_identity":
            continue
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("observer configuration run ID is invalid")
        if run_id not in run_ids:
            run_ids.append(run_id)
    return tuple(canonical_observer_run(records, run_id)[1] for run_id in run_ids)


def _same_contract(left: Record, right: Record) -> bool:
    if any(left.get(field) != right.get(field) for field in _IDENTITY_FIELDS):
        return False
    return _execution_payload(left) == _execution_payload(right)


def _execution_payload(row: Record) -> dict[str, object]:
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("observer configuration payload must be an object")
    return {key: value for key, value in payload.items() if key != "strategy_evidence"}
