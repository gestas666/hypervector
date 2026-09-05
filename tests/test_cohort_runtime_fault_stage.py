"""Secret-safe runtime-fault stage attribution regressions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from hypervector.live.cohort_runtime_fault import runtime_fault_payload
from hypervector.live.multi_asset_live_runner_support import reconcile_engines
from test_multi_asset_bidirectional_live_script import _load_module
from test_multi_asset_cohort_telemetry import _telemetry


class _FailingReconciliationEngine:
    def reconcile_telemetry(
        self,
        *,
        funding_start_time_ms: int,
        funding_end_time_ms: int,
    ) -> object:
        raise ValueError("secret venue response detail")


class _FailingRunner:
    def run(self, *, max_polls: int | None) -> int:
        reconcile_engines(
            ("BTC",),
            {"BTC": _FailingReconciliationEngine()},
            funding_start_time_ms=0,
            funding_end_time_ms=1,
        )
        return 0


def test_runtime_fault_payload_records_allowlisted_stage_without_detail() -> None:
    """Fault evidence carries a stage but cannot leak exception text."""
    payload = runtime_fault_payload(
        "ValueError",
        failure_stage="account_reconciliation",
    )

    assert payload["failure_stage"] == "account_reconciliation"
    assert "secret" not in str(payload)


def test_runtime_fault_stage_is_persisted_by_telemetry(tmp_path: Path) -> None:
    """The durable runtime-fault row retains the classified failure stage."""
    telemetry, ledger = _telemetry(tmp_path)

    telemetry.emit_runtime_fault(
        exception_type="ValueError",
        failure_stage="account_reconciliation",
    )

    assert ledger.read_all()[0]["payload"]["failure_stage"] == (
        "account_reconciliation"
    )


def test_guarded_runner_classifies_account_reconciliation_failure() -> None:
    """The live boundary derives a useful stage from the real traceback."""
    live_script = _load_module()
    telemetry = Mock()

    with pytest.raises(ValueError, match="secret venue response detail"):
        live_script._run_guarded(_FailingRunner(), telemetry, max_polls=None)

    telemetry.emit_runtime_fault.assert_called_once_with(
        exception_type="ValueError",
        failure_stage="account_reconciliation",
    )
