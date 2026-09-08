"""Consumable log events for the report-only checkpoint sidecar."""

from collections.abc import Mapping
import json
import sys
from typing import TextIO

from hypervector.research.cohort_background_sync import BackgroundResearchSync


def log_background_sync(controller: BackgroundResearchSync) -> None:
    """Emit new messages while leaving durable import telemetry untouched."""
    report = controller.pop_report()
    if report is not None:
        emit_event("cohort_research_sync", {"result": report})
    error = controller.pop_error()
    if error is not None:
        print(f"cohort research sync failed: {error}", file=sys.stderr)


def emit_event(
    event: str, fields: Mapping[str, object], *, stream: TextIO | None = None
) -> None:
    """Write one flushed report-only JSON event, defaulting to the shared stderr log."""
    payload = {"event": event, "execution_authority": "none", **fields}
    print(
        json.dumps(payload, sort_keys=True),
        file=sys.stderr if stream is None else stream,
        flush=True,
    )
