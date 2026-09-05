"""Command contract for the report-only SP500 lifecycle watcher."""

from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "sp500_fresh15_lifecycle_watch.py"


def test_sp500_lifecycle_watch_script_exists() -> None:
    """The durable watcher must expose a standalone report-only command."""
    assert SCRIPT.is_file()


def test_watch_once_publishes_exact_authority_none_status(tmp_path: Path) -> None:
    """One cycle must bind both append-only inputs before atomic publication."""
    module = _load()
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(json.dumps(_preregistration()))
    decision_journal = tmp_path / "decisions.jsonl"
    decision_journal.write_text(json.dumps(_decision()) + "\n")
    candle_journal = tmp_path / "candles.jsonl"
    candle_journal.write_text(json.dumps(_candle()) + "\n")
    status_path = tmp_path / "status.json"
    prereg_hash = sha256(preregistration.read_bytes()).hexdigest()
    args = module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--preregistration-sha256",
            prereg_hash,
            "--decision-journal",
            str(decision_journal),
            "--profit-lock-candles",
            str(candle_journal),
            "--status",
            str(status_path),
            "--max-cycles",
            "1",
        ]
    )

    payload = module.watch_once(args, clock_ms=lambda: _DECISION_MS + 65_000)

    assert json.loads(status_path.read_text()) == payload
    assert payload["execution_authority"] == "none"
    assert payload["orders_supported"] is False
    evidence = payload["input_evidence"]
    assert evidence["preregistration"]["sha256"] == prereg_hash
    assert evidence["decision_journal_prefix"]["rows"] == 1
    assert evidence["profit_lock_candle_prefix"]["rows"] == 1
    assert payload["generator_identity"]["files"]


def test_watch_once_rejects_wrong_preregistration_hash(tmp_path: Path) -> None:
    """A different experiment contract must not reuse the status path."""
    module = _load()
    args = _arguments(module, tmp_path)
    args.preregistration_sha256 = "0" * 64

    with pytest.raises(ValueError, match="preregistration hash"):
        module.watch_once(args, clock_ms=lambda: _DECISION_MS + 65_000)

    assert not args.status.exists()


_DECISION_MS = 1_787_120_100_000
_ENTRY_MS = 1_787_120_101_436


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v58_sp500_fresh15_lifecycle_watch_preregistration_v1",
        "status": "prospective_collecting",
        "symbol": "xyz:SP500",
        "provider_id": "fresh15-v3",
        "profile_id": "sp500-shadow-v3",
        "event": {
            "decision_time_ms": _DECISION_MS,
            "entry_time_ms": _ENTRY_MS,
            "side": "short",
            "entry_price": 7675.6,
            "stop_price": 7737.0048,
        },
        "profit_lock": {
            "policy_id": "v58_hip3_sp500_100_40_80",
            "activation_bps": 100.0,
            "floor_bps": 40.0,
            "trailing_giveback_bps": 80.0,
        },
        "maximum_hold_minutes": 1440,
        "maximum_candle_age_ms": 120_000,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _decision() -> dict[str, object]:
    return {
        "event_type": "sp500_hip3_breakout_shadow_decision",
        "execution_authority": "none",
        "decision": {
            "symbol": "xyz:SP500",
            "provider_id": "fresh15-v3",
            "profile_id": "sp500-shadow-v3",
            "decision_time_ms": _DECISION_MS,
            "observed_at_ms": _ENTRY_MS,
            "eligible": True,
            "side": "short",
            "prospective": True,
            "execution_authority": "none",
        },
    }


def _candle() -> dict[str, object]:
    return {
        "event_type": "sp500_hip3_breakout_shadow_profit_lock_candle_observation",
        "symbol": "xyz:SP500",
        "bar_open_ms": _DECISION_MS,
        "bar_close_ms": _DECISION_MS + 60_000,
        "observed_at_ms": _DECISION_MS + 61_000,
        "open": 7675.7,
        "high": 7675.9,
        "low": 7675.4,
        "close": 7675.9,
        "source": "hyperliquid_public_candleSnapshot_1m",
        "prospective": True,
        "execution_authority": "none",
    }


def _load() -> ModuleType:
    spec = spec_from_file_location("sp500_fresh15_lifecycle_watch_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load SP500 lifecycle watcher")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(module: ModuleType, tmp_path: Path) -> argparse.Namespace:
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(json.dumps(_preregistration()))
    decision_journal = tmp_path / "decisions.jsonl"
    decision_journal.write_text(json.dumps(_decision()) + "\n")
    candle_journal = tmp_path / "candles.jsonl"
    candle_journal.write_text(json.dumps(_candle()) + "\n")
    return module.build_parser().parse_args(
        [
            "--preregistration",
            str(preregistration),
            "--preregistration-sha256",
            sha256(preregistration.read_bytes()).hexdigest(),
            "--decision-journal",
            str(decision_journal),
            "--profit-lock-candles",
            str(candle_journal),
            "--status",
            str(tmp_path / "status.json"),
            "--max-cycles",
            "1",
        ]
    )
