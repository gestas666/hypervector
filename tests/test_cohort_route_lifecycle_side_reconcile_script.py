"""Command tests for side-aware route lifecycle reconciliation."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from test_cohort_route_lifecycle_side_reconciliation import (
    _checkpoint,
    _status,
)

_SCRIPT = Path("scripts/cohort_route_lifecycle_side_reconcile.py")


def test_command_publishes_source_bound_side_reconciliation(tmp_path: Path) -> None:
    """The command must bind both mutable inputs to the corrected snapshot."""
    status = tmp_path / "status.json"
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "reconciled.json"
    status.write_text(json.dumps(_status(), sort_keys=True))
    checkpoint.write_text(json.dumps(_checkpoint(), sort_keys=True))

    report = _module().run_command(status, checkpoint, output)

    assert json.loads(output.read_text()) == report
    assert report["state"] == "awaiting_short"
    assert report["source_evidence"]["status"]["path"] == str(status.resolve())
    assert report["source_evidence"]["checkpoint"]["path"] == str(checkpoint.resolve())


def _module() -> object:
    spec = spec_from_file_location("cohort_route_lifecycle_side_reconcile", _SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("side reconciliation script must be importable")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
