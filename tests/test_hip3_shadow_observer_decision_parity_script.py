"""Immutable CLI tests for HIP-3 observer decision parity."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

from test_hip3_shadow_observer_decision_parity import _observer_row, _signal_report

_SCRIPT = Path("scripts/hip3_shadow_observer_decision_parity.py")


def test_report_binds_signal_artifact_and_stable_observer_prefix(
    tmp_path: Path,
) -> None:
    module = _module()
    signal_path = tmp_path / "signal.json"
    journal_path = tmp_path / "observer.jsonl"
    output = tmp_path / "parity.json"
    signal_path.write_text(json.dumps(_signal_report(entry_side=None)))
    rows = [
        _observer_row(2_700_000, eligible=False, side=None),
        _observer_row(3_600_000, eligible=True, side="long"),
    ]
    raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    journal_path.write_bytes(raw)
    args = module.build_parser().parse_args(
        [
            "--signal-parity",
            str(signal_path),
            "--observer-journal",
            str(journal_path),
            "--output",
            str(output),
        ]
    )

    report = module.run_report(args)
    module.publish_report(output, report)

    persisted = json.loads(output.read_text())
    assert persisted["technical_assessment"]["pressure_decision_mismatches"] == 1
    assert (
        persisted["input_evidence"]["observer_journal"]["sha256"]
        == sha256(raw).hexdigest()
    )
    assert persisted["input_evidence"]["signal_parity"]["path"] == str(
        signal_path.resolve()
    )
    assert persisted["generator_identity"]["files"]
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.publish_report(output, report)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("HIP-3 observer decision parity script is missing")
    spec = spec_from_file_location(
        "hip3_shadow_observer_decision_parity_script", _SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load HIP-3 observer decision parity script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
