"""Tests for the immutable BTC option-flow candle source audit command."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


_SCRIPT = Path("scripts/v58_btc_option_flow_candle_audit.py")


def test_candle_audit_script_exists() -> None:
    """The source revision requires a reproducible audit entry point."""
    assert _SCRIPT.is_file()


def test_report_is_outcome_blind_and_cannot_authorize_live_changes() -> None:
    """Cadence registration must not claim economic or deployment authority."""
    module = _load_module()
    broad = _record("original_v1", False, 1_752, 875)
    revised = _record("outcome_blind_v2", True, 160, 23)

    report = module.build_report(
        recorded_at_utc="2026-08-22T08:00:00Z",
        broad=broad,
        revised=revised,
        revised_repair_count=160,
    )

    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["live_change_authorized"] is False
    assert report["outcome_blindness"]["candidate_trade_outcomes_inspected"] is False
    assert report["original_source"]["audit"]["contract_pass"] is False
    assert report["revised_source"]["audit"]["contract_pass"] is True
    assert report["revised_source"]["deterministic_gap_fill_count"] == 160


def _record(
    revision: str, passed: bool, missing: int, maximum: int
) -> dict[str, object]:
    return {
        "source_revision": revision,
        "expected_contract_pass": passed,
        "audit": {
            "contract_pass": passed,
            "missing_rows": missing,
            "maximum_gap_minutes": maximum,
        },
    }


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("btc_option_candle_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
