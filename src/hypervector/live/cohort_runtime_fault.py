"""Secret-safe payload construction for terminal cohort runtime faults."""

from __future__ import annotations


def runtime_fault_payload(exception_type: str) -> dict[str, object]:
    """Validate and encode only an exception class, never its message."""
    fault_type = exception_type.strip()
    valid = fault_type.replace("_", "").isalnum()
    if not fault_type or len(fault_type) > 128 or not valid:
        raise ValueError("runtime fault exception type is invalid")
    return {
        "status": "faulted",
        "exception_type": fault_type,
        "orders_attempted": False,
        "detail": "inspect backend process log",
    }
