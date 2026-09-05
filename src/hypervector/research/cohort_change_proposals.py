"""Fail-closed approval-ready change proposals for continuous research."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]

PROPOSAL_FIELDS = (
    "recommendation",
    "why_now",
    "evidence_reviewed",
    "observed_problem_or_opportunity",
    "applicable_market_regime",
    "alternatives_considered",
    "proposed_live_change",
    "expected_upside",
    "main_risks_and_failure_modes",
    "validation_completed",
    "validation_still_required",
    "success_metrics",
    "failure_or_rollback_triggers",
    "confidence_level",
    "explicit_approval_requested",
)
_METADATA_FIELDS = (
    "proposal_id",
    "approval_status",
    "execution_effect",
    "automatic_live_change",
)
_OPTIONAL_METADATA_FIELDS = ("approval_evidence",)
_ARRAY_FIELDS = frozenset(
    {
        "evidence_reviewed",
        "alternatives_considered",
        "main_risks_and_failure_modes",
        "validation_completed",
        "validation_still_required",
        "success_metrics",
        "failure_or_rollback_triggers",
    }
)


def normalize_change_proposals(value: object) -> list[dict[str, object]]:
    """Validate complete proposals while preserving human approval authority."""
    if not isinstance(value, list):
        raise ValueError("change proposals must be an array")
    proposals = [_normalize_proposal(item, index) for index, item in enumerate(value)]
    identifiers = [proposal["proposal_id"] for proposal in proposals]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("change proposal IDs must be unique")
    return proposals


def _normalize_proposal(value: object, index: int) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"change proposal {index} must be an object")
    required = set(PROPOSAL_FIELDS) | set(_METADATA_FIELDS)
    allowed = required | set(_OPTIONAL_METADATA_FIELDS)
    missing = sorted(required.difference(value))
    unknown = sorted(set(value).difference(allowed))
    if missing:
        raise ValueError(f"change proposal {index} missing required fields: {missing}")
    if unknown:
        raise ValueError(f"change proposal {index} has unknown fields: {unknown}")
    result = {field: _field(value, field, index) for field in required}
    if "approval_evidence" in value:
        result["approval_evidence"] = _field(value, "approval_evidence", index)
    _validate_authority(result, index)
    fields = (*_METADATA_FIELDS, *_OPTIONAL_METADATA_FIELDS, *PROPOSAL_FIELDS)
    return {field: result[field] for field in fields if field in result}


def _field(value: Record, field: str, index: int) -> object:
    if field in _ARRAY_FIELDS:
        return _text_array(value.get(field), f"change proposal {index} {field}")
    if field in {"explicit_approval_requested", "automatic_live_change"}:
        boolean = value.get(field)
        if not isinstance(boolean, bool):
            raise ValueError(f"change proposal {index} {field} must be boolean")
        return boolean
    return _text(value.get(field), f"change proposal {index} {field}")


def _validate_authority(proposal: Mapping[str, object], index: int) -> None:
    pending = (
        proposal.get("explicit_approval_requested") is True
        and proposal.get("approval_status") == "pending_human_approval"
        and proposal.get("execution_effect") == "proposal_only"
        and proposal.get("approval_evidence") is None
    )
    approved = (
        proposal.get("explicit_approval_requested") is False
        and proposal.get("approval_status") == "approved_waiting_flat_boundary"
        and proposal.get("execution_effect") == "approved_not_deployed"
        and isinstance(proposal.get("approval_evidence"), str)
    )
    active = (
        proposal.get("explicit_approval_requested") is False
        and proposal.get("approval_status")
        == "approved_activated_waiting_flat_boundary"
        and proposal.get("execution_effect") == "approved_active_transition_drain"
        and isinstance(proposal.get("approval_evidence"), str)
    )
    valid = (
        (pending or approved or active)
        and proposal.get("automatic_live_change") is False
        and proposal.get("confidence_level") in {"low", "medium", "high"}
    )
    if not valid:
        raise ValueError(f"change proposal {index} authority contract is invalid")


def _text_array(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty text array")
    return [_text(item, label) for item in value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
