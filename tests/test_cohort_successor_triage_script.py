"""Tests for the immutable cohort successor-triage command."""

from __future__ import annotations

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path("scripts/cohort_successor_triage.py")


def test_script_binds_source_identity_and_refuses_overwrite(tmp_path: Path) -> None:
    """Published triage retains exact input bytes and is immutable."""
    source = tmp_path / "audit.json"
    output = tmp_path / "triage.json"
    source.write_text(json.dumps(_audit(), sort_keys=True) + "\n", encoding="utf-8")
    content = source.read_bytes()
    module = _load(SCRIPT, "cohort_successor_triage_script")

    assert module.main(["--audit", str(source), "--out", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evidence"] == {
        "audit_path": str(source.resolve()),
        "audit_sha256": hashlib.sha256(content).hexdigest(),
        "audit_bytes": len(content),
    }
    assert report["contract"]["execution_authority"] == "none"
    assert report["summary"] == {
        "routes": 1,
        "proceed": 0,
        "revise": 1,
        "stop_exact_contract": 0,
        "routes_with_both_side_live_execution": 0,
    }
    with pytest.raises(FileExistsError):
        module.main(["--audit", str(source), "--out", str(output)])


def _load(path: Path, name: str) -> ModuleType:
    """Load one script without invoking its entry point."""
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load script: {path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _audit() -> dict[str, object]:
    contract = {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
        "balance_gate": False,
        "runtime_strategy_changed": False,
    }
    return {
        "run": {
            "run_id": "run-1",
            "profile_id": "profile-v25",
            "profile_fingerprint": "a" * 64,
            "last_observed_at_utc": "2026-08-08T21:00:00+00:00",
        },
        "experiment_contract": contract,
        "strategy_scorecard": {
            "contract": contract,
            "by_provider_symbol": {
                "strategy|BTC": {
                    "strategy_id": "strategy",
                    "symbol": "BTC",
                    "research_state": "historical_candidate",
                    "confidence": "medium",
                    "directional_research": {},
                    "eligible_signal_horizons": {},
                    "execution_outcomes_identifiable": False,
                }
            },
        },
        "open_trade_reflections": {"contract": contract, "trades": []},
    }
