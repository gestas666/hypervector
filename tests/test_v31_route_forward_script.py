"""CLI contracts for the bounded v31 route-forward tracker."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from route_forward_fixtures import frozen_source_checkpoint
from hypervector.research.route_forward_spec import V31_ROUTE_FORWARD_SPEC

_SCRIPT = Path("scripts/v31_route_forward.py")


def test_script_publishes_atomic_report_only_snapshot(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "latest.json"
    checkpoint = tmp_path / "v25-checkpoint.json"
    checkpoint.write_text(
        json.dumps(frozen_source_checkpoint(V31_ROUTE_FORWARD_SPEC)),
        encoding="utf-8",
    )
    args = module.build_parser().parse_args(
        [
            "--checkpoint",
            str(checkpoint),
            "--out",
            str(out),
        ]
    )

    report = module.run(args)
    persisted = json.loads(out.read_text(encoding="utf-8"))

    assert report["contract"]["execution_authority"] == "none"
    assert persisted == report
    assert persisted["evidence"]["checkpoint"]["sha256"]
    assert persisted["tracking_state"] == "candidate_inactive_baseline_captured"


def test_script_refuses_to_overwrite_an_immutable_snapshot(tmp_path: Path) -> None:
    module = _module()
    out = tmp_path / "immutable.json"
    out.write_text("{}\n", encoding="utf-8")
    args = module.build_parser().parse_args(["--out", str(out), "--immutable"])

    with pytest.raises(FileExistsError, match="already exists"):
        module.run(args)


def _module() -> object:
    spec = spec_from_file_location("v31_route_forward_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v31 route-forward script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
