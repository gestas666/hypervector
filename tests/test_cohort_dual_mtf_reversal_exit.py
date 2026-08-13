"""Tests for assembled dual-timeframe reversal-exit evidence."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_dual_mtf_reversal_exit import (
    build_dual_mtf_reversal_exit_challenger,
    build_dual_mtf_reversal_observations,
    summarize_dual_mtf_reversal_results,
)
from hypervector.research.cohort_trade_reflection_index import Candle

_MINUTE_MS = 60_000
_RUN = "run-live"
_PROFILE = "profile-live"
_STRATEGY = "hype_breakout_onset_bidirectional_v1"


def test_observations_require_prior_causal_cost_clearance() -> None:
    """The profitable completed close becomes state only for the next decision."""
    evaluations = {minute * _MINUTE_MS: _evaluation(minute) for minute in (1, 2)}
    candles = {
        minute * _MINUTE_MS: Candle(minute * _MINUTE_MS, 99.0, 99.2, 98.8, 99.0)
        for minute in range(3)
    }

    coverage = build_dual_mtf_reversal_observations(
        side="short",
        evaluations=evaluations,
        candles=candles,
        funding={0: 100.0},
        entry_timestamp_ms=1,
        end_timestamp_ms=3 * _MINUTE_MS,
        entry_price=100.0,
        size=1.0,
        entry_fee_usd=0.01,
    )

    assert coverage.evaluated_decisions == 2
    assert coverage.missing_price_decisions == 0
    assert coverage.observations[0].cost_cleared_before_decision is False
    assert coverage.observations[1].cost_cleared_before_decision is True
    assert coverage.observations[0].estimated_net_at_completed_close_usd < 2.0
    assert coverage.observations[0].direction_1m == 1
    assert coverage.observations[0].direction_5m == 1


def test_summary_retains_actual_for_nontrigger_and_removes_largest_winner() -> None:
    """Every lifecycle remains in the policy portfolio and outlier audit."""
    rows = [
        _result(actual=-1.0, candidate=0.4, triggered=True),
        _result(actual=2.0, candidate=2.0, triggered=False),
        _result(actual=-0.5, candidate=-0.5, triggered=False),
        _result(actual=-3.0, candidate=None, triggered=False, status="withheld"),
    ]

    summary = summarize_dual_mtf_reversal_results(rows, policy_id="dual_mtf_p1")

    assert summary["eligible_lifecycles"] == 3
    assert summary["all_lifecycle_actual_net_pnl_usd"] == pytest.approx(-2.5)
    assert summary["withheld_actual_net_pnl_usd"] == pytest.approx(-3.0)
    assert summary["triggered_lifecycles"] == 1
    assert summary["candidate_net_pnl_usd"] == pytest.approx(1.9)
    assert summary["candidate_minus_actual_net_usd"] == pytest.approx(1.4)
    assert summary["candidate_net_excluding_largest_winner_usd"] == pytest.approx(-0.1)
    assert summary["candidate_median_net_pnl_usd"] == pytest.approx(0.4)


def test_full_challenger_reports_all_cells_without_selecting_one() -> None:
    """The report exposes 1/3/5 persistence and has no promotion authority."""
    report = build_dual_mtf_reversal_exit_challenger(
        _cohort_records(),
        {"BTC": _asset_records()},
        closed_trades=[_trade()],
        current_run_id=_RUN,
        current_profile_fingerprint=_PROFILE,
        persistence_surface=(1, 3, 5),
    )

    lifecycle = report["closed_lifecycles"][0]
    assert set(lifecycle["policies"]) == {
        "dual_mtf_p1",
        "dual_mtf_p3",
        "dual_mtf_p5",
    }
    assert lifecycle["policies"]["dual_mtf_p1"]["status"] == "triggered"
    assert lifecycle["policies"]["dual_mtf_p3"]["status"] == "triggered"
    assert lifecycle["policies"]["dual_mtf_p5"]["status"] == "retained_actual_exit"
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["selected_policy"] is None
    assert report["trial_count"] == 3
    assert report["current_run_effective_episodes"]["effective_episode_clusters"] == 1


def _evaluation(minute: int) -> dict[str, object]:
    return {
        "strategy_id": "canonical_regime_telemetry_v1",
        "symbol": "BTC",
        "decision_time_ms": minute * _MINUTE_MS,
        "state_1m": "TREND_UP",
        "state_5m": "BREAKOUT",
        "readiness": {
            "metrics": {
                "structural_direction": "short",
                "regime_1m_ema_gap_bps": 6.0,
                "regime_5m_ema_gap_bps": 8.0,
            }
        },
    }


def _result(
    actual: float,
    candidate: float | None,
    triggered: bool,
    *,
    status: str = "eligible",
) -> dict[str, object]:
    return {
        "status": status,
        "actual_net_pnl_usd": actual,
        "policies": {
            "dual_mtf_p1": {
                "status": "triggered" if triggered else "retained_actual_exit",
                "estimated_net_pnl_usd": candidate,
            }
        },
    }


def _cohort_records() -> list[dict[str, object]]:
    bars = [
        {
            "timestamp_ms": minute * _MINUTE_MS,
            "open": 99.0,
            "high": 99.2,
            "low": 98.8,
            "close": 99.0,
        }
        for minute in range(5)
    ]
    records = [
        {
            "event_type": "market_candles",
            "run_id": _RUN,
            "payload": {"timeframe": "1m", "bars": {"BTC": bars}},
        }
    ]
    for minute in range(1, 5):
        records.append(
            {
                "event_type": "canonical_regime_evaluations",
                "run_id": _RUN,
                "payload": {"evaluations": [_evaluation(minute)]},
            }
        )
    return records


def _trade() -> dict[str, object]:
    return {
        "lifecycle_id": "BTC:11",
        "symbol": "BTC",
        "strategy_id": _STRATEGY,
        "side": "short",
        "source_run_id": _RUN,
        "source_profile_fingerprint": _PROFILE,
        "entry_oid": 11,
        "exit_oid": 12,
        "entry": {
            "price": 100.0,
            "size": 1.0,
            "venue_timestamp_ms": 1,
            "expected_reference_price": 99.98,
            "slippage_bps": 2.0,
        },
        "exit": {
            "price": 101.0,
            "size": 1.0,
            "venue_timestamp_ms": 4 * _MINUTE_MS + 30_000,
            "expected_reference_price": 100.9,
            "slippage_bps": 9.91,
        },
        "fees_usd": 0.02,
        "funding_usd": 0.0,
        "net_pnl_usd": -1.02,
    }


def _asset_records() -> list[dict[str, object]]:
    return [
        _fill(11, 101, 100.0, 0.01, 1),
        _fill(12, 102, 101.0, 0.01, 4 * _MINUTE_MS + 30_000),
    ]


def _fill(
    oid: int, trade_id: int, price: float, fee: float, timestamp: int
) -> dict[str, object]:
    return {
        "event_type": "fill",
        "payload": {
            "oid": oid,
            "trade_id": trade_id,
            "price": price,
            "size": 1.0,
            "fee_usd": fee,
            "venue_timestamp_ms": timestamp,
        },
    }
