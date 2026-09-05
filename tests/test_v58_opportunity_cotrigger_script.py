"""Integration tests for the immutable V58 opportunity-prefix command."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "v58_opportunity_cotrigger.py"
CONFIG = ROOT / "configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml"


def test_command_publishes_exact_report_only_prefix(tmp_path: Path) -> None:
    """The CLI binds config identity, JSONL prefix, and immutable output."""
    base = load_multi_asset_live_config(CONFIG, mode="observe")
    config = with_observer_ledger_root(base, tmp_path)
    ledger = tmp_path / "decisions.jsonl"
    output = tmp_path / "report.json"
    ledger.write_text(
        json.dumps(_routing(config.profile_id, config.profile_fingerprint)) + "\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(SCRIPT),
        "--config",
        str(CONFIG),
        "--ledger",
        str(ledger),
        "--observer-ledger-root",
        str(tmp_path),
        "--run-id",
        "run-1",
        "--out",
        str(output),
    ]

    first = subprocess.run(command, capture_output=True, check=False, text=True)
    repeated = subprocess.run(command, capture_output=True, check=False, text=True)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert first.returncode == 0, first.stderr
    assert repeated.returncode != 0
    assert report["contract"]["execution_authority"] == "none"
    assert report["summary"]["executable_eligible_events"] == 1
    assert report["summary"]["maximum_concurrent_margin_fraction"] == 0.03
    assert report["source_evidence"]["ledger"]["rows"] == 1


def _routing(profile_id: str, fingerprint: str) -> dict[str, object]:
    return {
        "event_type": "intent_routing",
        "sequence": 1,
        "observed_at_utc": "2026-08-19T09:00:00+00:00",
        "run_id": "run-1",
        "profile_id": profile_id,
        "profile_fingerprint": fingerprint,
        "execution_authority": "none",
        "payload": {
            "evaluations": [
                {
                    "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
                    "symbol": "ETH",
                    "side": "long",
                    "decision_time_ms": 100,
                    "eligible": True,
                    "reason": "ready",
                    "decision_action": "enter_long",
                    "backend_non_action_reason": None,
                }
            ]
        },
    }
