"""Command contracts for immutable SPCX long entry diagnosis."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_cash_open_long_entry_diagnosis.py"
_SPEC = spec_from_file_location("hip3_cash_open_long_entry_diagnosis_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
script = module_from_spec(_SPEC)
sys.path.insert(0, str(_SCRIPT.parent.resolve()))
try:
    _SPEC.loader.exec_module(script)
finally:
    sys.path.pop(0)


def test_parser_requires_preregistration() -> None:
    actions = {action.dest: action for action in script.build_parser()._actions}

    assert actions["preregistration"].required is True


def test_preregistration_rejects_scope_feature_or_authority_drift() -> None:
    payload = _preregistration()

    script._validate_preregistration(payload)
    changed = {
        **payload,
        "causal_feature_contract": payload["causal_feature_contract"][:-1],
    }
    with pytest.raises(ValueError, match="feature contract"):
        script._validate_preregistration(changed)
    searched = {
        **payload,
        "frozen_scope": {**payload["frozen_scope"], "threshold_search": True},
    }
    with pytest.raises(ValueError, match="scope"):
        script._validate_preregistration(searched)


def test_report_contract_satisfies_shared_immutable_publisher() -> None:
    report = script._report_contract()

    script.cash_open.session.base._require_report_only(report)


def _preregistration() -> dict[str, object]:
    features = [
        "opening_gap_bps",
        "opening_reversal_bps",
        "gap_recovery_fraction",
        "decision_spread_bps",
        "decision_imbalance_10",
        "public_trade_count",
        "signal_volume",
        "source_snapshot_count",
    ]
    return {
        "hypothesis_id": "V56_SPCX_LONG_ENTRY_QUALITY_DIAGNOSIS_20260818_V1",
        "route": "hip3_spcx_cash_open_gap_reversal_bidirectional_15m_v1|xyz:SPCX|long",
        "frozen_scope": {
            "symbol": "xyz:SPCX",
            "timeframe": "15m",
            "direction": "long_only",
            "validation_accessed": False,
            "holdout_accessed": False,
            "outcome_based_entry_exclusion": False,
            "threshold_search": False,
        },
        "causal_feature_contract": [
            {"name": name, "available_at_decision": True} for name in features
        ],
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_promotion": False,
            "live_change": False,
            "approval_requested": False,
        },
    }
