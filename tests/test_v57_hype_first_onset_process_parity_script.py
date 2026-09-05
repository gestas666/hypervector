"""Tests for the frozen V57 first-onset process-parity command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import pytest

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "v57_hype_first_onset_process_parity.py"
)


def _module() -> object:
    if not SCRIPT.is_file():
        pytest.fail("V57 first-onset process-parity command is not implemented")
    name = "v57_hype_first_onset_process_parity"
    spec = spec_from_file_location(name, SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load V57 process-parity command")
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_source_specs_freeze_exact_live_and_two_observers() -> None:
    """The command must bind the three processes that saw the same onset."""
    specs = _module().source_specs()

    assert [(row.name, row.kind, row.run_id) for row in specs] == [
        ("v57_live", "live", "bidirectional-live-1787065473571"),
        (
            "native_long_observer",
            "observer",
            "bidirectional-observe-1787029740833",
        ),
        (
            "native_fixed8_observer",
            "observer",
            "bidirectional-observe-1787028309077",
        ),
    ]
    assert all(row.path.name == "decisions.jsonl" for row in specs)


def test_related_stop_path_must_identify_the_same_event(tmp_path: Path) -> None:
    """A mismatched counterfactual path cannot be linked to parity evidence."""
    related = tmp_path / "stop.json"
    related.write_text(
        json.dumps(
            {
                "contract": {"report_only": True, "execution_authority": "none"},
                "identity": {
                    "run_id": "wrong-run",
                    "strategy_id": "hype_breakout_compression_alignment_bidirectional_v2",
                    "symbol": "HYPE",
                    "decision_time_ms": 1787070000000,
                },
            }
        )
    )

    with pytest.raises(ValueError, match="related event identity"):
        _module().validate_related_event(related)
