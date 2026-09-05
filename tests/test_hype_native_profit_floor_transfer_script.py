"""Command tests for native-HYPE profit-floor transfer evidence."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_profit_floor_transfer.py")


def test_command_reconciles_closed_and_prospective_ledger_prefixes(
    tmp_path: Path,
) -> None:
    module = _load_script()
    args, observer = _command_args(tmp_path, module)

    module.run_command(args)

    report = json.loads(args.output.read_text(encoding="utf-8"))
    assert report["comparison"]["status"] == "provisional_open_lifecycle"
    assert report["comparison"]["trades"] == 2
    assert report["comparison"]["triggered"] == 2
    assert report["source_evidence"]["prospective_ledger"]["sha256"] == (
        sha256(observer.read_bytes()).hexdigest()
    )
    assert report["contract"]["execution_authority"] == "none"


def test_immutable_final_output_refuses_replacement(tmp_path: Path) -> None:
    module = _load_script()
    args, _observer = _command_args(tmp_path, module, immutable=True)

    module.run_command(args)

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.run_command(args)


def _command_args(
    tmp_path: Path, module: ModuleType, *, immutable: bool = False
) -> tuple[object, Path]:
    cohort = _jsonl(tmp_path / "cohort.jsonl", (_candle("closed"),))
    asset = _jsonl(tmp_path / "asset.jsonl", (_book("closed"),))
    path = _write_json(tmp_path / "path.json", _closed_path(asset, cohort))
    funded = _write_json(tmp_path / "funded.json", _funded())
    observer = _jsonl(
        tmp_path / "observer.jsonl",
        (_candle("prospective"), _book("prospective")),
    )
    status = _write_json(tmp_path / "status.json", _status(observer))
    output = tmp_path / "report.json"
    argv = [
        "--closed-path",
        str(path),
        "--closed-funded",
        str(funded),
        "--lifecycle-status",
        str(status),
        "--output",
        str(output),
    ]
    if immutable:
        argv.append("--immutable")
    return module.build_parser().parse_args(argv), observer


def _closed_path(asset: Path, cohort: Path) -> dict[str, object]:
    return {
        "identity": {"run_id": "closed", "symbol": "HYPE", "side": "long"},
        "execution_path": {
            "entry_book_time_ms": 10_000,
            "entry_price": 100.0,
            "entry_quantity": 1.0,
            "exit_reason": "maximum_hold",
        },
        "evidence": {
            "asset_ledger": _slice_evidence(asset),
            "cohort_ledger": _slice_evidence(cohort),
        },
    }


def _candle(run_id: str) -> dict[str, object]:
    bars = [
        {
            "timestamp_ms": 60_000,
            "open": 100.0,
            "high": 101.1,
            "low": 99.9,
            "close": 100.5,
        },
        {
            "timestamp_ms": 120_000,
            "open": 100.5,
            "high": 100.8,
            "low": 100.2,
            "close": 100.4,
        },
        {
            "timestamp_ms": 180_000,
            "open": 100.4,
            "high": 100.7,
            "low": 100.3,
            "close": 100.5,
        },
    ]
    return {
        "event_type": "market_candles",
        "run_id": run_id,
        "payload": {"timeframe": "1m", "bars": {"HYPE": bars}},
    }


def _book(run_id: str) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "run_id": run_id,
        "payload": {
            "symbol": "HYPE",
            "exchange_ts_ms": 180_000,
            "recv_ts_ms": 180_005,
            "bids": [{"price": 100.25, "size": 10.0}],
            "asks": [{"price": 100.26, "size": 10.0}],
        },
    }


def _funded() -> dict[str, object]:
    return {
        "entry_book_time_ms": 10_000,
        "exit_book_time_ms": 240_000,
        "net_pnl_usd_after_funding": 2.5,
        "funding_events": [{"event_ts_ms": 150_000, "cashflow_usd": -0.01}],
    }


def _status(observer: Path) -> dict[str, object]:
    return {
        "mode": "hype_native_v54_prospective_lifecycle_report_only",
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {"run_id": "prospective", "symbol": "HYPE"},
        "lifecycles": [
            {
                "entry_book_time_ms": 10_000,
                "entry_price": 100.0,
                "entry_quantity": 1.0,
                "current_book_time_ms": 240_000,
                "exit_book_time_ms": None,
                "exit_reason": None,
            }
        ],
        "evidence": {"decision_ledger": _prefix_evidence(observer)},
    }


def _slice_evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), "source_start_offset": 0, **_prefix_evidence(path)}


def _prefix_evidence(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha256(raw).hexdigest()}


def _jsonl(path: Path, rows: tuple[dict[str, object], ...]) -> Path:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_profit_floor_transfer_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
