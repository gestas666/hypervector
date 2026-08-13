"""Report-only aligned timer-extension observer tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_aligned_timer_extension import (
    build_aligned_timer_extension_observer,
)


def test_aligned_zero_opposition_timer_exit_is_observed_for_five_minutes() -> None:
    """Aligned 15m context with complete zero-opposition evidence is eligible."""
    observer = build_aligned_timer_extension_observer([_trade()], horizon_minutes=5)

    assert observer["contract"]["execution_authority"] == "none"
    assert observer["policy"] == {
        "horizon_minutes": 5,
        "requires_15m_context_alignment": True,
        "requires_complete_zero_opposition": True,
        "retains_protective_stop": True,
    }
    assert observer["decisions"] == {
        "timer_exits": 1,
        "eligible": 1,
        "ineligible": 0,
        "by_reason": {"eligible": 1},
    }
    assert observer["horizon"] == {
        "eligible_extensions": 1,
        "resolved": 1,
        "positive": 1,
        "negative": 0,
        "unchanged": 0,
        "protective_stop_hits": 0,
        "censored": 0,
        "missing_data": 0,
        "incremental_gross_pnl_usd": pytest.approx(0.36),
    }
    assert observer["latest_observations"][0]["opposed_decisions"] == 0
    assert observer["latest_observations"][0]["directional_close_return_bps"] == 18.0


@pytest.mark.parametrize(
    ("context_15m", "opposed", "coverage_gaps", "expected_reason"),
    [
        ("TREND_UP", 0, 0, "context_15m_not_aligned"),
        ("TREND_DOWN", 1, 0, "opposition_observed"),
        ("TREND_DOWN", 0, 1, "opposition_coverage_incomplete"),
    ],
)
def test_observer_rejects_unaligned_or_contested_timer_exits(
    context_15m: str,
    opposed: int,
    coverage_gaps: int,
    expected_reason: str,
) -> None:
    """The frozen observer cannot silently broaden its eligibility contract."""
    trade = _trade(
        context_15m=context_15m,
        opposed_decisions=opposed,
        coverage_gap_decisions=coverage_gaps,
    )

    observer = build_aligned_timer_extension_observer([trade], horizon_minutes=5)

    assert observer["decisions"]["eligible"] == 0
    assert observer["decisions"]["by_reason"] == {expected_reason: 1}
    assert observer["horizon"]["resolved"] == 0


def test_observer_retains_the_original_venue_stop() -> None:
    """A stop touch overrides a favorable five-minute closing candle."""
    trade = _trade(stop_price=101.0, highest_price=102.0)

    observer = build_aligned_timer_extension_observer([trade], horizon_minutes=5)

    assert observer["horizon"]["protective_stop_hits"] == 1
    assert observer["horizon"]["negative"] == 1
    assert observer["horizon"]["incremental_gross_pnl_usd"] == pytest.approx(-2.0)


def test_observer_keeps_censored_paths_out_of_resolved_economics() -> None:
    """An unavailable future candle is not converted into a zero-return result."""
    trade = _trade()
    trade["post_exit_path"]["5"] = {"status": "censored"}

    observer = build_aligned_timer_extension_observer([trade], horizon_minutes=5)

    assert observer["horizon"]["eligible_extensions"] == 1
    assert observer["horizon"]["censored"] == 1
    assert observer["horizon"]["resolved"] == 0


def test_non_timer_exit_is_outside_observer_scope() -> None:
    """The observer cannot become a general exit-rewrite challenger."""
    trade = _trade()
    trade["exit_reason"] = "protective_stop"

    observer = build_aligned_timer_extension_observer([trade], horizon_minutes=5)

    assert observer["decisions"]["timer_exits"] == 0
    assert observer["decisions"]["eligible"] == 0
    assert observer["latest_observations"] == []


def _trade(
    *,
    context_15m: str = "TREND_DOWN",
    opposed_decisions: int = 0,
    coverage_gap_decisions: int = 0,
    stop_price: float = 101.5,
    highest_price: float = 100.5,
) -> dict[str, object]:
    return {
        "lifecycle_id": "SOL:1",
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "SOL",
        "side": "short",
        "exit_reason": "maximum_hold_seconds",
        "exit": {"price": 100.0, "size": 2.0, "venue_timestamp_ms": 10_000},
        "protective_stop": {"oid": 99, "trigger_price": stop_price},
        "exit_context": {"signal_provider": {"context_15m": context_15m}},
        "regime_opposition_episode": {
            "mode": "causal_regime_opposition_persistence_v1",
            "completed_decisions": 20,
            "opposed_decisions": opposed_decisions,
            "maximum_consecutive_opposed": opposed_decisions,
            "coverage_gap_decisions": coverage_gap_decisions,
            "unavailable_decisions": 0,
        },
        "post_exit_path": {
            "5": {
                "status": "resolved",
                "directional_close_return_bps": 18.0,
                "favorable_excursion_bps": 20.0,
                "adverse_excursion_bps": 5.0,
                "lowest_price": 99.7,
                "highest_price": highest_price,
            }
        },
    }
