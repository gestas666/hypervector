"""CLI contracts for the bounded v32 route-forward tracker."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from route_forward_fixtures import frozen_source_checkpoint
from hypervector.research.route_forward_spec import V32_ROUTE_FORWARD_SPEC

_SCRIPT = Path("scripts/v32_route_forward.py")


def test_script_publishes_exact_v32_report_only_snapshot(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "latest-v32.json"
    checkpoint = tmp_path / "v25-checkpoint.json"
    checkpoint.write_text(
        json.dumps(frozen_source_checkpoint(V32_ROUTE_FORWARD_SPEC)),
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(out)]
    )

    report = module.run(args)
    persisted = json.loads(out.read_text(encoding="utf-8"))

    assert persisted == report
    assert report["schema_version"] == "v32_route_forward_snapshot_v1"
    assert report["contract"]["execution_authority"] == "none"
    assert report["candidate"]["profile_id"].endswith("candidate_v32")
    assert len(report["candidate"]["removed_routes"]) == 3
    assert report["tracking_state"] in {
        "candidate_inactive_baseline_captured",
        "candidate_forward_tracking",
    }


def test_script_refuses_to_overwrite_immutable_snapshot(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "immutable.json"
    out.write_text("{}\n", encoding="utf-8")
    args = module.build_parser().parse_args(["--out", str(out), "--immutable"])

    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _module() -> object:
    spec = spec_from_file_location("v32_route_forward_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v32 route-forward script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
