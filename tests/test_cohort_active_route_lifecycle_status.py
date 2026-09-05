"""Exact active-route lifecycle status ingestion for the improvement digest."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cohort_active_route_lifecycle_status import (
    load_active_route_lifecycle_statuses,
)


def test_loads_fresh_exact_route_status_and_evidence(tmp_path: Path) -> None:
    """A matching prospective collector must enter central observability."""
    overrides, audit, override_path = _fixture(tmp_path)

    result = load_active_route_lifecycle_statuses(
        overrides,
        audit,
        overrides_path=override_path,
        project_root=tmp_path,
        observed_at=datetime(2026, 8, 18, 21, 0, tzinfo=UTC),
        maximum_age_seconds=300.0,
    )

    assert len(result.statuses) == 1
    status = result.statuses[0]
    assert status["hypothesis_id"] == "hypothesis-short"
    assert status["route"] == "provider-short|BTC"
    assert status["freshness_status"] == "fresh"
    assert status["prospective_evaluations"] == 2
    assert status["prospective_eligible"] == 0
    assert result.evidence["hypothesis-short"]["sha256"]


def test_rejects_route_identity_mismatch(tmp_path: Path) -> None:
    """A collector for another provider cannot satisfy the hypothesis."""
    overrides, audit, override_path = _fixture(tmp_path)
    status_path = tmp_path / "data/runtime/status.json"
    payload = json.loads(status_path.read_text())
    payload["identity"]["route"] = "other-provider|BTC"
    status_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="route identity mismatch"):
        _load(tmp_path, overrides, audit, override_path)


def test_rejects_stale_route_status(tmp_path: Path) -> None:
    """A parked collector cannot masquerade as a current observation."""
    overrides, audit, override_path = _fixture(tmp_path)

    with pytest.raises(ValueError, match="route lifecycle status is stale"):
        load_active_route_lifecycle_statuses(
            overrides,
            audit,
            overrides_path=override_path,
            project_root=tmp_path,
            observed_at=datetime(2026, 8, 18, 21, 10, tzinfo=UTC),
            maximum_age_seconds=300.0,
        )


def test_rejects_changed_frozen_generator(tmp_path: Path) -> None:
    """Status evidence is invalid when its producer changes after polling."""
    overrides, audit, override_path = _fixture(tmp_path)
    (tmp_path / "src/generator.py").write_text("changed = True\n")

    with pytest.raises(ValueError, match="generator evidence mismatch"):
        _load(tmp_path, overrides, audit, override_path)


def test_legacy_active_hypothesis_without_status_path_remains_supported(
    tmp_path: Path,
) -> None:
    """Existing aggregate-counter hypotheses retain their separate contract."""
    overrides, audit, override_path = _fixture(tmp_path)
    overrides["active_hypotheses"] = [
        {
            "hypothesis_id": "legacy",
            "route": "legacy|BTC",
            "status": "being_tested",
            "execution_effect": "report_only",
        }
    ]

    result = _load(tmp_path, overrides, audit, override_path)

    assert result.statuses == []
    assert result.evidence == {}


def test_applies_source_bound_side_reconciliation(tmp_path: Path) -> None:
    """Central status must separate excluded long from executable short evidence."""
    overrides, audit, override_path = _fixture(tmp_path)
    status_path = tmp_path / "data/runtime/status.json"
    payload = json.loads(status_path.read_text())
    payload["state"] = "eligible_evidence_unattributed"
    payload["route_readiness"].update(
        eligible=1,
        prospective_eligible=1,
        unattributed_eligible_evaluations=1,
    )
    status_path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    reconciliation_path = tmp_path / "data/runtime/status-side.json"
    reconciliation_path.write_text(
        json.dumps(_side_reconciliation(payload, status_path), sort_keys=True) + "\n"
    )
    hypothesis = overrides["active_hypotheses"][0]
    hypothesis["side_reconciliation_path"] = "data/runtime/status-side.json"

    result = _load(tmp_path, overrides, audit, override_path)

    status = result.statuses[0]
    assert status["state"] == "awaiting_short"
    assert status["unattributed_eligible_evaluations"] == 0
    assert status["executable_side_eligible_evaluations"] == 0
    assert status["excluded_side_eligible_evaluations"] == 1
    assert result.evidence["hypothesis-short"]["side_reconciliation"]["sha256"]


def test_zero_eligible_status_does_not_require_side_reconciliation_artifact(
    tmp_path: Path,
) -> None:
    """No side claim exists to reconcile before the first eligible evaluation."""
    overrides, audit, override_path = _fixture(tmp_path)
    hypothesis = overrides["active_hypotheses"][0]
    hypothesis["side_reconciliation_path"] = "data/runtime/missing-side.json"

    result = _load(tmp_path, overrides, audit, override_path)

    status = result.statuses[0]
    assert status["prospective_eligible"] == 0
    assert status["side_reconciliation_status"] == "not_required_no_eligible_evidence"
    assert "side_reconciliation" not in result.evidence["hypothesis-short"]


def _load(
    root: Path,
    overrides: dict[str, object],
    audit: dict[str, object],
    override_path: Path,
) -> object:
    return load_active_route_lifecycle_statuses(
        overrides,
        audit,
        overrides_path=override_path,
        project_root=root,
        observed_at=datetime(2026, 8, 18, 21, 0, tzinfo=UTC),
        maximum_age_seconds=300.0,
    )


def _fixture(
    root: Path,
) -> tuple[dict[str, object], dict[str, object], Path]:
    override_path = root / "configs/research/overrides.json"
    preregistration = root / "docs/preregistration.json"
    generator = root / "src/generator.py"
    status_path = root / "data/runtime/status.json"
    for path in (override_path, preregistration, generator, status_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    preregistration.write_text('{"contract":"frozen"}\n')
    generator.write_text("FROZEN = True\n")
    status_path.write_text(
        json.dumps(_status(preregistration, generator), sort_keys=True) + "\n"
    )
    overrides = {"active_hypotheses": [_hypothesis()]}
    audit = {
        "run": {
            "run_id": "run-v57",
            "profile_id": "profile-v57",
            "profile_fingerprint": "a" * 64,
            "executable_provider_symbols": ["provider-short|BTC"],
        }
    }
    override_path.write_text(json.dumps(overrides))
    return overrides, audit, override_path


def _hypothesis() -> dict[str, object]:
    return {
        "hypothesis_id": "hypothesis-short",
        "route": "provider-short|BTC",
        "status": "being_tested",
        "decision_source": "../../docs/preregistration.json",
        "execution_effect": "report_only",
        "automatic_live_change": False,
        "lifecycle_status_path": "data/runtime/status.json",
        "required_sides": ["short"],
    }


def _status(preregistration: Path, generator: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_evidence",
        "observed_at_utc": "2026-08-18T20:59:00+00:00",
        "state": "awaiting_short",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "orders_or_fills_assumed": False,
            "promotion_authority": "none",
        },
        "identity": {
            "run_id": "run-v57",
            "profile_id": "profile-v57",
            "profile_fingerprint": "a" * 64,
            "provider_id": "provider-short",
            "signal_strategy_id": "provider-short",
            "symbol": "BTC",
            "route": "provider-short|BTC",
            "required_sides": ["short"],
        },
        "route_readiness": {
            "evaluations": 12,
            "eligible": 0,
            "prospective_evaluations": 2,
            "prospective_eligible": 0,
            "unattributed_eligible_evaluations": 0,
        },
        "side_progress": {
            "short": {
                "attributable_entries": 0,
                "open_lifecycles": 0,
                "closed_lifecycles": 0,
                "resolved_lifecycles": 0,
                "minimum_met": False,
            }
        },
        "open_lifecycles": [],
        "closed_lifecycles": [],
        "resolved_lifecycles": [],
        "unresolved_lifecycles": [],
        "minimum_diagnostic_evidence_met": False,
        "live_change_supported": False,
        "preregistration_evidence": {
            "path": "docs/preregistration.json",
            **file_evidence(preregistration),
        },
        "generator_identity": [
            {"path": "src/generator.py", **file_evidence(generator)}
        ],
    }


def _side_reconciliation(payload: dict[str, object], status: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_exact_route_lifecycle_side_reconciliation",
        "observed_at_utc": payload["observed_at_utc"],
        "state": "awaiting_short",
        "source_state": "eligible_evidence_unattributed",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
            "orders_or_fills_assumed": False,
            "promotion_authority": "none",
        },
        "identity": payload["identity"],
        "side_eligibility": {
            "prospective_by_side": {"long": 1, "short": 0},
            "executable_side_eligible_evaluations": 0,
            "excluded_side_eligible_evaluations": 1,
            "attributable_executable_lifecycles": 0,
            "unattributed_executable_side_eligible_evaluations": 0,
        },
        "side_progress": payload["side_progress"],
        "live_change_supported": False,
        "source_evidence": {
            "status": {
                "path": str(status.resolve()),
                **file_evidence(status),
            },
            "checkpoint": {
                "path": "/tmp/checkpoint.json",
                "bytes": 1,
                "sha256": "f" * 64,
            },
        },
    }
