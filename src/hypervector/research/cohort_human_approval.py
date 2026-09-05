"""Human approval projection for report-only cohort improvement evidence."""

from __future__ import annotations

from collections.abc import Mapping

Record = Mapping[str, object]

_STATUS = "standing_preapproved_for_validated_required_changes"
_TEXT_FIELDS = ("approval_status", "approval_evidence")
_ARRAY_FIELDS = ("approved_scope", "excluded_scope")
_BOOLEAN_FIELDS = (
    "agent_may_apply_after_validation",
    "agent_reapproval_required",
    "automatic_live_change",
    "live_arming_flags_required",
    "validation_required",
    "rollback_required",
)
_EXPECTED_BOOLEANS = {
    "agent_may_apply_after_validation": True,
    "agent_reapproval_required": False,
    "automatic_live_change": False,
    "live_arming_flags_required": True,
    "validation_required": True,
    "rollback_required": True,
}
_COVERED_CHANGES = (
    "strategy",
    "asset_universe",
    "route",
    "parameter",
    "leverage",
    "sizing",
    "risk_control",
    "execution_behavior",
    "deployment_configuration",
)


def normalize_standing_live_change_approval(
    value: object,
) -> dict[str, object] | None:
    """Validate one source-bound standing operator approval record."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("standing live-change approval must be an object")
    required = set(_TEXT_FIELDS + _ARRAY_FIELDS + _BOOLEAN_FIELDS)
    missing = sorted(required.difference(value))
    unknown = sorted(set(value).difference(required))
    if missing or unknown:
        raise ValueError(
            f"standing approval fields are invalid: missing={missing}, unknown={unknown}"
        )
    result: dict[str, object] = {
        field: _text(value.get(field), field) for field in _TEXT_FIELDS
    }
    result.update(
        {field: _text_list(value.get(field), field) for field in _ARRAY_FIELDS}
    )
    result.update({field: value.get(field) for field in _BOOLEAN_FIELDS})
    _validate_contract(result)
    return result


def build_human_approval_boundary(value: object) -> dict[str, object]:
    """Project operator approval without granting this report order authority."""
    if value is None:
        return _default_boundary()
    approval = normalize_standing_live_change_approval(value)
    if approval is None:
        return _default_boundary()
    return {
        "required_before_live_change": False,
        "required_outside_approved_scope": True,
        "covered_changes": list(_COVERED_CHANGES),
        "current_authority": "standing_operator_preapproval_recorded",
        "execution_authority": "none",
        **approval,
    }


def _default_boundary() -> dict[str, object]:
    return {
        "required_before_live_change": True,
        "required_outside_approved_scope": True,
        "covered_changes": list(_COVERED_CHANGES),
        "current_authority": "research_and_diagnostics_only",
        "execution_authority": "none",
        "agent_may_apply_after_validation": False,
        "agent_reapproval_required": True,
        "automatic_live_change": False,
        "live_arming_flags_required": True,
        "validation_required": True,
        "rollback_required": True,
    }


def _validate_contract(value: Record) -> None:
    valid = value.get("approval_status") == _STATUS and all(
        value.get(field) is expected for field, expected in _EXPECTED_BOOLEANS.items()
    )
    if not valid:
        raise ValueError("standing approval contract is invalid")


def _text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty text array")
    return [_text(item, label) for item in value]


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
