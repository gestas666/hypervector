"""Freshness, persistence, model authority and profile-boundary regression tests."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from test_cohort_adaptive_exit_controller import act, bars, book, engine
from hypervector.live.cohort_adaptive_exit_controller import adaptive_exit_action
from hypervector.live.cohort_adaptive_exit_inputs import prepare_adaptive_inputs
from hypervector.live.cohort_adaptive_exit_journal import AdaptiveExitJournal
from hypervector.live.cohort_adaptive_exit_policy import ADAPTIVE_EXIT_POLICY
from hypervector.live.cohort_exit_continuation_shadow import score_bundle
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_configuration_exit_policy import provider_exit_expectation, provider_exit_policy_evidence
from hypervector.research.v91_exit_continuation import FEATURE_NAMES
from hypervector.live.cohort_exit_continuation_shadow import continuation_shadow
from hypervector.live.multi_asset_market_bars import CohortMarketBar
from test_cohort_regime_routing import _evaluation

NOW = 1_260_000


@pytest.mark.parametrize("snapshot", [None, book(NOW - 30_001, 101), book(NOW + 1, 101),
                                       replace(book(NOW, 101), asks=()),
                                       replace(book(NOW, 101), bid_depth=0),
                                       replace(book(NOW, 101), asks=book(NOW, 99).asks)])
def test_invalid_book_falls_back_to_completed_close(snapshot: object) -> None:
    """Future/stale/crossed/missing books cannot invent executable profit."""
    result = prepare_adaptive_inputs(symbol="SOL", side="long", entry_price=100,
                                     opened_ms=1_200_000, observed_ms=NOW, book=snapshot,
                                     bars=bars(NOW), evaluations=())
    assert result.price == 100 and result.price_source == "completed_minute_close"
    assert result.book_ms is None and result.signed_pressure is None


def test_missing_volatility_cannot_disarm_an_earned_floor() -> None:
    """Fresh adverse quotes enforce persisted profit despite candle outages."""
    journal = AdaptiveExitJournal([], Mock())
    owner = engine()
    act(owner, journal, NOW, 101)
    degraded = Mock()
    result = adaptive_exit_action(symbol="SOL", snapshot=owner.snapshot, book=book(NOW + 15_000, 100.2),
                                  observed_ms=NOW + 15_000, entry_price=100, market_bars=(),
                                  evaluations=(), journal=journal, degraded=degraded)
    assert degraded.called and result.exit_reason == "adaptive_profit_floor"


def test_journal_accepts_exact_duplicate_but_refuses_conflict() -> None:
    """An idempotent replay emits no second observation; conflicts fail closed."""
    emit = Mock()
    journal = AdaptiveExitJournal([], emit)
    payload = {"lifecycle_id": "SOL:7", "observed_ms": 12, "value": 1}
    journal.append(payload)
    journal.append(payload)
    assert emit.call_count == 1
    for changed in ({**payload, "value": 2}, {**payload, "observed_ms": 11}):
        with pytest.raises(ValueError, match="conflict"):
            journal.append(changed)


def test_model_scores_only_finite_features_after_training_end() -> None:
    """Prospective inference is deterministic and cannot score its own future."""
    bundle = {"features": list(FEATURE_NAMES), "training_end": "2026-01-01T00:00:00Z",
              "means": [0.] * 8, "scales": [1.] * 8, "coefficients": [1.] * 8, "intercept": 2.}
    features = pd.Series({name: 1.0 for name in FEATURE_NAMES})
    observed = int(pd.Timestamp("2026-02-01", tz="UTC").timestamp() * 1_000)
    assert score_bundle(bundle, features, observed) == 10
    with pytest.raises(ValueError, match="prior"):
        score_bundle(bundle, features, 1)
    features.iloc[0] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        score_bundle(bundle, features, observed)


def test_eight_asset_profile_and_checkpoint_bind_exact_exit_policy() -> None:
    """Every requested market has execution authority and the new bound policy."""
    path = Path("configs/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml")
    config = load_multi_asset_live_config(path, mode="observe")
    assert {symbol for _, symbol in config.executable_provider_symbols} == set(config.symbols)
    assert len(config.symbols) == 8
    policies = provider_exit_policy_evidence(provider_exit_expectation(config))
    for provider in config.providers:
        assert provider.execution.adaptive_exit_policy == ADAPTIVE_EXIT_POLICY
        assert policies[provider.strategy_id]["adaptive_exit_policy"] == ADAPTIVE_EXIT_POLICY
    assert config.maximum_positions == 8


@pytest.mark.parametrize("age,expected", [(0, 1.0), (90_001, None), (-1, None)])
def test_only_fresh_causal_regime_can_support_holding(age: int, expected: float | None) -> None:
    """Stale and future context cannot justify a wider trend allowance."""
    regime = replace(_evaluation("TREND_UP", "TREND_UP", "TREND_UP", decision_time_ms=NOW - age), symbol="SOL")
    result = prepare_adaptive_inputs(symbol="SOL", side="long", entry_price=100,
                                     opened_ms=1_200_000, observed_ms=NOW,
                                     book=book(NOW, 101), bars=bars(NOW), evaluations=(regime,))
    assert result.alignment == expected


def test_shadow_forecast_runs_prospectively_with_zero_order_authority() -> None:
    """Real serialized Ridge coefficients score new complete candles for both sides."""
    end = int(pd.Timestamp("2026-09-22T09:00:00Z").timestamp() * 1_000)
    history = tuple(CohortMarketBar("SOL", end - (900 - index) * 60_000,
                                  100 + index * .001, 100.1 + index * .001,
                                  99.9 + index * .001, 100 + index * .001, 10.0)
                    for index in range(900))
    long = continuation_shadow("SOL", "long", history, end)
    short = continuation_shadow("SOL", "short", history, end)
    assert long["outcome"] == "observed" and long["execution_authority"] == "none"
    assert long["incremental_hold_bps"] == -short["incremental_hold_bps"]


@pytest.mark.parametrize("change", [
    {"observed_ms": NOW + 1}, {"armed": False}, {"floor_bps": float("nan")},
    {"book_count": -1}, {"exit_reason": "invented"},
])
def test_corrupted_recovered_state_cannot_produce_a_close(change: dict[str, object]) -> None:
    """Restart rejects invalid temporal, activation and numerical evidence."""
    journal = AdaptiveExitJournal([], Mock())
    owner = engine()
    act(owner, journal, NOW, 101)
    payload = dict(journal.recorded("SOL:7:1200000"))
    payload["state"] = {**payload["state"], **change}
    restored = AdaptiveExitJournal([{"event_type": "adaptive_exit_observation", "payload": payload}], Mock())
    with pytest.raises(ValueError):
        act(owner, restored, NOW + 15_000, 100.2)


def test_repeated_cycle_is_idempotent_and_initial_missing_data_is_unavailable() -> None:
    """No duplicate durable observation and no false armed state during warmup."""
    emit = Mock()
    journal = AdaptiveExitJournal([], emit)
    owner = engine()
    assert act(owner, journal, NOW, 101, ()) is None
    assert not emit.called
    assert act(owner, journal, NOW, 101) is None
    assert act(owner, journal, NOW, 101) is None
    assert emit.call_count == 1
