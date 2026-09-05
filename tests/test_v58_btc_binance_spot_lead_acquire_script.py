"""Tests for the frozen Binance spot source-acquisition command."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.research.binance_spot_archive_acquisition import (
    monthly_spot_kline_archives,
)


def test_binance_spot_acquisition_script_exists() -> None:
    """The source-bound acquisition must have a reproducible entry point."""
    assert Path("scripts/v58_btc_binance_spot_lead_acquire.py").is_file()


def test_command_binds_preregistration_without_candidate_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must preserve the frozen authority-none research identity."""
    module = _load_module()
    assert hasattr(module, "build_parser")
    assert hasattr(module, "run_command")
    preregistration = _write_preregistration(tmp_path, "none")
    output = tmp_path / "bundle"
    responses = _responses()
    monkeypatch.setattr(module, "_fetch_bytes", responses.__getitem__)
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--output",
            str(output),
        ]
    )

    published = module.run_command(args)

    assert published == output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_count"] == 13
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["context"]["hypothesis_id"] == (
        "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1"
    )
    assert manifest["context"]["preregistration"]["sha256"]


def test_command_rejects_preregistration_with_authority(tmp_path: Path) -> None:
    """A research source bundle must fail closed on authority drift."""
    module = _load_module()
    assert hasattr(module, "build_parser")
    assert hasattr(module, "run_command")
    preregistration = _write_preregistration(tmp_path, "live")
    output = tmp_path / "bundle"
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match="execution authority"):
        module.run_command(args)
    assert not output.exists()


def _responses() -> dict[str, bytes]:
    start = datetime(2025, 7, 28, tzinfo=UTC)
    end = datetime(2026, 7, 28, tzinfo=UTC)
    values: dict[str, bytes] = {}
    for spec in monthly_spot_kline_archives(start, end):
        content = f"archive:{spec.filename}".encode()
        digest = hashlib.sha256(content).hexdigest()
        values[spec.url] = content
        values[spec.checksum_url] = f"{digest}  {spec.filename}\n".encode()
    return values


def _write_preregistration(tmp_path: Path, authority: str) -> Path:
    path = tmp_path / "preregistration.json"
    payload = {
        "schema_version": (
            "v58_btc_binance_spot_lead_hl_perp_catchup_preregistration_v1"
        ),
        "hypothesis_id": "V58_BTC_BINANCE_SPOT_LEAD_HL_PERP_CATCHUP_LONG_V1",
        "status": (
            "preregistered_before_external_spot_data_acquisition_or_candidate_results"
        ),
        "authority": {"execution_authority": authority},
        "source_evidence": {
            "binance_spot_bars": {
                "path": None,
                "bytes": None,
                "sha256": None,
                "state": "not_acquired_before_preregistration",
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_binance_spot_lead_acquire.py")
    spec = importlib.util.spec_from_file_location("btc_binance_acquire_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
