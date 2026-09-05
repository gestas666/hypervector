"""Development-only accounting for funding/price-exhaustion screens."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import hypervector.research.funding_price_exhaustion_development as study
from hypervector.research.funding_price_exhaustion_development import (
    FundingExhaustionCosts,
    FundingExhaustionDevelopmentSpec,
    evaluate_funding_price_exhaustion_development,
)
from hypervector.research.funding_price_exhaustion_signals import (
    FundingPriceExhaustionConfig,
    FundingPriceExhaustionSignals,
)


def _bars(times: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": times,
            "open": [100.0] * len(times),
            "high": [101.2] * len(times),
            "low": [99.0] * len(times),
            "close": [100.0] * len(times),
            "volume": [10.0] * len(times),
        }
    )


def _funding(times: list[pd.Timestamp], rates: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": times,
            "event_ts_ms": [int(value.timestamp() * 1_000) + 1 for value in times],
            "funding_rate": rates,
            "source": ["hl_funding_history"] * len(times),
        }
    )


def _signals(block: pd.DataFrame, indexes: list[int]) -> FundingPriceExhaustionSignals:
    selected = pd.Series(False, index=block.index)
    selected.iloc[indexes] = True
    return FundingPriceExhaustionSignals(
        long_signals=selected,
        short_signals=pd.Series(False, index=block.index),
        atr_bps=pd.Series(np.nan, index=block.index),
        diagnostics=block.loc[:, ["timestamp", "open", "close"]].copy(),
    )


def test_gap_paths_are_censored_and_funding_is_side_correct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = pd.date_range("2026-01-01", periods=5, freq="5min", tz="UTC")
    second = pd.date_range("2026-01-01T00:30Z", periods=7, freq="5min")
    bars = _bars(first.append(second))
    bars.loc[bars["timestamp"] == second[3], "close"] = 101.0
    funding = _funding(
        [pd.Timestamp("2025-12-31T21:00Z"), pd.Timestamp("2026-01-01T00:40Z")],
        [0.0, 0.001],
    )

    def fake_builder(
        block: pd.DataFrame,
        _funding: pd.DataFrame,
        _config: FundingPriceExhaustionConfig,
    ) -> FundingPriceExhaustionSignals:
        indexes = [3] if block.iloc[0]["timestamp"] == first[0] else [0, 1, 2]
        return _signals(block, indexes)

    monkeypatch.setattr(study, "build_funding_price_exhaustion_signals", fake_builder)
    report = evaluate_funding_price_exhaustion_development(
        bars,
        funding,
        FundingPriceExhaustionConfig(clean_history_bars=21),
        FundingExhaustionCosts(4.0, 8.0),
        FundingExhaustionDevelopmentSpec(horizons_minutes=(15,)),
        start_utc=first[0],
        end_utc=second[-1] + pd.Timedelta(minutes=5),
    )

    horizon = report["horizons"]["15m"]
    assert horizon["resolved_observations"] == 3
    assert horizon["censored_observations"] == 1
    assert horizon["primary_non_overlapping"]["observations"] == 1
    assert horizon["primary_non_overlapping"]["funding_return_bps"] == -10.0
    assert horizon["primary_non_overlapping"]["nominal_net_bps"] == pytest.approx(86.0)
    assert horizon["primary_non_overlapping"]["stress_net_bps"] == pytest.approx(82.0)
    assert report["decision"] == "insufficient_development_evidence"


def test_supportive_decision_requires_independent_robust_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = pd.date_range("2026-01-01", periods=21, freq="5min", tz="UTC")
    bars = _bars(times)
    outcomes = [101.0] * 10
    outcomes[3] = 99.5
    outcomes[7] = 99.5
    for signal_index, close in zip(range(0, 20, 2), outcomes, strict=True):
        bars.loc[signal_index + 1, "close"] = close
    funding = _funding([pd.Timestamp("2025-12-31T23:00Z")], [0.0])

    def fake_builder(
        block: pd.DataFrame,
        _funding: pd.DataFrame,
        _config: FundingPriceExhaustionConfig,
    ) -> FundingPriceExhaustionSignals:
        return _signals(block, list(range(0, 20, 2)))

    monkeypatch.setattr(study, "build_funding_price_exhaustion_signals", fake_builder)
    report = evaluate_funding_price_exhaustion_development(
        bars,
        funding,
        FundingPriceExhaustionConfig(clean_history_bars=21),
        FundingExhaustionCosts(4.0, 10.0),
        FundingExhaustionDevelopmentSpec(horizons_minutes=(5,)),
        start_utc=times[0],
        end_utc=times[-1] + pd.Timedelta(minutes=5),
    )

    summary = report["horizons"]["5m"]["primary_non_overlapping"]
    assert summary["observations"] == 10
    assert summary["stress_net_bps"] == pytest.approx(600.0)
    assert summary["stress_excluding_largest_winner_bps"] == pytest.approx(510.0)
    assert summary["stress_profit_factor"] == pytest.approx(6.0)
    assert summary["stress_positive_folds"] >= 3
    assert report["decision"] == "supportive_development_only"
    assert report["supportive_horizons"] == ["5m"]


def test_stress_cost_cannot_be_cheaper_than_nominal() -> None:
    with pytest.raises(ValueError, match="stress round-trip"):
        FundingExhaustionCosts(10.0, 9.0)


def test_frozen_twenty_four_hour_horizon_keeps_exact_label() -> None:
    assert study._horizon_label(1_440) == "24h"
