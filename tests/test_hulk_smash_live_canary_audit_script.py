"""Operator contract for the immutable Hulk live-canary audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


_SCRIPT = Path("scripts/hulk_smash_live_canary_audit.py")


def test_hulk_audit_script_is_report_only_and_immutable(tmp_path: Path) -> None:
    """Publishing an audit cannot create execution authority or overwrite evidence."""
    module = _load_script()
    ledger = tmp_path / "decisions.jsonl"
    content = b"".join(json.dumps(row).encode() + b"\n" for row in _flat_rows())
    ledger.write_bytes(content)
    output = tmp_path / "audit.json"

    assert module.main(["--decisions", str(ledger), "--out", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["experiment_contract"]["execution_authority"] == "none"
    assert report["evidence"]["decisions"] == {
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
    }
    with pytest.raises(FileExistsError, match="immutable live audit output exists"):
        module.main(["--decisions", str(ledger), "--out", str(output)])

    source = _SCRIPT.read_text(encoding="utf-8")
    assert "private_key" not in source
    assert "create_armed" not in source
    assert "submit_market_entry" not in source


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hulk_live_audit_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load audit script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flat_rows() -> list[dict[str, object]]:
    payloads = [
        ("configuration_identity", {"strategy_name": "hulk_expansion_short_robust_v3"}),
        ("position", {"size_signed": 0.0, "position_value_usd": 0.0}),
        ("reconciliation", {"account_value_usd": 150.0, "open_order_ids": []}),
        ("state_transition", {"state": "STOPPED"}),
    ]
    return [
        {
            "schema_version": 1,
            "sequence": sequence,
            "event_type": event_type,
            "observed_at_utc": f"2026-08-01T12:00:0{sequence}+00:00",
            "execution_mode": "live",
            "live_armed": True,
            "execution_authority": "hyperliquid_mainnet",
            "profile_id": "hulk_expansion_short_robust_v3_canary_v1",
            "profile_fingerprint": "profile",
            "run_fingerprint": "run",
            "run_id": "run-a",
            "payload": payload,
        }
        for sequence, (event_type, payload) in enumerate(payloads, start=1)
    ]
