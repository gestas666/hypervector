"""Tests for the frozen IBIT source acquisition command."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def test_ibit_acquisition_script_exists() -> None:
    """The preregistered source acquisition needs a reproducible entry point."""
    assert Path("scripts/v58_btc_ibit_creation_acquire.py").is_file()


def test_command_binds_preregistration_without_candidate_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must bind frozen identity before fetching official bytes."""
    module = _load_module()
    preregistration = _write_preregistration(tmp_path, "none")
    addendum = _write_addendum(tmp_path)
    output = tmp_path / "bundle"
    monkeypatch.setattr(module, "_fetch_bytes", lambda _: _valid_workbook())
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--source-integrity-addendum",
            str(addendum),
            "--output",
            str(output),
        ]
    )

    published = module.run_command(args)

    assert published == output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["context"]["hypothesis_id"] == (
        "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1"
    )
    assert manifest["context"]["preregistration"]["sha256"]
    assert manifest["context"]["source_integrity_addendum"]["sha256"]


@pytest.mark.parametrize(
    "authority, source_state, message",
    [
        ("live", "not_acquired_before_preregistration", "execution authority"),
        ("none", "already_acquired", "outcome-blind"),
    ],
)
def test_command_rejects_preregistration_drift_before_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authority: str,
    source_state: str,
    message: str,
) -> None:
    """Authority or prior-acquisition drift must prevent network access."""
    module = _load_module()
    preregistration = _write_preregistration(tmp_path, authority, source_state)
    addendum = _write_addendum(tmp_path)
    output = tmp_path / "bundle"
    fetched = False

    def fetch(_: str) -> bytes:
        nonlocal fetched
        fetched = True
        return _valid_workbook()

    monkeypatch.setattr(module, "_fetch_bytes", fetch)
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--source-integrity-addendum",
            str(addendum),
            "--output",
            str(output),
        ]
    )

    with pytest.raises(ValueError, match=message):
        module.run_command(args)
    assert fetched is False
    assert not output.exists()


def _write_preregistration(
    tmp_path: Path,
    authority: str,
    source_state: str = "not_acquired_before_preregistration",
) -> Path:
    path = tmp_path / "preregistration.json"
    payload = {
        "schema_version": "v58_btc_ibit_creation_persistence_long_preregistration_v1",
        "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
        "status": "preregistered_before_blackrock_source_acquisition_or_candidate_results",
        "authority": {"report_only": True, "execution_authority": authority},
        "source_evidence": {
            "blackrock_ibit_history": {
                "source_url": _source_url(),
                "path": None,
                "bytes": None,
                "sha256": None,
                "state": source_state,
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_addendum(tmp_path: Path) -> Path:
    path = tmp_path / "source-addendum.json"
    payload = {
        "schema_version": (
            "v58_btc_ibit_creation_persistence_long_source_integrity_addendum_v1"
        ),
        "hypothesis_id": "V58_BTC_IBIT_CREATION_PERSISTENCE_LONG_V1",
        "status": (
            "frozen_after_failed_technical_acquisition_before_candidate_signal_or_"
            "return_results"
        ),
        "authority": {"report_only": True, "execution_authority": "none"},
        "trigger": {
            "candidate_signal_count_inspected": False,
            "candidate_returns_inspected": False,
            "candidate_pnl_inspected": False,
        },
        "frozen_normalization_rule": {
            "frozen_market_start": "2025-07-28T00:00:00Z",
            "allowed_placeholder_token": "--",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_ibit_creation_acquire.py")
    spec = importlib.util.spec_from_file_location("btc_ibit_acquire_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_workbook() -> bytes:
    headers = ("As Of", "NAV per Share", "Ex-Dividends", "Shares Outstanding")
    rows = (("Aug 20, 2026", "38.25", "-", "1,200"),)
    rendered = "".join(_row(row) for row in (headers, *rows))
    return (
        '<Workbook xmlns:ss="urn:test"><Worksheet ss:Name="Historical"><Table>'
        f"{rendered}</Table></Worksheet></Workbook>"
    ).encode()


def _row(values: tuple[str, str, str, str]) -> str:
    cells = "".join(f"<Cell><Data>{value}</Data></Cell>" for value in values)
    return f"<Row>{cells}</Row>"


def _source_url() -> str:
    return (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v1/get-fund-document?appSubType=ISHARES&"
        "appType=PRODUCT_PAGE&component=fundDownload&locale=en_US&"
        "portfolioId=333011&targetSite=us-ishares&userType=individual"
    )
