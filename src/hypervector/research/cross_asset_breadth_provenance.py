"""Generator and prior-search provenance for breadth artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.cross_asset_impulse_artifact_validation import (
    validate_cross_asset_impulse_artifact,
)

_MODULE_PATHS = (
    "src/hypervector/research/cross_asset_breadth_models.py",
    "src/hypervector/research/cross_asset_breadth_data.py",
    "src/hypervector/research/cross_asset_breadth_signal.py",
    "src/hypervector/research/cross_asset_breadth_metrics.py",
    "src/hypervector/research/cross_asset_breadth_screen.py",
    "src/hypervector/research/cross_asset_breadth_artifact_validation.py",
    "src/hypervector/research/cross_asset_breadth_provenance.py",
    "src/hypervector/research/cross_asset_impulse_data.py",
    "src/hypervector/research/cross_asset_impulse_warmup.py",
    "src/hypervector/data/oxa_trade_bars.py",
    "src/hypervector/data/oxa_trade_candle_audit.py",
)
_PRIOR_SCHEMA = "cross_asset_impulse_development_v1"
_KNOWN_PRIOR_SELECTABLE_CELLS = 105


def build_breadth_generator_identity(runner_path: Path) -> dict[str, object]:
    """Hash every direct breadth generator and shared source-repair module."""
    root = Path(__file__).resolve().parents[3]
    runner = runner_path if runner_path.is_absolute() else root / runner_path
    relative_runner = _repository_relative(runner.resolve(), root)
    paths = (*_MODULE_PATHS, str(relative_runner))
    modules = {relative: file_evidence(root / relative) for relative in paths}
    return {"generator_modules": modules}


def build_prior_impulse_identity(path: Path) -> dict[str, object]:
    """Validate and bind the exact prior residual-plus-impulse search record."""
    validation = validate_cross_asset_impulse_artifact(path)
    payload = _read_json(path)
    accounting = payload.get("search_accounting")
    if not isinstance(accounting, dict):
        raise ValueError("prior impulse search accounting is missing")
    if payload.get("schema_version") != _PRIOR_SCHEMA:
        raise ValueError("prior impulse artifact schema differs")
    if (
        accounting.get("known_cumulative_selectable_cells")
        != _KNOWN_PRIOR_SELECTABLE_CELLS
    ):
        raise ValueError("prior impulse artifact must account for 105 selectable cells")
    evidence = file_evidence(path)
    return {
        "artifact": str(path),
        "sha256": evidence["sha256"],
        "bytes": evidence["bytes"],
        "selectable_cells": _KNOWN_PRIOR_SELECTABLE_CELLS,
        "schema_version": _PRIOR_SCHEMA,
        "validated_primary_cells": validation.primary_cells_verified,
        "validated_control_cells": validation.control_cells_verified,
        "file": evidence,
    }


def _repository_relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError as error:
        raise ValueError("breadth runner must be inside the repository") from error


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"prior impulse artifact does not exist: {path}")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prior impulse artifact must contain a JSON object")
    return payload
