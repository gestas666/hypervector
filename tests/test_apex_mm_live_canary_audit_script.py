"""Operator contract for the report-only Apex MM canary audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/apex_regime_mm_live_canary_audit.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("apex_mm_live_audit_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load audit script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity() -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": 1,
        "event_type": "configuration_identity",
        "observed_at_utc": "2026-08-01T12:00:00+00:00",
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "apex_regime_mm_canary_v1",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": "run-a",
        "payload": {"strategy_name": "apex_regime_mm_v2"},
    }


def test_script_is_report_only_and_publishes_immutable_sparse_evidence(
    tmp_path: Path,
) -> None:
    module = _load_script()
    ledger = tmp_path / "decisions.jsonl"
    content = (json.dumps(_identity()) + "\n").encode()
    ledger.write_bytes(content)
    output = tmp_path / "audit.json"

    assert module.main(["--decisions", str(ledger), "--out", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["experiment_contract"]["execution_authority"] == "none"
    assert report["experiment_contract"]["runtime_strategy_changed"] is False
    assert report["evidence"]["decisions"] == {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    with pytest.raises(FileExistsError, match="immutable live audit output exists"):
        module.main(["--decisions", str(ledger), "--out", str(output)])

    source = _SCRIPT.read_text(encoding="utf-8")
    assert "create_armed" not in source
    assert "private_key" not in source
    assert "submit_entry" not in source
