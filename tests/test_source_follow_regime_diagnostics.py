"""Behavior-neutral diagnostics for the pinned source-follow classifier."""

from __future__ import annotations

from datetime import UTC, datetime

from hypervector.live.source_follow_live_telemetry import SourceFollowLiveTelemetry
from hypervector.regime.source_follow_runtime import (
    FiveMinuteBar,
    SourceFollowRuntime,
    SourceRegimeLabel,
)
from hypervector.regime.source_regime_diagnostics import (
    build_source_regime_diagnostics,
)


class _DiagnosticClassifier:
    def classify(self, bar: FiveMinuteBar) -> SourceRegimeLabel:
        diagnostics = build_source_regime_diagnostics(
            raw_primary="TREND_DOWN",
            raw_secondary=None,
            raw_confidence=0.8,
            indicators={
                "adx": 12.5,
                "adx_rank": 0.31,
                "ema_alignment": "bearish",
                "rsi": 48.0,
                "volume_ratio": 0.8,
                "range_break_up": False,
                "range_break_down": False,
            },
            adx_range_percentile_threshold=0.4,
            adx_weak_percentile_threshold=0.5,
        )
        return SourceRegimeLabel(
            label_time_utc=bar.timestamp_utc,
            primary="RANGE",
            secondary="RG_TIGHT_LOW_VOL",
            confidence=0.55,
            diagnostics=diagnostics,
        )


def test_runtime_preserves_diagnostics_without_changing_entry_decision() -> None:
    """Raw diagnostics must remain telemetry and cannot grant entry authority."""
    runtime = SourceFollowRuntime(
        _DiagnosticClassifier(),
        direction_mode="source_follow_bidirectional",
    )

    decision = runtime.update(_bar())

    assert decision.primary == "RANGE"
    assert decision.entry_eligible is False
    assert decision.entry_direction is None
    assert decision.regime_diagnostics is not None
    assert decision.regime_diagnostics.raw_primary == "TREND_DOWN"
    emitted = SourceFollowLiveTelemetry._regime_diagnostics(decision)
    assert emitted is not None
    assert emitted["authority"] == "telemetry_only"
    assert emitted["confirmed_primary"] == "RANGE"


def test_diagnostic_payload_exposes_raw_confirmed_divergence() -> None:
    """An operator must be able to distinguish raw output from hysteresis output."""
    label = _DiagnosticClassifier().classify(_bar())
    assert label.diagnostics is not None

    payload = label.diagnostics.to_dict(confirmed_primary=label.primary)

    assert payload == {
        "authority": "telemetry_only",
        "raw_primary": "TREND_DOWN",
        "raw_secondary": None,
        "raw_confidence": 0.8,
        "confirmed_primary": "RANGE",
        "state_filtered": True,
        "adx": 12.5,
        "adx_percentile_rank": 0.31,
        "adx_range_percentile_threshold": 0.4,
        "adx_weak_percentile_threshold": 0.5,
        "ema_alignment": "bearish",
        "rsi": 48.0,
        "volume_ratio": 0.8,
        "range_break_up": False,
        "range_break_down": False,
    }


def _bar() -> FiveMinuteBar:
    return FiveMinuteBar(
        timestamp_utc=datetime(2026, 7, 31, 21, 15, tzinfo=UTC),
        open=62_984.0,
        high=63_000.0,
        low=62_979.0,
        close=62_980.0,
        volume=114.93658,
    )
