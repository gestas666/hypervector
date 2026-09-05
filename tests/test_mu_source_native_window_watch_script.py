"""Durable runner for the independent MU source-native window status."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.data.oxa_storage import file_evidence


def test_watch_once_publishes_exact_authority_none_prefix_status(
    tmp_path: Path,
) -> None:
    """One cycle must bind the preregistration and observed journal prefix."""
    script = _script()
    args = _arguments(script, tmp_path)

    status = script.watch_once(args, clock_ms=lambda: 1_787_108_403_000)

    persisted = json.loads(args.status.read_text(encoding="utf-8"))
    assert status == persisted
    assert status["included_decisions"] == 1
    assert status["eligible_onsets"] == 1
    assert status["execution_authority"] == "none"
    assert status["input_evidence"]["journal_prefix"]["rows"] == 1
    assert status["input_evidence"]["preregistration"]["sha256"] == (
        args.preregistration_sha256
    )


def test_watch_rejects_wrong_preregistration_hash_without_status(
    tmp_path: Path,
) -> None:
    """A different experiment contract cannot silently reuse the status path."""
    script = _script()
    args = _arguments(script, tmp_path)
    args.preregistration_sha256 = "0" * 64

    with pytest.raises(ValueError, match="preregistration hash"):
        script.watch_once(args, clock_ms=lambda: 1_787_108_403_000)

    assert not args.status.exists()


def _script() -> ModuleType:
    path = Path("scripts/mu_source_native_window_watch.py")
    spec = importlib.util.spec_from_file_location("mu_window_watch_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("MU window watcher script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments(script: ModuleType, tmp_path: Path) -> argparse.Namespace:
    preregistration = tmp_path / "preregistration.json"
    journal = tmp_path / "decisions.jsonl"
    status = tmp_path / "status.json"
    preregistration.write_text(json.dumps(_preregistration()), encoding="utf-8")
    journal.write_text(json.dumps(_decision()) + "\n", encoding="utf-8")
    digest = str(file_evidence(preregistration)["sha256"])
    return script.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--preregistration-sha256",
            digest,
            "--journal",
            str(journal),
            "--status",
            str(status),
            "--max-cycles",
            "1",
        ]
    )


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v57_mu_source_native_independent_window_preregistration_v1",
        "status": "prospective_collecting",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "independence_contract": {"decision_start_ms": 1_787_108_400_000},
        "frozen_strategy_contract": {
            "symbol": "xyz:MU",
            "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
            "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
            "maximum_book_lateness_ms": 15_000,
        },
        "stopping_rule": {
            "minimum_eligible_onsets_before_replay": 20,
            "minimum_eligible_onsets_per_side_before_replay": 5,
            "time_limit_ms": 1_788_318_000_000,
        },
    }


def _decision() -> dict[str, object]:
    return {
        "event_type": "mu_hip3_breakout_shadow_decision",
        "decision": {
            "symbol": "xyz:MU",
            "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
            "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
            "decision_time_ms": 1_787_108_400_000,
            "observed_at_ms": 1_787_108_402_000,
            "eligible": True,
            "side": "long",
            "prospective": True,
            "execution_authority": "none",
        },
    }
