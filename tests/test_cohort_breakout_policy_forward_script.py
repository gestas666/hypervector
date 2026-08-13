"""Tests for the immutable breakout policy forward audit command."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_SCRIPT = Path("scripts/cohort_breakout_policy_forward_audit.py")
_SOURCE = Path(
    "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
)
_CANDIDATE = Path(
    "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"
)


def test_command_publishes_immutable_report_only_evidence(tmp_path: Path) -> None:
    """The command must snapshot the ledger and refuse output replacement."""
    module = _module()
    source = load_multi_asset_live_config(_SOURCE, mode="observe")
    run_id = "breakout-script-run"
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "sequence": 1,
                "event_type": "configuration_identity",
                "run_id": run_id,
                "observed_at_utc": "2026-08-06T00:00:00+00:00",
                "payload": {"profile_fingerprint": source.profile_fingerprint},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "audit.json"
    args = module.build_parser().parse_args(
        [
            "--decisions",
            str(ledger),
            "--source-config",
            str(_SOURCE),
            "--candidate-config",
            str(_CANDIDATE),
            "--run-id",
            run_id,
            "--out",
            str(output),
        ]
    )

    report = module.publish(args)

    assert output.is_file()
    assert report["contract"]["execution_authority"] == "none"
    assert report["evidence"]["ledger"]["path"] == str(ledger)
    assert report["evidence"]["source_config"]["path"] == str(_SOURCE)
    assert report["evidence"]["candidate_config"]["path"] == str(_CANDIDATE)
    with pytest.raises(FileExistsError, match="output exists"):
        module.publish(args)


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("breakout_policy_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load breakout policy audit script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
