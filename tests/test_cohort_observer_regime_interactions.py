"""Tests for report-only observer regime interaction diagnostics."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_observer_regime_interactions import (
    build_observer_regime_interactions,
)


def _report(*, authority: str = "none") -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": authority,
        "runtime_strategy_changed": False,
        "contract": {
            "strategy_id": "range_onset_bidirectional_v1",
            "symbol": "SOL",
            "blocker": "awaiting_hourly_sma_cross",
            "horizon_minutes": 15,
        },
        "source": {
            "selected_run_id": "observer-run",
            "effective_profile_fingerprint": "f" * 64,
        },
        "executions": [
            _execution(-12.0, "TREND_DOWN", "RANGE"),
            _execution(4.0, "TREND_DOWN", "TRANSITION"),
            _execution(2.0, "TREND_UP", "RANGE"),
        ],
    }


def _execution(
    net_return_bps: float,
    context_15m: str,
    state_1m: str,
) -> dict[str, object]:
    return {
        "side": "long",
        "status": "resolved",
        "net_return_bps": net_return_bps,
        "entry_features": {
            "primary_regime": "RANGE",
            "state_1m": state_1m,
            "state_5m": "RANGE",
            "context_15m": context_15m,
            "structural_direction": "long",
        },
    }


def test_regime_interactions_preserve_exact_states_and_side_relations() -> None:
    """Diagnostic must expose sparse raw states without inventing a gate."""
    result = build_observer_regime_interactions([_report()])
    route = result["routes"][0]

    assert result["execution_authority"] == "none"
    assert result["automatic_strategy_change"] is False
    assert route["resolved"] == 3
    assert route["by_context_15m_relation"]["opposed"] == {
        "resolved": 2,
        "wins": 1,
        "losses": 1,
        "total_net_return_bps": pytest.approx(-8.0),
        "mean_net_return_bps": pytest.approx(-4.0),
        "median_net_return_bps": pytest.approx(-4.0),
        "net_excluding_largest_winner_bps": pytest.approx(-12.0),
    }
    assert route["by_context_15m_relation"]["aligned"]["resolved"] == 1
    assert len(route["by_exact_entry_state"]) == 3


def test_regime_interactions_reject_execution_authority() -> None:
    """A diagnostic may not ingest a success-shaped execution report."""
    with pytest.raises(ValueError, match="authority-none"):
        build_observer_regime_interactions([_report(authority="live")])


def test_regime_interactions_reject_mixed_source_identity() -> None:
    """Reports from different observer runs must not be pooled silently."""
    first = _report()
    second = _report()
    second["source"] = {
        "selected_run_id": "other-run",
        "effective_profile_fingerprint": "f" * 64,
    }

    with pytest.raises(ValueError, match="same observer run"):
        build_observer_regime_interactions([first, second])
