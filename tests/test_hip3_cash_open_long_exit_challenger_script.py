"""Command tests for immutable SPCX long exit evidence."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_cash_open_long_exit_challenger.py"
_SPEC = spec_from_file_location("hip3_cash_open_long_exit_challenger_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
script = module_from_spec(_SPEC)
sys.path.insert(0, str(_SCRIPT.parent.resolve()))
try:
    _SPEC.loader.exec_module(script)
finally:
    sys.path.pop(0)


def test_parser_requires_preregistered_family() -> None:
    """Make the exact candidate declaration a required command input."""
    actions = {action.dest: action for action in script.build_parser()._actions}

    assert actions["preregistration"].required is True


def test_preregistration_rejects_candidate_or_authority_drift() -> None:
    """Fail closed if target values or report-only authority change."""
    payload = {
        "hypothesis_id": "V56_SPCX_LONG_EXIT_GIVEBACK_CHALLENGER_20260818_V1",
        "route": "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX|long",
        "challengers": [
            {"target_bps": 40.0},
            {"target_bps": 60.0},
            {"target_bps": 80.0},
        ],
        "frozen_scope": {
            "symbol": "xyz:SPCX",
            "direction": "long_only",
            "validation_accessed": False,
            "holdout_accessed": False,
        },
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "live_exit_change": False,
        },
    }
    assert script._validate_preregistration(payload) == (40.0, 60.0, 80.0)
    changed = {**payload, "challengers": [{"target_bps": 50.0}]}
    with pytest.raises(ValueError, match="target family"):
        script._validate_preregistration(changed)
    armed = {**payload, "authority": {**payload["authority"], "live_exit_change": True}}
    with pytest.raises(ValueError, match="authority"):
        script._validate_preregistration(armed)
