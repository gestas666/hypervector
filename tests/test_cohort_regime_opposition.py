"""Causal regime-opposition persistence tests."""

from __future__ import annotations

import pytest

from hypervector.research import cohort_regime_opposition
from hypervector.research.cohort_regime_opposition import (
    build_regime_opposition_episode,
    build_regime_opposition_outcome_challenger,
)


def test_opposition_episode_reports_fixed_persistence_without_exit_authority() -> None:
    """One, three, and five-decision triggers remain descriptive evidence."""
    provider = [
        _evaluation(60_000, "TREND_UP"),
        _evaluation(120_000, "TREND_DOWN"),
        _evaluation(180_000, "TREND_DOWN"),
        _evaluation(240_000, "TREND_DOWN"),
        _evaluation(300_000, "TREND_UP"),
        _evaluation(360_000, "TREND_DOWN"),
    ]

    episode = build_regime_opposition_episode(
        "long",
        provider,
        provider,
        entry_timestamp_ms=30_000,
        end_timestamp_ms=400_000,
    )

    assert episode["contract"]["execution_authority"] == "none"
    assert episode["completed_decisions"] == 6
    assert episode["opposed_decisions"] == 4
    assert episode["first_opposed_decision_ms"] == 120_000
    assert episode["maximum_consecutive_opposed"] == 3
    assert episode["current_consecutive_opposed"] == 1
    assert episode["current_active"] is True
    assert episode["persistence_triggers"] == {
        "1": 120_000,
        "3": 240_000,
        "5": None,
    }


def test_opposition_episode_breaks_persistence_across_missing_decisions() -> None:
    """Runtime gaps cannot masquerade as continuous contrary evidence."""
    provider = [
        _evaluation(60_000, "TREND_DOWN"),
        _evaluation(180_000, "TREND_DOWN"),
    ]

    episode = build_regime_opposition_episode(
        "long",
        provider,
        provider,
        entry_timestamp_ms=0,
        end_timestamp_ms=200_000,
    )

    assert episode["coverage_gap_decisions"] == 1
    assert episode["maximum_consecutive_opposed"] == 1
    assert episode["persistence_triggers"]["3"] is None


def test_opposition_episode_rejects_conflicting_duplicate_decisions() -> None:
    """Overlapping run evidence must not be selected silently."""
    provider = [
        _evaluation(60_000, "TREND_UP"),
        _evaluation(60_000, "TREND_DOWN"),
    ]

    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_regime_opposition_episode(
            "long",
            provider,
            provider[:1],
            entry_timestamp_ms=0,
            end_timestamp_ms=120_000,
        )


def test_support_decay_requires_five_contiguous_weak_decisions() -> None:
    """Mixed structure must persist before it can arm a report-only profit lock."""
    builder = getattr(
        cohort_regime_opposition, "build_regime_support_decay_episode", None
    )
    assert callable(builder), "support-decay episode builder is not implemented"
    provider = [
        _evaluation(60_000, "TREND_UP"),
        _evaluation(120_000, "RANGE"),
        _evaluation(180_000, "RANGE"),
        _evaluation(240_000, "RANGE"),
        _evaluation(300_000, "RANGE"),
        _evaluation(360_000, "RANGE"),
    ]

    episode = builder(
        "long",
        provider,
        provider,
        entry_timestamp_ms=30_000,
        end_timestamp_ms=400_000,
    )

    assert episode["mode"] == "causal_regime_support_decay_persistence_v1"
    assert episode["contract"]["execution_authority"] == "none"
    assert episode["support_decay_threshold"] == pytest.approx(0.25)
    assert episode["persistence_decisions"] == [5]
    assert episode["decayed_decisions"] == 5
    assert episode["maximum_consecutive_decayed"] == 5
    assert episode["persistence_triggers"] == {"5": 360_000}


def test_opposition_outcomes_remain_partitioned_by_provider_and_persistence() -> None:
    """Resolved after-cost outcomes challenge rather than authorize early exits."""
    trades = [
        _trade(1.0, trigger_five=240_000),
        _trade(-0.5, trigger_five=None),
    ]

    challenger = build_regime_opposition_outcome_challenger(trades)

    assert challenger["contract"]["execution_authority"] == "none"
    provider = challenger["provider_symbols"][0]
    assert provider["strategy_id"] == "provider"
    assert provider["symbol"] == "BTC"
    five = next(
        row
        for row in provider["persistence_results"]
        if row["persistence_decisions"] == 5
    )
    assert five["triggered_performance"]["closed_trades"] == 1
    assert five["triggered_performance"]["wins"] == 1
    assert five["triggered_performance"]["net_pnl_usd"] == 1.0
    assert five["not_triggered_performance"]["closed_trades"] == 1
    assert five["not_triggered_performance"]["losses"] == 1
    assert five["not_triggered_performance"]["net_pnl_usd"] == -0.5


def _evaluation(timestamp_ms: int, state: str) -> dict[str, object]:
    return {
        "strategy_id": "provider",
        "symbol": "BTC",
        "decision_time_ms": timestamp_ms,
        "primary_regime": state,
        "state_1m": state,
        "state_5m": state,
        "context_15m": state,
        "confidence": 0.8,
    }


def _trade(net_pnl_usd: float, *, trigger_five: int | None) -> dict[str, object]:
    triggers = {"1": 120_000, "3": 180_000, "5": trigger_five}
    return {
        "strategy_id": "provider",
        "symbol": "BTC",
        "net_pnl_usd": net_pnl_usd,
        "entry_margin_used_usd": 5.0,
        "net_return_on_margin_pct": net_pnl_usd / 5.0 * 100.0,
        "fees_usd": 0.02,
        "funding_usd": 0.0,
        "regime_opposition_episode": {"persistence_triggers": triggers},
    }
