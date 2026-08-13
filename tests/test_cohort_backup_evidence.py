"""Validation tests for durable cohort backup provenance."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_backup_evidence import (
    validated_prestart_backup_payload,
)


def _evidence() -> dict[str, object]:
    bundle = "data/backups/bidirectional_cohort/prestart_test"
    return {
        "status": "verified",
        "bundle_path": bundle,
        "manifest_path": f"{bundle}/manifest.json",
        "manifest_sha256": "a" * 64,
        "strategy_changed": True,
        "implementation_file_count": 1_156,
        "implementation_sha256": "b" * 64,
    }


def test_validated_prestart_backup_payload_preserves_exact_identity() -> None:
    """Valid non-secret evidence survives normalization without inference."""
    evidence = _evidence()

    assert validated_prestart_backup_payload(evidence) == evidence


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("manifest_sha256", "not-a-hash", "manifest SHA-256"),
        ("implementation_file_count", 0, "implementation count"),
        ("status", "assumed", "verification status"),
        ("manifest_path", "data/elsewhere/manifest.json", "must belong"),
    ],
)
def test_malformed_prestart_backup_payload_is_rejected(
    field: str,
    value: object,
    message: str,
) -> None:
    """Malformed provenance cannot become success-shaped journal evidence."""
    evidence = _evidence()
    evidence[field] = value

    with pytest.raises(ValueError, match=message):
        validated_prestart_backup_payload(evidence)


def test_extra_prestart_backup_field_is_rejected() -> None:
    """Unexpected fields cannot smuggle unreviewed data into run identity."""
    evidence = _evidence()
    evidence["wallet_secret"] = "must-not-pass"

    with pytest.raises(ValueError, match="fields are invalid"):
        validated_prestart_backup_payload(evidence)
