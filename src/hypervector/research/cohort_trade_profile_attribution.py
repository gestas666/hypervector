"""Source-profile provenance for resolved cohort trade reflections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import text

Record = Mapping[str, object]


def attach_source_profile_fingerprints(
    trades: Sequence[Record],
    cohort_records: Sequence[Record],
) -> list[dict[str, object]]:
    """Attach the exact cohort profile fingerprint that authored each entry."""
    profiles = _profiles_by_run(cohort_records)
    output: list[dict[str, object]] = []
    for trade in trades:
        source_run = text(trade.get("source_run_id"), "trade source run")
        fingerprint = profiles.get(source_run)
        if fingerprint is None:
            raise ValueError(f"trade source run {source_run} lacks profile provenance")
        output.append({**trade, "source_profile_fingerprint": fingerprint})
    return output


def _profiles_by_run(records: Sequence[Record]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for row in records:
        run_id = text(row.get("run_id"), "cohort run id")
        fingerprint = text(row.get("profile_fingerprint"), "profile fingerprint")
        prior = profiles.setdefault(run_id, fingerprint)
        if prior != fingerprint:
            raise ValueError(f"cohort run {run_id} has conflicting profile provenance")
    return profiles
