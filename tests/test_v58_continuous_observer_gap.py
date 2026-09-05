"""Observer-gap boundary for the V58 continuous diagnostics lane."""

from __future__ import annotations

import pytest

from hypervector.research.v58_continuous_improvement import (
    _require_observer_identity,
)

_HEARTBEAT_GAP = "observer_heartbeat_gap_exceeds_entry_delay"


def test_continuous_lane_accepts_reportable_observer_gap() -> None:
    """Measured cadence failure remains diagnosable but technically incomplete."""
    status = _status()
    status["technical_complete"] = False
    status["technical_gaps"] = [_HEARTBEAT_GAP]

    _require_observer_identity(status)


def test_continuous_lane_rejects_unknown_observer_gap() -> None:
    """A direct caller cannot bypass the exact reportable-gap contract."""
    status = _status()
    status["technical_complete"] = False
    status["technical_gaps"] = ["unknown_gap"]

    with pytest.raises(ValueError, match="technical state"):
        _require_observer_identity(status)


def _status() -> dict[str, object]:
    return {
        "profile_id": "multi_asset_growth_first_5000_eight_asset_incremental_v58",
        "freshness_status": "fresh",
        "technical_complete": True,
        "technical_gaps": [],
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
