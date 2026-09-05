"""Command contract for cutoff-bound observer evidence."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/cohort_observer_prospective_window.py")


def test_publish_binds_snapshot_evidence_and_window_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command must publish the exact source prefix and frozen cutoff."""
    module = _load_script()
    output = tmp_path / "window.json"
    source = tmp_path / "observer.jsonl"
    calls: dict[str, object] = {}

    @contextmanager
    def snapshot(path: Path):
        calls["source"] = path
        yield ([{"run_id": "run-a"}], {"bytes": 12, "sha256": "a" * 64})

    def audit(records: object, *, run_id: str) -> dict[str, object]:
        calls["audit"] = (records, run_id)
        return {"mode": "full-audit"}

    def build(
        records: object, full_audit: object, *, start_ms: int
    ) -> dict[str, object]:
        calls["build"] = (records, full_audit, start_ms)
        return {
            "status": "prospective_collecting_no_eligible_signal",
            "signals": {"evaluations": 3, "eligible_evaluations": 0},
        }

    monkeypatch.setattr(module, "snapshot_decision_ledger", snapshot)
    monkeypatch.setattr(module, "audit_cohort_observer_run", audit)
    monkeypatch.setattr(module, "build_observer_prospective_window", build)

    report = module.publish_window(_args(source, output))

    assert calls["source"] == source
    assert calls["audit"] == ([{"run_id": "run-a"}], "run-a")
    assert calls["build"] == (
        [{"run_id": "run-a"}],
        {"mode": "full-audit"},
        2_000,
    )
    assert report["evidence"] == {
        "path": str(source),
        "bytes": 12,
        "sha256": "a" * 64,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_publish_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    """Immutable evidence publication must reject an existing destination."""
    module = _load_script()
    output = tmp_path / "window.json"
    output.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="output exists"):
        module.publish_window(_args(tmp_path / "observer.jsonl", output))


def _args(source: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        decisions=source,
        run_id="run-a",
        start_ms=2_000,
        out=output,
    )


def _load_script() -> ModuleType:
    spec = spec_from_file_location("observer_window_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
