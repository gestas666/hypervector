"""Tests for the frozen Deribit BTC DVOL acquisition command."""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.research.deribit_dvol_acquisition import (
    EXPECTED_ROWS,
    HOUR_MS,
    START_TIMESTAMP_MS,
)


def test_dvol_acquisition_script_exists() -> None:
    """The preregistered source acquisition needs a reproducible entry point."""
    assert Path("scripts/v58_btc_dvol_acquire.py").is_file()


def test_command_binds_preregistration_without_candidate_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must bind exact preregistration before source requests."""
    module = _load_module()
    preregistration = _write_preregistration(tmp_path)
    output = tmp_path / "bundle"
    responses = _responses()
    requests: list[dict[str, str | int]] = []

    def fetch(_: str, params: Mapping[str, str | int]) -> bytes:
        requests.append(dict(params))
        return responses[len(requests) - 1]

    monkeypatch.setattr(module, "_fetch_bytes", fetch)
    args = module.build_parser().parse_args(
        ["--preregistration", str(preregistration), "--output", str(output)]
    )

    published = module.run_command(args)

    manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
    assert published == output
    assert len(requests) == 9
    assert manifest["candidate_outcomes_computed"] is False
    assert manifest["context"]["hypothesis_id"] == (
        "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1"
    )
    assert len(manifest["context"]["preregistration"]["sha256"]) == 64


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"execution_authority": "live"}, "execution authority"),
        ({"status": "changed"}, "identity"),
        ({"outcomes_inspected_before_preregistration": True}, "outcome-blind"),
        (
            {"source_contract.source_acquisition_state": "already_acquired"},
            "source state",
        ),
    ],
)
def test_command_rejects_preregistration_drift_before_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, object],
    message: str,
) -> None:
    """Changed identity, authority, or outcome state must prevent requests."""
    module = _load_module()
    preregistration = _write_preregistration(tmp_path, change)
    fetched = False

    def fetch(_: str, __: Mapping[str, str | int]) -> bytes:
        nonlocal fetched
        fetched = True
        return b"{}"

    monkeypatch.setattr(module, "_fetch_bytes", fetch)
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--output",
            str(tmp_path / "bundle"),
        ]
    )

    with pytest.raises(ValueError, match=message):
        module.run_command(args)
    assert fetched is False


def _write_preregistration(
    tmp_path: Path,
    changes: dict[str, object] | None = None,
) -> Path:
    payload: dict[str, object] = {
        "schema_version": "v58_btc_dvol_vrp_continuation_long_preregistration_v1",
        "hypothesis_id": "V58_BTC_DVOL_VRP_CONTINUATION_LONG_V1",
        "status": "preregistered_before_source_acquisition_or_outcomes",
        "execution_authority": "none",
        "outcomes_inspected_before_preregistration": False,
        "candidate_signal_counts_inspected": False,
        "candidate_forward_returns_inspected": False,
        "candidate_trade_outcomes_inspected": False,
        "source_contract": {
            "endpoint": (
                "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            ),
            "parameters": {
                "currency": "BTC",
                "resolution": "3600",
                "start_utc": "2025-07-28T00:00:00Z",
                "end_utc": "2026-07-28T00:00:00Z",
            },
            "source_acquisition_state": "not_acquired_before_preregistration",
            "outcome_blind_coverage_expected_inclusive": 8761,
        },
    }
    for key, value in (changes or {}).items():
        if key == "source_contract.source_acquisition_state":
            source = payload["source_contract"]
            assert isinstance(source, dict)
            source["source_acquisition_state"] = value
        else:
            payload[key] = value
    path = tmp_path / "preregistration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _responses() -> list[bytes]:
    rows: list[list[int | float]] = [
        [START_TIMESTAMP_MS + index * HOUR_MS, 50.0, 51.0, 49.0, 50.5]
        for index in range(EXPECTED_ROWS)
    ]
    chunks = [rows[max(0, end - 1000) : end] for end in range(len(rows), 0, -1000)]
    return [
        json.dumps(
            {
                "jsonrpc": "2.0",
                "result": {
                    "data": chunk,
                    "continuation": (
                        chunk[0][0] - 1 if index < len(chunks) - 1 else None
                    ),
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        for index, chunk in enumerate(chunks)
    ]


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_dvol_acquire.py")
    spec = importlib.util.spec_from_file_location("btc_dvol_acquire_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
