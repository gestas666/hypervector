"""Immutable CLI publication for the HYPE-native third-path decision."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_third_forward_decision.py")


def test_script_publishes_supportive_approval_request(tmp_path: Path) -> None:
    """Exact inputs produce one immutable, report-only approval request."""
    module = _load_script()
    resolution = tmp_path / "resolution.json"
    journal = tmp_path / "journal.json"
    output = tmp_path / "decision.json"
    resolution.write_text(json.dumps(_resolution()), encoding="utf-8")
    journal.write_text(json.dumps(_journal()), encoding="utf-8")

    assert module.main(_argv(resolution, journal, output)) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["decision"] == "request_human_approval_for_hype_native_long_v3"
    assert report["evidence"]["resolution"]["sha256"]
    assert report["evidence"]["preregistered_journal"]["sha256"]
    assert report["change_proposals"][0]["execution_effect"] == "proposal_only"


def test_script_refuses_to_overwrite_decision(tmp_path: Path) -> None:
    """A decision artifact is immutable even when inputs are unchanged."""
    module = _load_script()
    resolution = tmp_path / "resolution.json"
    journal = tmp_path / "journal.json"
    output = tmp_path / "decision.json"
    resolution.write_text(json.dumps(_resolution()), encoding="utf-8")
    journal.write_text(json.dumps(_journal()), encoding="utf-8")
    module.main(_argv(resolution, journal, output))

    with pytest.raises(FileExistsError):
        module.main(_argv(resolution, journal, output))


def _argv(resolution: Path, journal: Path, output: Path) -> list[str]:
    return [
        "--resolution",
        str(resolution),
        "--preregistered-journal",
        str(journal),
        "--out",
        str(output),
    ]


def _resolution() -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_exact_post_close_resolution_report_only",
        "contract": {"report_only": True, "execution_authority": "none"},
        "identity": {
            "profile_id": "multi_asset_growth_first_5000_hype_native_long_challenger_v54",
            "profile_fingerprint": "1c0beafb19ef1b8c5594d3bf1aa6a23eeff12f28f540d958953cc25e8bff1643",
            "strategy_id": "hype_native_breakout_onset_long_v3",
            "symbol": "HYPE",
        },
        "lifecycles": [
            {
                "side": "long",
                "exit_reason": "maximum_hold",
                "funding_event_count": 8,
                "net_pnl_usd_after_funding": 13.0,
                "mark_stop_truth": "confirmed_no_earlier_mark_stop",
            }
        ],
        "summary": {"trades": 1, "net_pnl_usd_after_funding": 13.0},
    }


def _journal() -> dict[str, object]:
    return {
        "schema_version": 1,
        "hypothesis_id": "v54-hype-native-third-forward-preregistered-decision-v1",
        "automatic_live_change": False,
        "explicit_approval_requested": False,
        "preregistered_decision_rule": {
            "prior_two_path_net_usd_after_funding": 1.660554,
            "prior_largest_winner_usd": 13.754459,
            "prior_loss_usd": -12.093905,
            "third_path_after_funding_threshold_usd": 12.093905,
        },
    }


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_third_forward_decision_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
