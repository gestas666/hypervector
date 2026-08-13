"""Causal report-only evidence for provider exits ignored by live policy."""

from dataclasses import dataclass

import pytest

from hypervector.research.cohort_ignored_provider_exit import (
    build_ignored_provider_exit_observer,
)


@dataclass(frozen=True)
class _Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def test_observer_selects_first_post_entry_same_side_exit() -> None:
    """Pre-entry, future, and opposite-side signals cannot contaminate the path."""
    evidence = build_ignored_provider_exit_observer(
        (
            _evaluation(60_000, 100.5, ("long",)),
            _evaluation(120_000, 99.0, ("short",)),
            _evaluation(180_000, 99.0, ("long",)),
            _evaluation(240_000, 99.2, ("long",)),
            _evaluation(420_000, 98.0, ("long",)),
        ),
        {
            240_000: _bar(240_000, 99.2, 99.7, 99.1, 99.6),
            300_000: _bar(300_000, 99.6, 99.8, 99.4, 99.5),
        },
        side="long",
        entry={"venue_timestamp_ms": 100_000, "price": 100.0},
        marked_economics={"mark_price": 99.5},
        exit_plan={"provider_recipe_exit_policy": "ignore"},
        as_of_ms=360_000,
    )

    assert evidence["status"] == "observed"
    assert evidence["first_signal"]["decision_time_ms"] == 180_000
    assert evidence["first_signal"]["reference_price"] == 99.0
    assert evidence["first_signal"]["entry_directional_return_bps"] == pytest.approx(
        -100.0
    )
    assert evidence["ignored_signal_count"] == 2
    path = evidence["path_since_first_signal"]
    assert path["completed_bars"] == 2
    assert path["current_directional_return_bps"] == pytest.approx(
        (99.5 / 99.0 - 1.0) * 10_000.0
    )


def test_observer_reports_absence_without_inventing_a_path() -> None:
    """No eligible ignored signal must remain explicit rather than success-shaped."""
    evidence = build_ignored_provider_exit_observer(
        (_evaluation(120_000, 99.0, ("short",)),),
        {},
        side="long",
        entry={"venue_timestamp_ms": 100_000, "price": 100.0},
        marked_economics={"mark_price": 100.5},
        exit_plan={"provider_recipe_exit_policy": "ignore"},
        as_of_ms=180_000,
    )

    assert evidence["status"] == "no_ignored_exit_observed"
    assert evidence["first_signal"] is None
    assert evidence["path_since_first_signal"] is None


def test_observer_is_not_applicable_when_policy_honors_recipe_exit() -> None:
    """An executable recipe signal cannot be mislabeled as ignored evidence."""
    evidence = build_ignored_provider_exit_observer(
        (_evaluation(120_000, 99.0, ("long",)),),
        {},
        side="long",
        entry={"venue_timestamp_ms": 100_000, "price": 100.0},
        marked_economics={"mark_price": 99.0},
        exit_plan={"provider_recipe_exit_policy": "honor"},
        as_of_ms=180_000,
    )

    assert evidence["status"] == "not_applicable_policy_honors"
    assert evidence["ignored_signal_count"] == 0


def test_observer_rejects_malformed_exit_sides() -> None:
    """Malformed source telemetry must fail rather than disappear silently."""
    malformed = _evaluation(120_000, 99.0, ("long",))
    malformed["exit_sides"] = "long"

    with pytest.raises(ValueError, match="exit_sides"):
        build_ignored_provider_exit_observer(
            (malformed,),
            {},
            side="long",
            entry={"venue_timestamp_ms": 100_000, "price": 100.0},
            marked_economics={"mark_price": 99.0},
            exit_plan={"provider_recipe_exit_policy": "ignore"},
            as_of_ms=180_000,
        )


def _evaluation(
    decision_time_ms: int,
    reference_price: float,
    exit_sides: tuple[str, ...],
) -> dict[str, object]:
    return {
        "strategy_id": "hip3_swing",
        "symbol": "xyz:GOLD",
        "decision_time_ms": decision_time_ms,
        "reference_price": reference_price,
        "decision_action": "close_long",
        "eligible": False,
        "reason": "hip3_swing_ha_flip",
        "side": "long",
        "exit_sides": list(exit_sides),
        "exit_reason": "hip3_swing_ha_flip",
        "readiness": {
            "conditions_met": 2,
            "conditions_required": 4,
            "blockers": ["heikin_ashi_color_mismatch"],
        },
    }


def _bar(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> _Candle:
    return _Candle(timestamp_ms, open_price, high, low, close)
