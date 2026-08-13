"""Typed backend strategy-readiness contract tests."""

from __future__ import annotations

import pytest

from hypervector.live.provider_readiness import SignalReadiness


def test_readiness_exposes_progress_blockers_and_exact_indicators() -> None:
    """The TUI receives measured setup progress rather than inferring it."""
    readiness = SignalReadiness(
        side="long",
        conditions_met=4,
        conditions_required=6,
        blockers=("awaiting_squeeze_release", "volume_not_above_1x"),
        indicators=("ADX 21.4/18.0", "VOLUME 0.92x", "SQUEEZE ON"),
        metrics={
            "adx": 21.425,
            "volume_ratio": 0.9231,
            "squeeze_on": True,
        },
    )

    assert readiness.fraction == pytest.approx(2.0 / 3.0)
    assert readiness.as_payload() == {
        "side": "long",
        "conditions_met": 4,
        "conditions_required": 6,
        "readiness_fraction": pytest.approx(2.0 / 3.0),
        "blockers": ["awaiting_squeeze_release", "volume_not_above_1x"],
        "indicators": ["ADX 21.4/18.0", "VOLUME 0.92x", "SQUEEZE ON"],
        "metrics": {
            "adx": 21.425,
            "volume_ratio": 0.9231,
            "squeeze_on": True,
        },
    }


def test_readiness_rejects_success_shaped_unknown_conditions() -> None:
    """Missing indicator telemetry cannot appear as measured zero or ready."""
    with pytest.raises(ValueError, match="conditions_required"):
        SignalReadiness(
            side=None,
            conditions_met=0,
            conditions_required=0,
            blockers=("indicator_telemetry_unavailable",),
            indicators=(),
        )
