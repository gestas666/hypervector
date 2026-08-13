"""Bounded rolling analysis for the disarmed multi-asset observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_observer_audit import audit_cohort_observer_run
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

Record = Mapping[str, object]
_MODE = "multi_asset_bidirectional_observer_checkpoint"
_SOURCE_STALE_AFTER_SECONDS = 90.0


def build_observer_checkpoint(
    records: Sequence[Record],
    *,
    run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Build setup-process evidence without execution outcome fields."""
    audit = audit_cohort_observer_run(records, run_id=run_id)
    run = _mapping(audit.get("run"), "observer audit run")
    observed_at = generated_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "mode": _MODE,
        "generated_at_utc": _aware_isoformat(observed_at),
        "checkpoint_contract": _checkpoint_contract(),
        "observer": _observer_status(run, observed_at),
        "audit": audit,
    }


def publish_observer_checkpoint(
    decisions: Path,
    destination: Path,
    *,
    run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Snapshot a stable ledger prefix and replace one bounded checkpoint."""
    with snapshot_decision_ledger(
        decisions,
        allow_incomplete_tail=True,
    ) as (records, evidence):
        checkpoint = build_observer_checkpoint(
            records,
            run_id=run_id,
            generated_at=generated_at,
        )
    checkpoint["evidence"] = {"path": str(decisions), **evidence}
    write_atomic_json(destination, checkpoint)
    return checkpoint


def publish_unavailable_observer_checkpoint(
    destination: Path,
    technical_issue: str,
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Replace the latest document with an explicit unavailable state."""
    observed_at = generated_at or datetime.now(timezone.utc)
    checkpoint: dict[str, object] = {
        "schema_version": 1,
        "mode": _MODE,
        "generated_at_utc": _aware_isoformat(observed_at),
        "checkpoint_contract": _checkpoint_contract(),
        "status": {
            "state": "unavailable",
            "technical_issue": _text(technical_issue, "checkpoint technical issue"),
        },
    }
    write_atomic_json(destination, checkpoint)
    return checkpoint


def _checkpoint_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "final": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "performance_gate": False,
    }


def _observer_status(
    run: Mapping[str, object],
    generated_at: datetime,
) -> dict[str, object]:
    last_text = _text(run.get("last_observed_at_utc"), "observer last observation")
    last_observed = datetime.fromisoformat(last_text)
    _aware_isoformat(last_observed)
    source_age = max(0.0, (generated_at - last_observed).total_seconds())
    state = (
        "stale_source"
        if source_age > _SOURCE_STALE_AFTER_SECONDS
        else "setup_process_observation"
    )
    return {
        "state": state,
        "run_id": _text(run.get("run_id"), "observer run_id"),
        "last_observed_at_utc": last_text,
        "source_age_seconds": source_age,
        "stale_after_seconds": _SOURCE_STALE_AFTER_SECONDS,
    }


def _aware_isoformat(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checkpoint generation time must be timezone-aware")
    return value.isoformat()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
