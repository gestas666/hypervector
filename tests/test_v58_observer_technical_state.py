"""Shared V58 observer technical-state contract."""

from __future__ import annotations

import pytest

from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

_GAP = "observer_heartbeat_gap_exceeds_entry_delay"


@pytest.mark.parametrize(
    "status",
    (
        {"technical_complete": True},
        {"technical_complete": True, "technical_gaps": []},
        {"technical_complete": False, "technical_gaps": [_GAP]},
    ),
)
def test_accepts_complete_or_exact_reportable_gap(status: dict[str, object]) -> None:
    """Known cadence degradation remains observable without claiming completeness."""
    require_reportable_v58_observer_status(status, "test observer")


@pytest.mark.parametrize(
    "status",
    (
        {"technical_complete": False, "technical_gaps": []},
        {"technical_complete": True, "technical_gaps": [_GAP]},
        {"technical_complete": False, "technical_gaps": ["unknown_gap"]},
        {"technical_complete": False, "technical_gaps": _GAP},
    ),
)
def test_rejects_contradictory_or_unknown_gap(status: dict[str, object]) -> None:
    """Malformed or undeclared gaps cannot enter downstream diagnostics."""
    with pytest.raises(ValueError, match="technical state"):
        require_reportable_v58_observer_status(status, "test observer")
