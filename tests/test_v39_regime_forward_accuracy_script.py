"""Immutable CLI tests for exact v39 regime forward diagnostics."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

from test_v39_regime_forward_accuracy import _events, _identity

_SCRIPT = Path("scripts/v39_regime_forward_accuracy.py")
_RUN_ID = "v39-run"


def test_report_snapshots_exact_run_and_publishes_once(tmp_path: Path) -> None:
    """The report binds its stable live-ledger prefix and generator bytes."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    output = tmp_path / "accuracy.json"
    rows = [_identity(), *_events((100.0, 101.0, 102.0))]
    raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    ledger.write_bytes(raw)
    args = module.build_parser().parse_args(
        [
            "--ledger",
            str(ledger),
            "--run-id",
            _RUN_ID,
            "--horizons-minutes",
            "1",
            "--out",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.publish_report(output, report)

    persisted = json.loads(output.read_text())
    assert persisted["source"]["run_id"] == _RUN_ID
    assert persisted["evidence"]["ledger"]["sha256"] == sha256(raw).hexdigest()
    assert persisted["generator_identity"]["files"]
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(output, report)


def test_output_cannot_alias_live_ledger(tmp_path: Path) -> None:
    """A report cannot replace the source decision journal."""
    module = _module()
    ledger = tmp_path / "decisions.jsonl"
    args = module.build_parser().parse_args(
        [
            "--ledger",
            str(ledger),
            "--run-id",
            _RUN_ID,
            "--out",
            str(ledger),
        ]
    )

    with pytest.raises(ValueError, match="output must differ"):
        module.run_report(args)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v39 regime forward accuracy script is missing")
    spec = spec_from_file_location("v39_regime_forward_accuracy_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v39 regime forward accuracy script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
