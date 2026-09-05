"""Central monitor integration for exact route lifecycle collectors."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_cohort_improvement_monitor_script import (
    _install_fakes,
    _load,
    _monitor_files,
    _once_args,
)


def test_refresh_attaches_route_lifecycle_status_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The central digest must expose every validated active collector."""
    module = _load()
    checkpoint, output, history, overrides, _ = _monitor_files(tmp_path)
    _install_fakes(module, monkeypatch)
    collection = SimpleNamespace(
        statuses=[{"hypothesis_id": "route-first", "state": "awaiting_short"}],
        evidence={"route-first": {"sha256": "a" * 64, "bytes": 10}},
    )
    monkeypatch.setattr(
        module,
        "load_active_route_lifecycle_statuses",
        lambda *args, **kwargs: collection,
    )
    args = _once_args(module, checkpoint, output, history, overrides)

    assert module.run_monitor(args, sleep_fn=lambda seconds: None) == 0
    report = json.loads(output.read_text())
    assert report["active_hypothesis_lifecycle_statuses"] == collection.statuses
    assert report["evidence"]["active_hypothesis_lifecycle_statuses"] == (
        collection.evidence
    )
