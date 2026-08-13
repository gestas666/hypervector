"""Run provenance for report-only cohort opportunity matrices."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime


def opportunity_matrix_provenance(
    matrix: Mapping[str, object],
    checkpoint_run: Mapping[str, object],
) -> dict[str, object]:
    """Relate one research matrix source to the selected checkpoint run."""
    checkpoint_run_id = _required_text(
        checkpoint_run.get("run_id"), "checkpoint run_id"
    )
    checkpoint_first = _required_text(
        checkpoint_run.get("first_observed_at_utc"),
        "checkpoint first_observed_at_utc",
    )
    evidence_value = matrix.get("evidence")
    evidence = evidence_value if isinstance(evidence_value, Mapping) else {}
    evidence_run_id = _optional_text(evidence.get("run_id"))
    evidence_config = _optional_text(evidence.get("config"))
    matrix_updated = _optional_text(matrix.get("runtime_updated_at_utc"))
    return {
        "relationship": _matrix_run_relationship(
            checkpoint_run_id,
            checkpoint_first,
            evidence_run_id,
            matrix_updated,
        ),
        "checkpoint_run_id": checkpoint_run_id,
        "checkpoint_first_observed_at_utc": checkpoint_first,
        "evidence_run_id": evidence_run_id,
        "evidence_config_path": evidence_config,
        "matrix_updated_at_utc": matrix_updated,
    }


def _matrix_run_relationship(
    checkpoint_run_id: str,
    checkpoint_first: str,
    evidence_run_id: str | None,
    matrix_updated: str | None,
) -> str:
    if evidence_run_id is None:
        return "unattributed"
    if evidence_run_id == checkpoint_run_id:
        return "current_run"
    if matrix_updated is None:
        return "different_run"
    try:
        if datetime.fromisoformat(matrix_updated) < datetime.fromisoformat(
            checkpoint_first
        ):
            return "historical_prior_run"
    except ValueError:
        return "different_run"
    return "different_run"


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
