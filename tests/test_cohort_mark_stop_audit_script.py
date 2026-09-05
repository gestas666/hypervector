"""Immutable CLI evidence for exact cohort mark-stop paths."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT = Path("scripts/cohort_mark_stop_audit.py")


def _module() -> object:
    if not _SCRIPT.exists():
        pytest.fail("cohort mark-stop audit script is missing")
    spec = importlib.util.spec_from_file_location("cohort_mark_stop_audit", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_binds_lifecycle_marks_and_immutable_identity(tmp_path: Path) -> None:
    module = _module()
    start_ms = 1_800_000_000_000
    audit = _audit(tmp_path, start_ms)
    _mark_part(tmp_path, start_ms)
    output = tmp_path / "report.json"
    args = module.build_parser().parse_args(
        [
            "--audit",
            str(audit),
            "--lifecycle-id",
            "xyz:SPCX:123",
            "--data-root",
            str(tmp_path),
            "--as-of-time-ms",
            str(start_ms + 2_000),
            "--maximum-gap-ms",
            "2000",
            "--output",
            str(output),
        ]
    )

    report = module.run_command(args)

    assert report["run_identity"]["profile_id"] == "profile-v51"
    assert report["lifecycle_identity"]["lifecycle_id"] == "xyz:SPCX:123"
    assert report["mark_stop_path"]["path_status"] == "no_observed_stop_cross"
    assert report["mark_stop_path"]["observed_stop_crossed"] is False
    assert report["input_evidence"]["audit"]["sha256"]
    assert report["input_evidence"]["marks"]["rows"] == 3
    assert report["execution_authority"] == "none"
    assert report["automatic_live_change"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_command_rejects_missing_lifecycle_and_existing_output(tmp_path: Path) -> None:
    module = _module()
    start_ms = 1_800_000_000_000
    audit = _audit(tmp_path, start_ms)
    _mark_part(tmp_path, start_ms)
    output = tmp_path / "report.json"
    output.write_text("{}", encoding="utf-8")
    base = [
        "--audit",
        str(audit),
        "--lifecycle-id",
        "xyz:SPCX:missing",
        "--data-root",
        str(tmp_path),
        "--as-of-time-ms",
        str(start_ms + 2_000),
        "--output",
        str(output),
    ]

    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(module.build_parser().parse_args(base))

    output.unlink()
    with pytest.raises(ValueError, match="exactly one open lifecycle"):
        module.run_command(module.build_parser().parse_args(base))


def _audit(root: Path, start_ms: int) -> Path:
    path = root / "audit.json"
    payload = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_audit",
        "run": {
            "run_id": "run-v51",
            "profile_id": "profile-v51",
            "profile_fingerprint": "fingerprint-v51",
        },
        "open_trade_reflections": {
            "trades": [
                {
                    "lifecycle_id": "xyz:SPCX:123",
                    "symbol": "xyz:SPCX",
                    "side": "short",
                    "strategy_id": "hip3-v3",
                    "source_run_id": "source-run",
                    "entry": {
                        "venue_timestamp_ms": start_ms,
                        "price": 100.0,
                        "size": 10.0,
                    },
                    "protective_stop": {"oid": 456, "trigger_price": 105.0},
                }
            ]
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mark_part(root: Path, start_ms: int) -> Path:
    day = pd.Timestamp(start_ms, unit="ms", tz="UTC").date().isoformat()
    directory = (
        root / "cache/events/hyperliquid/xyz:SPCX" / day / "asset_context.parquet"
    )
    directory.mkdir(parents=True)
    path = directory / "part-fixture.parquet"
    rows = [
        {
            "symbol": "xyz:SPCX",
            "observed_ts_ms": start_ms + offset,
            "received_ts_ns": (start_ms + offset) * 1_000_000,
            "mark_price": mark,
            "source": "hyperliquid_ws_activeAssetCtx",
        }
        for offset, mark in ((0, 100.0), (1_000, 101.0), (2_000, 104.0))
    ]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path
