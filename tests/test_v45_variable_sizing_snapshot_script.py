"""CLI contracts for the report-only v45 sizing snapshot."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root

_SCRIPT = Path("scripts/v45_variable_sizing_snapshot.py")
_CONFIG = Path(
    "configs/multi_asset_bidirectional_btc_specialists_growth_sizing_candidate_v45.toml"
)


def test_script_atomically_publishes_no_authority_empty_candidate_snapshot(
    tmp_path: Path,
) -> None:
    """The CLI retains the source prefix identity and cannot recommend sizing."""
    module = _module()
    ledger_root = tmp_path / "isolated"
    config = with_observer_ledger_root(
        load_multi_asset_live_config(_CONFIG, mode="observe"),
        ledger_root,
    )
    ledger = tmp_path / "decisions.jsonl"
    output = tmp_path / "latest.json"
    ledger.write_text(json.dumps(_row(config)) + "\n", encoding="utf-8")

    report = module.run(
        argparse.Namespace(
            config=_CONFIG,
            ledger=ledger,
            ledger_root=ledger_root,
            output=output,
        )
    )

    persisted = json.loads(output.read_text())
    assert report["eligible_candidates"] == 0
    assert persisted["tier_authority"] == "counterfactual_only"
    assert persisted["execution_authority"] == "none"
    assert persisted["source"]["rows"] == 1
    assert len(persisted["source"]["prefix_sha256"]) == 64


def _module() -> object:
    spec = importlib.util.spec_from_file_location("v45_sizing_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(config: object) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "profile_id": getattr(config, "profile_id"),
        "profile_fingerprint": getattr(config, "profile_fingerprint"),
        "run_id": "bidirectional-observe-test",
        "run_fingerprint": "test-run-fingerprint",
        "execution_authority": "none",
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "payload": {
            "actions": [],
            "evaluations": [
                {
                    "strategy_id": "hype_breakout_compression_pullback_bidirectional_v1",
                    "symbol": "HYPE",
                    "decision_time_ms": 1,
                    "decision_action": "hold",
                    "eligible": False,
                    "side": "long",
                    "readiness": {"metrics": {}},
                }
            ],
        },
    }
