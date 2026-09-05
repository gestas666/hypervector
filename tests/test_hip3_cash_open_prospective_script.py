"""Tests for immutable prospective cash-open report orchestration."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_SCRIPT = Path("scripts/hip3_cash_open_prospective.py")


def _script():
    spec = spec_from_file_location("hip3_cash_open_prospective_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("prospective cash-open script cannot be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconcile_accepts_exact_audit_trade_prefix() -> None:
    """The report must bind the same receipt-causal trade prefix as the audit."""
    script = _script()
    report = {"source": {"raw_trade_rows": 3, "raw_trade_sha256": "abc"}}
    audit = {
        "evidence_identity": {"completed_bar_trades": {"rows": 3, "sha256": "abc"}}
    }
    script._reconcile_audit(report, audit)


def test_reconcile_rejects_audit_trade_prefix_mismatch() -> None:
    """A different source prefix must abort before publication."""
    script = _script()
    report = {"source": {"raw_trade_rows": 3, "raw_trade_sha256": "abc"}}
    audit = {
        "evidence_identity": {"completed_bar_trades": {"rows": 4, "sha256": "changed"}}
    }
    with pytest.raises(ValueError, match="trade prefix differs"):
        script._reconcile_audit(report, audit)
