"""Shared armed-run selection for report-only cohort research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    is_armed_live,
    payload,
    run_id,
)

Record = Mapping[str, object]
_STRATEGY_NAME = "multi_asset_bidirectional_cohort"


def select_armed_live_run(
    records: Sequence[Record], requested: str | None = None
) -> tuple[tuple[Record, ...], Record]:
    """Return one explicitly armed cohort run and its sole identity record."""
    identities = event_rows(records, "configuration_identity")
    candidates = [row for row in identities if is_armed_live(row)]
    chosen = requested or (run_id(candidates[-1]) if candidates else None)
    if chosen is None:
        raise ValueError("cohort research found no armed live run")
    selected = tuple(row for row in records if row.get("run_id") == chosen)
    if not selected or not all(is_armed_live(row) for row in selected):
        raise ValueError(f"run {chosen} is not an armed live run")
    run_identities = event_rows(selected, "configuration_identity")
    if len(run_identities) != 1:
        raise ValueError(f"run {chosen} requires exactly one configuration identity")
    identity = run_identities[0]
    if payload(identity).get("strategy_name") != _STRATEGY_NAME:
        raise ValueError(f"run {chosen} has unexpected cohort strategy identity")
    return selected, identity


def select_compatible_armed_live_runs(
    records: Sequence[Record],
    *,
    profile_fingerprint: str,
    required_run_id: str | None = None,
) -> tuple[tuple[Record, ...], tuple[Record, ...]]:
    """Return every armed restart with the exact requested cohort profile."""
    if not profile_fingerprint.strip():
        raise ValueError("compatible run profile fingerprint must be non-empty")
    compatible: list[Record] = []
    seen: set[str] = set()
    for identity in event_rows(records, "configuration_identity"):
        values = payload(identity)
        if not is_armed_live(identity) or not _matches_profile(
            identity, values, profile_fingerprint
        ):
            continue
        identity_run_id = run_id(identity)
        if identity_run_id in seen:
            raise ValueError(f"run {identity_run_id} has duplicate identities")
        seen.add(identity_run_id)
        compatible.append(identity)
    if required_run_id is not None and required_run_id not in seen:
        raise ValueError("required armed run does not match the requested profile")
    if not compatible:
        raise ValueError("cohort research found no compatible armed live run")
    selected = tuple(row for row in records if row.get("run_id") in seen)
    if not selected or not all(is_armed_live(row) for row in selected):
        raise ValueError("compatible run history contains non-armed evidence")
    return selected, tuple(compatible)


def _matches_profile(
    identity: Record, values: Record, profile_fingerprint: str
) -> bool:
    return (
        identity.get("profile_fingerprint") == profile_fingerprint
        and values.get("profile_fingerprint") == profile_fingerprint
        and values.get("strategy_name") == _STRATEGY_NAME
    )
