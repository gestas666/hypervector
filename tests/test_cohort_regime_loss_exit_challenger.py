"""Tests for causal assembly and summary of regime-loss exit evidence."""

from __future__ import annotations

import pytest

from cohort_trade_reflection_fixtures import (
    independent_canonical_rows,
    reflection_asset_rows,
    reflection_cohort_rows,
)
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_regime_loss_exit_challenger import (
    build_regime_loss_exit_challenger,
    build_regime_loss_exit_observations,
    summarize_regime_loss_exit_results,
)
from hypervector.research.cohort_trade_reflection_index import Candle
from test_multi_asset_live_audit import _RUN_ID, _SYMBOLS, _asset_rows

_MINUTE_MS = 60_000


def test_observations_align_completed_close_with_next_open() -> None:
    """Decision D uses the D-1 close and D open without future-bar leakage."""
    decisions = tuple(range(_MINUTE_MS, 6 * _MINUTE_MS, _MINUTE_MS))
    provider = {decision: _context(decision, "TREND_UP") for decision in decisions}
    canonical = {decision: _context(decision, "TREND_UP") for decision in decisions}
    candles = {
        minute * _MINUTE_MS: Candle(
            minute * _MINUTE_MS,
            100.0 + minute * 0.1,
            100.2 + minute * 0.1,
            99.8 + minute * 0.1,
            100.05 + minute * 0.1,
        )
        for minute in range(0, 6)
    }

    coverage = build_regime_loss_exit_observations(
        side="short",
        provider_evaluations=provider,
        canonical_evaluations=canonical,
        candles=candles,
        entry_timestamp_ms=1,
        end_timestamp_ms=6 * _MINUTE_MS,
    )

    assert len(coverage.observations) == 5
    assert coverage.missing_price_decisions == 0
    assert coverage.observations[0].completed_close_price == pytest.approx(100.05)
    assert coverage.observations[0].next_open_price == pytest.approx(100.1)
    assert coverage.observations[0].structure_support_score == pytest.approx(-1.0)


def test_observation_coverage_reports_missing_next_open() -> None:
    """An unavailable execution reference is excluded and counted explicitly."""
    decision = 2 * _MINUTE_MS
    coverage = build_regime_loss_exit_observations(
        side="short",
        provider_evaluations={decision: _context(decision, "TREND_UP")},
        canonical_evaluations={decision: _context(decision, "TREND_UP")},
        candles={
            _MINUTE_MS: Candle(_MINUTE_MS, 100.0, 100.1, 99.9, 100.0),
        },
        entry_timestamp_ms=1,
        end_timestamp_ms=3 * _MINUTE_MS,
    )

    assert coverage.observations == ()
    assert coverage.missing_price_decisions == 1


def test_summary_uses_actual_exit_when_policy_does_not_trigger() -> None:
    """Non-triggering paths remain in the counterfactual portfolio unchanged."""
    rows = [
        _result(actual=-1.0, candidate=-0.4, triggered=True),
        _result(actual=2.0, candidate=2.0, triggered=False),
    ]

    summary = summarize_regime_loss_exit_results(rows, policy_id="opp5_loss30")

    assert summary["eligible_lifecycles"] == 2
    assert summary["triggered_lifecycles"] == 1
    assert summary["actual_net_pnl_usd"] == pytest.approx(1.0)
    assert summary["candidate_net_pnl_usd"] == pytest.approx(1.6)
    assert summary["candidate_minus_actual_net_usd"] == pytest.approx(0.6)
    assert summary["candidate_wins"] == 1
    assert summary["candidate_losses"] == 1
    assert summary["candidate_profit_factor"] == pytest.approx(5.0)


def test_summary_uses_null_profit_factor_without_losses() -> None:
    """No-loss subsets remain standards-compliant JSON instead of Infinity."""
    summary = summarize_regime_loss_exit_results(
        [_result(actual=1.0, candidate=1.0, triggered=False)],
        policy_id="opp5_loss30",
    )

    assert summary["candidate_wins"] == 1
    assert summary["candidate_losses"] == 0
    assert summary["candidate_profit_factor"] is None


def test_full_challenger_reconciles_nontriggering_closed_lifecycle() -> None:
    """A real audit fixture retains actual economics when no conjunction fires."""
    cohort = reflection_cohort_rows()
    btc = reflection_asset_rows()
    assets = {
        "BTC": btc,
        **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
    }
    audit = audit_multi_asset_live_run(cohort, assets, run_id=_RUN_ID)
    reflections = audit["trade_reflections"]

    challenger = build_regime_loss_exit_challenger(
        cohort,
        assets,
        closed_trades=reflections["all_time_live"]["trades"],
        open_trades=(),
        current_run_id=_RUN_ID,
        current_profile_fingerprint="cohort-profile-fingerprint",
        thresholds_bps=(30.0,),
        persistence_decisions=5,
    )

    assert challenger["contract"]["execution_authority"] == "none"
    assert challenger["contract"]["runtime_strategy_changed"] is False
    summary = challenger["all_live"]["opp5_loss30"]
    assert summary["eligible_lifecycles"] == 1
    assert summary["triggered_lifecycles"] == 0
    assert summary["candidate_net_pnl_usd"] == pytest.approx(0.97)
    assert summary["candidate_minus_actual_net_usd"] == pytest.approx(0.0)
    assert challenger["open_lifecycles"] == []


def test_full_challenger_uses_independent_canonical_regime_rows() -> None:
    """Telemetry-only canonical rows remain joinable after Range retirement."""
    cohort = independent_canonical_rows(reflection_cohort_rows())
    assets = {
        "BTC": reflection_asset_rows(),
        **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
    }
    audit = audit_multi_asset_live_run(cohort, assets, run_id=_RUN_ID)

    challenger = build_regime_loss_exit_challenger(
        cohort,
        assets,
        closed_trades=audit["trade_reflections"]["all_time_live"]["trades"],
        open_trades=(),
        current_run_id=_RUN_ID,
        current_profile_fingerprint="cohort-profile-fingerprint",
        thresholds_bps=(30.0,),
    )

    assert challenger["all_live"]["opp5_loss30"]["eligible_lifecycles"] == 1
    assert challenger["closed_lifecycles"][0]["evaluated_decisions"] > 0
    policy = challenger["closed_lifecycles"][0]["policies"]["opp5_loss30"]
    assert policy["unavailable_decisions"] == 0


def _context(decision_time_ms: int, regime: str) -> dict[str, object]:
    return {
        "decision_time_ms": decision_time_ms,
        "primary_regime": regime,
        "state_1m": regime,
        "state_5m": regime,
        "context_15m": regime,
        "confidence": 0.8,
        "readiness": {"metrics": {}},
    }


def _result(*, actual: float, candidate: float, triggered: bool) -> dict[str, object]:
    return {
        "status": "eligible",
        "actual_net_pnl_usd": actual,
        "policies": {
            "opp5_loss30": {
                "status": "triggered" if triggered else "retained_actual_exit",
                "estimated_net_pnl_usd": candidate,
            }
        },
    }
