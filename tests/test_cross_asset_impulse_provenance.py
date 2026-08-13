from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hypervector.research.cross_asset_impulse_provenance import (
    build_impulse_generator_identity,
    build_prior_residual_identity,
)


def test_generator_identity_hashes_runner_and_every_impulse_module() -> None:
    runner = Path("scripts/cross_asset_impulse_development.py")

    identity = build_impulse_generator_identity(runner)

    modules = identity["generator_modules"]
    assert str(runner) in modules
    assert "src/hypervector/research/cross_asset_impulse_models.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_data.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_warmup.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_signal.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_screen.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_evidence.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_metrics.py" in modules
    assert "src/hypervector/research/cross_asset_impulse_provenance.py" in modules
    assert (
        "src/hypervector/research/cross_asset_impulse_artifact_validation.py" in modules
    )
    assert "src/hypervector/research/cross_asset_impulse_artifact_metrics.py" in modules
    assert len(modules) == 11
    for relative, evidence in modules.items():
        payload = Path(relative).read_bytes()
        assert evidence["bytes"] == len(payload)
        assert evidence["sha256"] == hashlib.sha256(payload).hexdigest()


def test_prior_residual_identity_requires_exact_v2_report(tmp_path: Path) -> None:
    path = tmp_path / "cross_asset_residual_exit_surface_v2.json"
    payload = {
        "schema_version": "cross_asset_residual_exit_surface_v2",
        "trial_count": 90,
        "report_only": True,
        "execution_authority": "none",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    identity = build_prior_residual_identity(path)

    assert identity["artifact"] == str(path)
    assert identity["selectable_cells"] == 90
    assert identity["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert identity["schema_version"] == payload["schema_version"]
    assert identity["trial_count"] == 90
    assert identity["file"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": "cross_asset_residual_exit_surface_v1"}, "schema"),
        ({"trial_count": 89}, "90 cells"),
        ({"report_only": False}, "report-only"),
        ({"execution_authority": "orders"}, "authority"),
    ],
)
def test_prior_residual_identity_rejects_wrong_contract(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    path = tmp_path / "residual.json"
    payload: dict[str, object] = {
        "schema_version": "cross_asset_residual_exit_surface_v2",
        "trial_count": 90,
        "report_only": True,
        "execution_authority": "none",
    }
    payload.update(change)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        build_prior_residual_identity(path)
