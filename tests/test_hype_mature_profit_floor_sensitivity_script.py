"""Command-boundary tests for immutable HYPE mature-floor evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.data.oxa_storage import file_evidence

_SCRIPT = Path(__file__).parents[1] / "scripts/hype_mature_profit_floor_sensitivity.py"
_SPEC = spec_from_file_location("hype_mature_floor_script", _SCRIPT)
assert _SPEC and _SPEC.loader
script = module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def _baseline(tmp_path: Path) -> Path:
    root = tmp_path / "baseline"
    root.mkdir()
    report = {
        "development": {
            "development": {},
            "selection": {"selected_challenger": "compression_5m50_1m40_pullback"},
        }
    }
    (root / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (root / "development_trades.parquet").write_bytes(b"development")
    (root / "confirmation_trades.parquet").write_bytes(b"confirmation")
    files = {
        name: file_evidence(root / name)
        for name in (
            "report.json",
            "development_trades.parquet",
            "confirmation_trades.parquet",
        )
    }
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "complete": True, "files": files}),
        encoding="utf-8",
    )
    return root


def test_verified_baseline_rejects_changed_sidecar(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    report = script.verified_baseline(baseline)
    assert report["development"]["selection"]["selected_challenger"] == (
        "compression_5m50_1m40_pullback"
    )

    (baseline / "development_trades.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="evidence"):
        script.verified_baseline(baseline)


def test_execution_config_matches_v51_hype_exit_contract() -> None:
    config = script.execution_config()
    assert config.maximum_hold_minutes == 480
    assert config.hard_maximum_hold_minutes == 1_440
    assert config.exit_on_opposite_signal is True
