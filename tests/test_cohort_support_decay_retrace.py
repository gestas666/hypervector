"""Causal support-decay breakeven-retrace challenger tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_profit_lock_results import ProfitLockEconomics
from hypervector.research.cohort_support_decay_retrace import (
    SupportDecayRetracePolicy,
    build_support_decay_retrace_mechanism,
    evaluate_support_decay_retrace_path,
)
from hypervector.research.cohort_trade_reflection_index import Candle


def test_retrace_requires_prior_mfe_and_prior_support_decay() -> None:
    """Neither the activation bar nor the support-decay bar may trigger an exit."""
    policy = SupportDecayRetracePolicy("mfe40_decay_net5", 40.0, 5.0)
    state = evaluate_support_decay_retrace_path(
        policy,
        "long",
        (
            _bar(60_000, 100.0, 100.50, 100.0, 100.40),
            _bar(120_000, 100.40, 100.45, 100.05, 100.10),
            _bar(180_000, 100.10, 100.15, 100.04, 100.05),
        ),
        _economics(),
        {},
        support_decay_trigger_ms=120_000,
    )

    assert state.activation_timestamp_ms == 60_000
    assert state.trigger is not None
    assert state.trigger.decision_timestamp_ms == 180_000
    assert state.trigger.exit_timestamp_ms == 180_000
    assert state.trigger.exit_reference_price == pytest.approx(100.10)


def test_retrace_is_directionally_symmetric_for_shorts() -> None:
    """A short uses its completed trough and rising retrace net consistently."""
    policy = SupportDecayRetracePolicy("mfe40_decay_net5", 40.0, 5.0)
    economics = _economics(entry_price=100.0, actual_exit_price=101.0)
    state = evaluate_support_decay_retrace_path(
        policy,
        "short",
        (
            _bar(60_000, 100.0, 100.0, 99.50, 99.60),
            _bar(120_000, 99.60, 99.95, 99.55, 99.90),
            _bar(180_000, 99.90, 100.0, 99.85, 99.95),
        ),
        economics,
        {},
        support_decay_trigger_ms=120_000,
    )

    assert state.trigger is not None
    assert state.trigger.exit_reference_price == pytest.approx(99.90)
    assert state.trigger.best_completed_price == pytest.approx(99.50)


def test_mechanism_is_report_only_and_exact_provider_scoped() -> None:
    """Unrelated strategies cannot be pooled into HYPE-breakout exit evidence."""
    report = build_support_decay_retrace_mechanism(
        _cohort_rows(),
        {"HYPE": _asset_rows()},
        [_trade(), _trade(strategy_id="hulk_expansion_bidirectional_tuned_v2")],
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert report["strategy_scope"] == "hype_breakout_onset_bidirectional_v1"
    assert report["source_lifecycles"] == 1
    assert report["trial_accounting"] == {
        "predeclared_policy_trials": 3,
        "selection_performed": False,
    }
    summary = report["summary_by_policy"]["mfe40_decay_net5"]
    assert summary["eligible_lifecycles"] == 1
    assert summary["triggered"] == 1


def _economics(
    *, entry_price: float = 100.0, actual_exit_price: float = 99.0
) -> ProfitLockEconomics:
    return ProfitLockEconomics(
        entry_timestamp_ms=10_000,
        exit_timestamp_ms=250_000,
        entry_price=entry_price,
        actual_exit_price=actual_exit_price,
        size=1.0,
        entry_fee_usd=0.045,
        exit_fee_rate=0.00045,
        fill_reference_ratio=1.0,
        actual_funding_usd=0.0,
        actual_net_pnl_usd=-1.09,
    )


def _bar(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(timestamp_ms, open_price, high, low, close)


def _cohort_rows() -> list[dict[str, object]]:
    bars = [
        _bar_payload(60_000, 100.0, 100.50, 100.0, 100.40),
        _bar_payload(120_000, 100.40, 100.45, 100.30, 100.35),
        _bar_payload(180_000, 100.35, 100.40, 100.30, 100.35),
        _bar_payload(240_000, 100.35, 100.40, 100.30, 100.35),
        _bar_payload(300_000, 100.35, 100.40, 100.05, 100.10),
        _bar_payload(360_000, 100.10, 100.15, 100.04, 100.05),
    ]
    rows: list[dict[str, object]] = [
        {
            "event_type": "market_candles",
            "run_id": "run-current",
            "payload": {"timeframe": "1m", "bars": {"HYPE": bars}},
        }
    ]
    for timestamp_ms in (60_000, 120_000, 180_000, 240_000, 300_000):
        rows.append(
            {
                "event_type": "intent_routing",
                "run_id": "run-current",
                "payload": {
                    "evaluations": [
                        _evaluation(
                            "hype_breakout_onset_bidirectional_v1", timestamp_ms
                        ),
                        _evaluation("range_onset_bidirectional_v1", timestamp_ms),
                    ]
                },
            }
        )
    return rows


def _bar_payload(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
    }


def _evaluation(strategy_id: str, timestamp_ms: int) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": "HYPE",
        "decision_time_ms": timestamp_ms,
        "primary_regime": "RANGE",
        "state_1m": "RANGE",
        "state_5m": "RANGE",
        "context_15m": "RANGE",
        "confidence": 0.2,
    }


def _asset_rows() -> list[dict[str, object]]:
    return [
        _asset_event(
            "fill",
            oid=11,
            trade_id=101,
            venue_timestamp_ms=10_000,
            price=100.0,
            size=1.0,
            fee_usd=0.045,
        ),
        _asset_event(
            "fill",
            oid=12,
            trade_id=102,
            venue_timestamp_ms=430_000,
            price=99.0,
            size=1.0,
            fee_usd=0.04455,
        ),
    ]


def _asset_event(event_type: str, **payload: object) -> dict[str, object]:
    return {"event_type": event_type, "payload": payload}


def _trade(
    *, strategy_id: str = "hype_breakout_onset_bidirectional_v1"
) -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "symbol": "HYPE",
        "strategy_id": strategy_id,
        "side": "long",
        "source_run_id": "run-current",
        "source_profile_fingerprint": "profile-current",
        "entry_oid": 11,
        "exit_oid": 12,
        "entry": {
            "venue_timestamp_ms": 10_000,
            "price": 100.0,
            "size": 1.0,
        },
        "exit": {
            "venue_timestamp_ms": 430_000,
            "price": 99.0,
            "size": 1.0,
            "expected_reference_price": 99.0,
        },
        "fees_usd": 0.08955,
        "funding_usd": 0.0,
        "net_pnl_usd": -1.08955,
    }
