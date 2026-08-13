"""Tests for the immutable separate-side composition command."""

from __future__ import annotations

import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

SCRIPT = Path("scripts/cohort_side_composition.py")


def test_script_binds_audit_bytes_and_refuses_overwrite(tmp_path: Path) -> None:
    """Published composition must retain exact source identity and be immutable."""
    source = tmp_path / "audit.json"
    output = tmp_path / "composition.json"
    source.write_text(json.dumps(_audit(), sort_keys=True) + "\n", encoding="utf-8")
    content = source.read_bytes()
    module = _load(SCRIPT, "cohort_side_composition_script")

    assert module.main(["--audit", str(source), "--out", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evidence"] == {
        "audit_path": str(source.resolve()),
        "audit_sha256": hashlib.sha256(content).hexdigest(),
        "audit_bytes": len(content),
    }
    assert report["contract"]["execution_authority"] == "none"
    assert report["summary"]["both_side_frontier_available"] is True
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
            "last_observed_at_utc": "2026-08-09T05:00:00+00:00",
        },
        "experiment_contract": contract,
        "strategy_scorecard": {
            "contract": contract,
            "by_provider_symbol": {
                "strategy|BTC": {
                    "strategy_id": "strategy",
                    "symbol": "BTC",
                    "research_state": "directional_candidate",
                    "directional_research": {
                        "long": {"research_state": "historical_candidate"},
                        "short": {"research_state": "historical_candidate"},
                    },
                    "execution_outcomes_identifiable": False,
                }
            },
        },
        "entry_alignment_mechanism": {
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "execution_gate": False,
                "automatic_strategy_changes": False,
                "runtime_strategy_changed": False,
            },
            "scope": "all_live_history_mixed_profiles",
            "by_provider_symbol_side": {},
        },
    }
