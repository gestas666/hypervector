"""Secret-safe payload construction for terminal cohort runtime faults."""

from __future__ import annotations

from pathlib import Path


_VALID_FAILURE_STAGES = frozenset(
    {
        "account_reconciliation",
        "cycle_finalization",
        "entry_submission",
        "intent_polling",
        "operator_commands",
        "routing",
        "startup",
        "telemetry",
        "unclassified",
    }
)


def runtime_failure_stage(exc: BaseException) -> str:
    """Classify a terminal traceback without retaining values or messages."""
    stage = "unclassified"
    traceback = exc.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        stage = _frame_stage(Path(code.co_filename).name, code.co_name) or stage
        traceback = traceback.tb_next
    return stage


def runtime_fault_arguments(exc: BaseException) -> dict[str, str]:
    """Build compatible fault-emission arguments with a stage when known."""
    arguments = {"exception_type": type(exc).__name__}
    stage = runtime_failure_stage(exc)
    if stage != "unclassified":
        arguments["failure_stage"] = stage
    return arguments


def _frame_stage(filename: str, function: str) -> str | None:
    if filename == "multi_asset_live_runner_support.py" and function == (
        "reconcile_engines"
    ):
        return "account_reconciliation"
    if filename == "multi_asset_intent_poller.py":
        return "intent_polling"
    if filename == "cohort_route_cycle.py":
        return "routing"
    if filename == "cohort_entry_submission.py":
        return "entry_submission"
    if filename == "multi_asset_cohort_telemetry.py":
        return "telemetry"
    runner_stages = {
        "start": "startup",
        "_run_operator_commands": "operator_commands",
        "_finish_cycle": "cycle_finalization",
    }
    return (
        runner_stages.get(function)
        if filename == "multi_asset_live_runner.py"
        else None
    )


def runtime_fault_payload(
    exception_type: str,
    *,
    failure_stage: str | None = None,
) -> dict[str, object]:
    """Validate and encode only an exception class, never its message."""
    fault_type = exception_type.strip()
    valid = fault_type.replace("_", "").isalnum()
    if not fault_type or len(fault_type) > 128 or not valid:
        raise ValueError("runtime fault exception type is invalid")
    payload: dict[str, object] = {
        "status": "faulted",
        "exception_type": fault_type,
        "orders_attempted": False,
        "detail": "inspect backend process log",
    }
    if failure_stage is not None:
        if failure_stage not in _VALID_FAILURE_STAGES:
            raise ValueError("runtime fault failure stage is invalid")
        payload["failure_stage"] = failure_stage
    return payload
