"""Cutoff-bound HYPE rejected-onset path diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.v58_hype_rejected_onset_context import (
    build_hype_rejected_onset_context,
)

_RUN = "observe-v58"
_STRATEGY = "hype_breakout_compression_alignment_bidirectional_v2"


def test_rejected_onsets_report_causal_cost_adjusted_paths() -> None:
    """Rejected onsets remain counterfactual and are summarized after friction."""
    report = build_hype_rejected_onset_context(
        _records(),
        strategy_id=_STRATEGY,
        symbol="HYPE",
        prospective_start_ms=0,
        horizons_minutes=(5,),
        estimated_round_trip_friction_bps=13.0,
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["pnl_claimed"] is False
    assert report["rejected_fresh_onsets"] == 2
    assert report["breakout_side_relations"] == {"opposed": 2}
    horizon = report["horizons"]["5"]
    assert horizon["resolved"] == 2
    assert horizon["positive_directional_rate"] == 0.5
    assert horizon["mean_directional_close_return_bps"] == pytest.approx(0.0)
    assert horizon["mean_after_estimated_friction_bps"] == pytest.approx(-13.0)
    assert report["strategy_change_supported"] is False


def test_prospective_cutoff_excludes_earlier_onset() -> None:
    """A self-declared earlier evaluation cannot enter the prospective result."""
    report = build_hype_rejected_onset_context(
        _records(),
        strategy_id=_STRATEGY,
        symbol="HYPE",
        prospective_start_ms=600_000,
        horizons_minutes=(5,),
        estimated_round_trip_friction_bps=13.0,
    )

    assert report["rejected_fresh_onsets"] == 1
    assert report["first_decision_time_ms"] == 600_000
    assert report["horizons"]["5"][
        "mean_directional_close_return_bps"
    ] == pytest.approx(-200.0)


def test_onset_relation_must_be_explicit() -> None:
    """A fresh onset without exact relation telemetry is a technical failure."""
    records = _records()
    routing = records[1]["payload"]
    assert isinstance(routing, dict)
    evaluations = routing["evaluations"]
    assert isinstance(evaluations, list)
    readiness = evaluations[0]["readiness"]
    assert isinstance(readiness, dict)
    metrics = readiness["metrics"]
    assert isinstance(metrics, dict)
    metrics["breakout_side_relation"] = "unavailable"

    with pytest.raises(ValueError, match="fresh onset relation"):
        build_hype_rejected_onset_context(
            records,
            strategy_id=_STRATEGY,
            symbol="HYPE",
            prospective_start_ms=0,
            horizons_minutes=(5,),
            estimated_round_trip_friction_bps=13.0,
        )


def _records() -> list[dict[str, object]]:
    rows = [_row("configuration_identity", {}, 0)]
    rows.append(_routing(60_000, 61_000, 100.0))
    rows.append(_routing(600_000, 601_000, 100.0))
    bars = _bars(120_000, (100.0, 99.5, 99.0, 98.5, 98.0))
    bars.extend(_bars(660_000, (100.0, 100.5, 101.0, 101.5, 102.0)))
    rows.append(
        _row("market_candles", {"timeframe": "1m", "bars": {"HYPE": bars}}, 1_000_000)
    )
    return rows


def _routing(decision_ms: int, observed_ms: int, price: float) -> dict[str, object]:
    evaluation = {
        "strategy_id": _STRATEGY,
        "symbol": "HYPE",
        "decision_time_ms": decision_ms,
        "reference_price": price,
        "eligible": False,
        "reason": "authoritative_5m_compression_absent",
        "side": "short",
        "readiness": {
            "side": "short",
            "blockers": ["authoritative_5m_compression_absent"],
            "metrics": {
                "canonical_breakout_onset_fresh": True,
                "breakout_side": "long",
                "breakout_side_relation": "opposed",
            },
        },
    }
    return _row("intent_routing", {"evaluations": [evaluation]}, observed_ms)


def _bars(start_ms: int, closes: tuple[float, ...]) -> list[dict[str, object]]:
    return [
        {
            "timestamp_ms": start_ms + index * 60_000,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]


def _row(
    event_type: str, payload: dict[str, object], observed_ms: int
) -> dict[str, object]:
    return {
        "sequence": observed_ms + 1,
        "event_type": event_type,
        "observed_at_utc": datetime.fromtimestamp(
            observed_ms / 1_000, timezone.utc
        ).isoformat(),
        "run_id": _RUN,
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "v58",
        "profile_fingerprint": "fingerprint",
        "run_fingerprint": "run-fingerprint",
        "payload": payload,
    }
