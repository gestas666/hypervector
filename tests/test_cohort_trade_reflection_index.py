"""Causal completed-candle indexing across live recovery runs."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_trade_reflection_index import (
    build_reflection_evidence_index,
)


def _row(run_id: str, close: float) -> dict[str, object]:
    return {
        "event_type": "market_candles",
        "run_id": run_id,
        "payload": {
            "timeframe": "1m",
            "bars": {
                "BTC": [
                    {
                        "timestamp_ms": 1_785_600_000_000,
                        "open": 100.0,
                        "high": 101.0,
                        "low": 99.0,
                        "close": close,
                    }
                ]
            },
        },
    }


def _evaluation_row(
    run_id: str,
    regime: str,
    *,
    event_type: str = "intent_routing",
    strategy_id: str = "range_onset_bidirectional_v1",
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": run_id,
        "payload": {
            "evaluations": [
                {
                    "strategy_id": strategy_id,
                    "symbol": "BTC",
                    "decision_time_ms": 1_785_600_000_000,
                    "primary_regime": regime,
                }
            ]
        },
    }


def test_recovery_revision_preserves_first_causal_candle() -> None:
    """A later run cannot rewrite the completed candle seen by the first run."""
    evidence = build_reflection_evidence_index(
        [_row("live-run-1", 100.0), _row("recovery-run-2", 101.0)]
    )

    assert evidence.candles["BTC"][1_785_600_000_000].close == 100.0


def test_conflicting_candle_inside_one_run_still_fails_closed() -> None:
    """One live run cannot publish two incompatible completed candles."""
    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_reflection_evidence_index(
            [_row("live-run-1", 100.0), _row("live-run-1", 101.0)]
        )


def test_recovery_decision_revision_preserves_first_causal_timeline() -> None:
    """A recovery poll cannot rewrite a decision used by opposition history."""
    evidence = build_reflection_evidence_index(
        [
            _evaluation_row("live-run-1", "TREND_UP"),
            _evaluation_row("recovery-run-2", "TREND_DOWN"),
        ]
    )

    timeline = evidence.timelines[("range_onset_bidirectional_v1", "BTC")]
    assert len(timeline) == 1
    assert timeline[0]["primary_regime"] == "TREND_UP"


def test_independent_canonical_regime_events_are_indexed_for_reflections() -> None:
    """Trade journals retain canonical context after Range execution retires."""
    evidence = build_reflection_evidence_index(
        [
            _evaluation_row(
                "live-run-1",
                "TREND_UP",
                event_type="canonical_regime_evaluations",
                strategy_id="canonical_regime_telemetry_v1",
            )
        ]
    )

    assert (
        evidence.timelines[("canonical_regime_telemetry_v1", "BTC")][0][
            "primary_regime"
        ]
        == "TREND_UP"
    )
