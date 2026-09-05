"""Prospective status for the first V58 SP500 fresh15 lifecycle."""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from hypervector.research.sp500_fresh15_lifecycle_watch import (
    build_sp500_fresh15_lifecycle_status,
)


_DECISION_MS = 1_787_120_100_000
_ENTRY_MS = 1_787_120_101_436


def test_sp500_lifecycle_watch_module_exists() -> None:
    """The report-only watcher logic must have a dedicated module."""
    assert find_spec("hypervector.research.sp500_fresh15_lifecycle_watch") is not None


def test_open_lifecycle_remains_censored_without_configured_trigger() -> None:
    """Fresh unfinished evidence must never become a completed PnL result."""
    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short")],
        _candles([7675.9, 7678.0, 7679.0]),
        observed_at_ms=_DECISION_MS + 185_000,
    )

    assert status["watch_state"] == "OPEN_LIFECYCLE_CENSORED"
    assert status["lifecycle_replay_candidate_due"] is False
    assert status["trigger_reasons"] == []
    assert status["source"] == {"observed_decisions": 1, "eligible_decisions": 1}
    assert status["lifecycle"] == {
        "side": "short",
        "decision_time_ms": _DECISION_MS,
        "entry_time_ms": _ENTRY_MS,
        "entry_price": 7675.6,
        "stop_price": 7737.0048,
    }
    assert status["nominal"]["summary"] == {
        "resolved": 0,
        "censored": 1,
        "modeled_net_usd_excluding_funding": 0.0,
    }
    assert status["stress"] == status["nominal"]
    assert status["path"]["completed_candles"] == 3
    assert status["path"]["profit_lock_activated"] is False
    assert status["technical_assessment"]["live_change_supported"] is False
    assert status["execution_authority"] == "none"
    assert status["orders_supported"] is False


def test_stop_candidate_makes_exact_replay_due() -> None:
    """A completed candle crossing the frozen stop must request exact replay."""
    candles = _candles([7675.9, 7678.0])
    candles[1]["high"] = 7738.0

    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short")],
        candles,
        observed_at_ms=_DECISION_MS + 125_000,
    )

    assert status["watch_state"] == "LIFECYCLE_REPLAY_CANDIDATE_DUE"
    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["protective_stop_candidate"]


def test_opposite_eligible_intent_makes_exact_replay_due() -> None:
    """The frozen router's opposite side must request lifecycle resolution."""
    later = _decision(eligible=True, side="long", offset_ms=900_000)

    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short"), later],
        _candles([7679.0] * 16),
        observed_at_ms=_DECISION_MS + 965_000,
    )

    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["opposite_eligible_intent"]


def test_completed_bar_profit_lock_makes_exact_replay_due() -> None:
    """Activation followed by a causal giveback must request exact replay."""
    candles = _candles([7590.0, 7580.0, 7650.0])

    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short")],
        candles,
        observed_at_ms=_DECISION_MS + 185_000,
    )

    assert status["path"]["profit_lock_activated"] is True
    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["completed_bar_profit_lock"]


def test_stale_candle_capture_makes_technical_replay_due() -> None:
    """An open lifecycle must not look healthy after its source stops advancing."""
    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short")],
        _candles([7675.9]),
        observed_at_ms=_DECISION_MS + 300_000,
    )

    assert status["path"]["source_stale"] is True
    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["profit_lock_source_stale"]


def test_maximum_hold_elapsed_makes_exact_replay_due() -> None:
    """The frozen 24-hour fallback boundary must be represented generically."""
    preregistration = _preregistration()
    preregistration["maximum_hold_minutes"] = 3

    status = build_sp500_fresh15_lifecycle_status(
        preregistration,
        [_decision(eligible=True, side="short")],
        _candles([7675.9, 7678.0, 7679.0]),
        observed_at_ms=_DECISION_MS + 185_000,
    )

    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["maximum_hold_elapsed"]


def test_candle_gap_makes_technical_replay_due() -> None:
    """Missing completed minutes must become an explicit evidence failure."""
    preregistration = _preregistration()
    preregistration["maximum_candle_age_ms"] = 300_000
    candles = _candles([7675.9, 7678.0, 7679.0])
    candles.pop(1)

    status = build_sp500_fresh15_lifecycle_status(
        preregistration,
        [_decision(eligible=True, side="short")],
        candles,
        observed_at_ms=_DECISION_MS + 185_000,
    )

    assert status["path"]["source_gap"] is True
    assert status["lifecycle_replay_candidate_due"] is True
    assert status["trigger_reasons"] == ["profit_lock_source_gap"]


def test_recovery_backfill_does_not_invalidate_prospective_prefix() -> None:
    """Explicit retrospective recovery rows are not lifecycle evidence."""
    candles = _candles([7675.9, 7678.0, 7679.0])
    recovery = dict(candles[1])
    recovery["prospective"] = False
    candles.append(recovery)

    status = build_sp500_fresh15_lifecycle_status(
        _preregistration(),
        [_decision(eligible=True, side="short")],
        candles,
        observed_at_ms=_DECISION_MS + 185_000,
    )

    assert status["watch_state"] == "OPEN_LIFECYCLE_CENSORED"
    assert status["path"]["completed_candles"] == 3
    assert status["path"]["source_gap"] is False


def test_missing_first_candle_is_rejected_with_actionable_error() -> None:
    """A late-started journal cannot establish a causal lifecycle prefix."""
    candles = _candles([7675.9, 7678.0])
    candles.pop(0)

    with pytest.raises(ValueError, match="first completed profit-lock candle"):
        build_sp500_fresh15_lifecycle_status(
            _preregistration(),
            [_decision(eligible=True, side="short")],
            candles,
            observed_at_ms=_DECISION_MS + 125_000,
        )


def test_duplicate_decision_boundary_is_rejected() -> None:
    """Repeated decision rows must not inflate opportunity or trigger counts."""
    later = _decision(eligible=True, side="long", offset_ms=900_000)

    with pytest.raises(ValueError, match="duplicate decision boundary"):
        build_sp500_fresh15_lifecycle_status(
            _preregistration(),
            [_decision(eligible=True, side="short"), later, dict(later)],
            _candles([7679.0] * 16),
            observed_at_ms=_DECISION_MS + 965_000,
        )


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v58_sp500_fresh15_lifecycle_watch_preregistration_v1",
        "status": "prospective_collecting",
        "symbol": "xyz:SP500",
        "provider_id": "fresh15-v3",
        "profile_id": "sp500-shadow-v3",
        "event": {
            "decision_time_ms": _DECISION_MS,
            "entry_time_ms": _ENTRY_MS,
            "side": "short",
            "entry_price": 7675.6,
            "stop_price": 7737.0048,
        },
        "profit_lock": {
            "policy_id": "v58_hip3_sp500_100_40_80",
            "activation_bps": 100.0,
            "floor_bps": 40.0,
            "trailing_giveback_bps": 80.0,
        },
        "maximum_hold_minutes": 1440,
        "maximum_candle_age_ms": 120_000,
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _decision(
    *, eligible: bool, side: str | None, offset_ms: int = 0
) -> dict[str, object]:
    return {
        "event_type": "sp500_hip3_breakout_shadow_decision",
        "execution_authority": "none",
        "decision": {
            "symbol": "xyz:SP500",
            "provider_id": "fresh15-v3",
            "profile_id": "sp500-shadow-v3",
            "decision_time_ms": _DECISION_MS + offset_ms,
            "observed_at_ms": _ENTRY_MS + offset_ms,
            "eligible": eligible,
            "side": side,
            "prospective": True,
            "execution_authority": "none",
        },
    }


def _candles(closes: list[float]) -> list[dict[str, object]]:
    rows = []
    for index, close in enumerate(closes):
        open_ms = _DECISION_MS + index * 60_000
        rows.append(
            {
                "event_type": (
                    "sp500_hip3_breakout_shadow_profit_lock_candle_observation"
                ),
                "symbol": "xyz:SP500",
                "bar_open_ms": open_ms,
                "bar_close_ms": open_ms + 60_000,
                "observed_at_ms": open_ms + 61_000,
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "source": "hyperliquid_public_candleSnapshot_1m",
                "prospective": True,
                "execution_authority": "none",
            }
        )
    return rows
