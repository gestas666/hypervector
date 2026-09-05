"""Tests for the immutable V62 BRENTOIL lock-decision command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "v62_brentoil_profit_lock_decision.py"


def _load() -> object:
    spec = spec_from_file_location("v62_brentoil_profit_lock_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V62 BRENTOIL decision script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_is_report_only_and_binds_checkpoint_and_preregistration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publication command cannot mutate live state or omit source identity."""
    checkpoint = tmp_path / "checkpoint.json"
    preregistration = tmp_path / "preregistration.json"
    checkpoint.write_text('{"generated_at_utc":"2026-08-25T17:00:00Z"}')
    preregistration.write_text('{"hypothesis_id":"brent-lock"}')
    script = _load()
    expected = {"passed": False, "decision": "retain_v61_no_lock_collect_both_sides"}
    monkeypatch.setattr(
        script, "evaluate_brentoil_profit_locks", lambda checkpoint, prereg: expected
    )
    monkeypatch.setattr(
        script,
        "file_evidence",
        lambda path: {"sha256": f"sha-{path.name}", "bytes": path.stat().st_size},
    )

    report = script.run(
        SimpleNamespace(checkpoint=checkpoint, preregistration=preregistration)
    )

    assert report["evaluation"] == expected
    assert report["execution_authority"] == "none"
    assert report["automatic_live_change"] is False
    assert report["runtime_strategy_changed"] is False
    assert report["checkpoint_generated_at_utc"] == "2026-08-25T17:00:00Z"
    assert report["sources"]["checkpoint"]["sha256"] == "sha-checkpoint.json"
