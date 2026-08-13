"""CLI contracts for immutable v31 post-start acceptance evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from hypervector.research.v31_poststart_acceptance import PRESSURE_ROUTES

_SCRIPT = Path("scripts/v31_poststart_acceptance.py")


def test_script_persists_rejection_and_returns_nonzero(tmp_path: Path) -> None:
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps(_rejected_checkpoint()), encoding="utf-8")
    out = tmp_path / "acceptance.json"
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(out)]
    )
    module.build_v31_route_forward_snapshot = lambda *unused: _source_snapshot()

    report = module.run(args)

    assert report["accepted"] is False
    assert json.loads(out.read_text(encoding="utf-8")) == report
    assert module.exit_code(report) == 2
    assert report["evidence"]["checkpoint"]["sha256"]


def test_script_refuses_to_replace_immutable_evidence(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "acceptance.json"
    out.write_text("{}\n", encoding="utf-8")
    args = module.build_parser().parse_args(["--out", str(out)])

    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _module() -> object:
    spec = spec_from_file_location("v31_poststart_acceptance_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v31 post-start acceptance script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rejected_checkpoint() -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-09T20:00:00+00:00",
        "transition_drain": {"status": "inactive"},
        "audit": {
            "coverage": {
                "complete": False,
                "technical_gaps": ["provider_metric_telemetry_missing"],
            },
            "health": {"faults": 0},
            "signal_outcomes": {
                "coverage": {
                    "complete": False,
                    "market_data_complete": True,
                    "metric_telemetry_complete": False,
                    "evaluations_without_metrics": 0,
                    "metric_value_gaps": 10,
                },
                "by_provider_symbol": {
                    route: {
                        "evaluations": 0,
                        "metric_diagnostics": _empty_diagnostics(),
                    }
                    for route in PRESSURE_ROUTES
                },
            },
        },
    }


def _empty_diagnostics() -> dict[str, object]:
    return {
        "coverage": {
            "complete": False,
            "evaluations_with_metrics": 0,
            "evaluations_without_metrics": 0,
            "metric_value_gaps": 0,
        },
        "metrics": {},
    }


def _source_snapshot() -> dict[str, object]:
    return {
        "phase": "pretransition_v25_baseline",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_transition": False,
            "runtime_strategy_changed": False,
        },
        "source_run": {
            "run_id": "v25-live-run",
            "profile_id": "multi_asset_bidirectional_complete_portfolio_canary_v25",
            "profile_fingerprint": "source-fingerprint",
        },
        "candidate": {
            "profile_id": "multi_asset_bidirectional_swing_pruned_candidate_v31",
            "profile_fingerprint": "candidate-fingerprint",
            "both_directions": True,
        },
        "live_state": {
            "faults": 0,
            "all_open_positions_protected": True,
            "open_positions": [],
        },
    }
