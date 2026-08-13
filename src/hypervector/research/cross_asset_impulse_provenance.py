"""Generator and prior-search provenance for impulse research artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence

_MODULE_PATHS = (
    "src/hypervector/research/cross_asset_impulse_models.py",
    "src/hypervector/research/cross_asset_impulse_data.py",
    "src/hypervector/research/cross_asset_impulse_warmup.py",
    "src/hypervector/research/cross_asset_impulse_signal.py",
    "src/hypervector/research/cross_asset_impulse_screen.py",
    "src/hypervector/research/cross_asset_impulse_evidence.py",
    "src/hypervector/research/cross_asset_impulse_metrics.py",
    "src/hypervector/research/cross_asset_impulse_artifact_metrics.py",
    "src/hypervector/research/cross_asset_impulse_artifact_validation.py",
    "src/hypervector/research/cross_asset_impulse_provenance.py",
)
_PRIOR_SCHEMA = "cross_asset_residual_exit_surface_v2"
_PRIOR_CELL_COUNT = 90


def build_impulse_generator_identity(runner_path: Path) -> dict[str, object]:
    """Hash every impulse generator module and the invoked command runner."""
    root = Path(__file__).resolve().parents[3]
    runner = runner_path if runner_path.is_absolute() else root / runner_path
    relative_runner = _repository_relative(runner.resolve(), root)
    modules = {
        relative: _module_evidence(root, relative)
        for relative in (*_MODULE_PATHS, str(relative_runner))
    }
    return {"generator_modules": modules}


def build_prior_residual_identity(path: Path) -> dict[str, object]:
    """Verify and hash the exact prior 90-cell residual v2 search artifact."""
    if not path.is_file():
        raise FileNotFoundError(f"prior residual v2 artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prior residual artifact must contain a JSON object")
    if payload.get("schema_version") != _PRIOR_SCHEMA:
        raise ValueError("prior residual artifact schema is not exit-surface v2")
    if payload.get("trial_count") != _PRIOR_CELL_COUNT:
        raise ValueError("prior residual artifact must retain exactly 90 cells")
    if payload.get("report_only") is not True:
        raise ValueError("prior residual artifact must be report-only")
    if payload.get("execution_authority") != "none":
        raise ValueError("prior residual artifact authority must be none")
    evidence = file_evidence(path)
    return {
        "artifact": str(path),
        "sha256": evidence["sha256"],
        "bytes": evidence["bytes"],
        "selectable_cells": _PRIOR_CELL_COUNT,
        "schema_version": _PRIOR_SCHEMA,
        "trial_count": _PRIOR_CELL_COUNT,
        "file": evidence,
    }


def _repository_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError as error:
        raise ValueError("impulse runner must be inside the repository") from error


def _module_evidence(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"impulse generator module does not exist: {path}")
    return file_evidence(path)
