"""CLI tests for immutable v42 successor-design evidence."""

from __future__ import annotations

import pytest

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

_SCRIPT = Path("scripts/v42_successor_design.py")


@pytest.mark.evidence
def test_report_is_source_bound_and_execution_incapable(tmp_path: Path) -> None:
    """The command captures every input without granting runtime authority."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(json.dumps(_runtime_checkpoint()), encoding="utf-8")
    args = module.build_parser().parse_args(
        [
            "--current-checkpoint",
            str(checkpoint),
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    report = module.run_report(args)

    assert report["contract"]["execution_authority"] == "none"
    assert report["candidate"]["profile_id"].endswith("v42")
    assert set(report["evidence"]) == {
        "config",
        "v41_readiness",
        "current_checkpoint",
        "hype_exit_evidence",
    }
    assert report["generator_identity"]["files"]
    module.require_unchanged_inputs(report)


def _runtime_checkpoint() -> dict[str, object]:
    return {
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": "frozen-v39-profile",
        },
        "audit": {
            "trade_reflections": {
                "performance": {
                    "current_run": {
                        "run_id": "frozen-v39-run",
                        "total": {
                            "closed_trades": 4,
                            "wins": 0,
                            "losses": 4,
                            "net_pnl_usd": -2.25,
                        },
                    }
                }
            },
            "open_trade_reflections": {"open_lifecycles": 0},
        },
        "lifecycle": {"all_assets_terminal": False},
    }


def _module() -> ModuleType:
    spec = spec_from_file_location("v42_successor_design_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v42 successor-design script")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
