"""Operator contract for the report-only source-follow live-canary audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import duckdb
import pytest


_SCRIPT = Path("scripts/hypervelocity_source_live_canary_audit.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("source_live_canary_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load audit script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ledger_row() -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": 1,
        "event_type": "configuration_identity",
        "observed_at_utc": "2026-07-31T20:00:00+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "source-bidirectional",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": "run-a",
        "payload": {"symbol": "BTC", "network": "mainnet"},
    }


def test_script_contract_is_report_only_and_accepts_explicit_run() -> None:
    """The operator boundary carries evidence paths but no execution authority."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--decisions",
            "decisions.jsonl",
            "--database",
            "market.duckdb",
            "--run-id",
            "run-a",
            "--out",
            "audit.json",
        ]
    )

    assert args.decisions == Path("decisions.jsonl")
    assert args.database == Path("market.duckdb")
    assert args.run_id == "run-a"
    assert args.out == Path("audit.json")
    assert module._experiment_contract() == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
    }
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "create_armed" not in source
    assert "private_key" not in source
    assert "submit_entry" not in source


def test_script_publishes_immutable_evidence_and_never_gates_sparse_results(
    tmp_path: Path,
) -> None:
    """A valid zero-decision run is published and an existing output is refused."""
    module = _load_script()
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps(_ledger_row()) + "\n", encoding="utf-8")
    database = tmp_path / "market.duckdb"
    with duckdb.connect(str(database)):
        pass
    output = tmp_path / "audit.json"
    argv = [
        "--decisions",
        str(decisions),
        "--database",
        str(database),
        "--out",
        str(output),
    ]

    assert module.main(argv) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["report_only"] is True
    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["run"]["run_id"] == "run-a"
    assert report["decisions"]["rows"] == 0
    assert report["evidence"]["decisions"]["sha256"]
    assert report["evidence"]["database"]["sha256"]
    with pytest.raises(FileExistsError, match="immutable live audit output exists"):
        module.main(argv)


def test_ledger_snapshot_hashes_exactly_the_rows_that_are_audited(
    tmp_path: Path,
) -> None:
    """Concurrent appends to the live ledger cannot alter captured provenance."""
    module = _load_script()
    decisions = tmp_path / "decisions.jsonl"
    original = (json.dumps(_ledger_row()) + "\n").encode()
    decisions.write_bytes(original)

    with module._ledger_snapshot(decisions) as (rows, evidence):
        decisions.write_bytes(original + original)

    assert len(rows) == 1
    assert evidence == {
        "sha256": hashlib.sha256(original).hexdigest(),
        "bytes": len(original),
    }
