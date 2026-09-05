"""Shared fail-closed technical-state contract for the V58 observer."""

from __future__ import annotations

from collections.abc import Mapping

_REPORTABLE_GAPS = ("observer_heartbeat_gap_exceeds_entry_delay",)


def require_reportable_v58_observer_status(
    status: Mapping[str, object], label: str
) -> None:
    """Accept complete evidence or one exact, explicitly incomplete cadence gap."""
    complete = status.get("technical_complete")
    gaps = status.get("technical_gaps")
    if complete is True and gaps is None:
        gaps = []
    valid_complete = complete is True and gaps == []
    valid_degraded = complete is False and gaps == list(_REPORTABLE_GAPS)
    if not (valid_complete or valid_degraded):
        raise ValueError(f"{label} technical state is invalid")
