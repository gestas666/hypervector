"""Prove the new cohort adapters preserve the exact researched signal stream."""

import numpy as np
import pandas as pd
import pytest

from hypervector.live.hourly_price_provider import (
    HOURLY_PRICE_STRATEGIES,
    HourlyPriceCollector,
    build_hourly_price_signals,
)


def _bars() -> pd.DataFrame:
    values = np.repeat([100.0] * 25 + [90.0, 97.0, 100.0, 110.0, 103.0, 100.0], 4)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=len(values), freq="15min", tz="UTC"
            ),
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values,
            "volume": 10.0,
        }
    )


@pytest.mark.parametrize("strategy", sorted(HOURLY_PRICE_STRATEGIES))
@pytest.mark.parametrize("symbol", ["xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL"])
def test_provider_preserves_research_entries_stops_and_recipe_exits(
    strategy: str, symbol: str
) -> None:
    """Cohort publication must match the completed-bar research mechanism exactly."""
    bars = _bars()
    observed = bars.timestamp.iloc[-1] + pd.Timedelta(minutes=15)
    batch = HourlyPriceCollector(strategy_id=strategy)(
        bars,
        symbol=symbol,
        observed_at=observed,
        after_decision_time_ms=None,
    )
    expected = build_hourly_price_signals(bars.set_index("timestamp"), strategy)
    expected_entries = [
        (int((time + pd.Timedelta(minutes=15)).timestamp() * 1000), side)
        for time, row in expected.iterrows()
        for side in ("long", "short")
        if row[f"{side}_entry"] and np.isfinite(row.stop_price)
    ]
    assert [
        (row.decision_time_ms, row.side) for row in batch.intents
    ] == expected_entries
    assert batch.intents
    for intent in batch.intents:
        time = pd.Timestamp(
            intent.decision_time_ms, unit="ms", tz="UTC"
        ) - pd.Timedelta(minutes=15)
        assert intent.stop_anchor == expected.loc[time, "stop_price"]
        assert intent.symbol == symbol
    for evaluation, (_, row) in zip(
        batch.evaluations, expected.iterrows(), strict=True
    ):
        assert evaluation.exit_sides == frozenset(
            side for side in ("long", "short") if row[f"{side}_exit"]
        )
    repeated = HourlyPriceCollector(strategy_id=strategy)(
        bars,
        symbol=symbol,
        observed_at=observed,
        after_decision_time_ms=batch.latest_decision_time_ms,
    )
    assert repeated.intents == repeated.evaluations == ()


def test_provider_rejects_unqualified_symbol_and_unknown_recipe() -> None:
    """Unknown symbols or mechanisms cannot silently inherit another recipe."""
    with pytest.raises(ValueError, match="strategy"):
        HourlyPriceCollector(strategy_id="unknown")
    collector = HourlyPriceCollector(strategy_id=next(iter(HOURLY_PRICE_STRATEGIES)))
    with pytest.raises(ValueError, match="symbol"):
        collector(
            _bars(),
            symbol="cash:WTI",
            observed_at=pd.Timestamp("2026-01-03T00:00Z"),
            after_decision_time_ms=None,
        )


@pytest.mark.parametrize("strategy", sorted(HOURLY_PRICE_STRATEGIES))
def test_hourly_readiness_publishes_displayable_prices_and_both_clocks(
    strategy: str,
) -> None:
    """The inspector receives measured prices and distinguishes source from signal."""
    bars = _bars()
    batch = HourlyPriceCollector(strategy_id=strategy)(
        bars,
        symbol="xyz:SPCX",
        observed_at=bars.timestamp.iloc[-1] + pd.Timedelta(minutes=15),
        after_decision_time_ms=None,
    )
    readiness = batch.evaluations[-1].readiness
    assert readiness.metrics["source_timeframe"] == "15m"
    assert readiness.metrics["signal_timeframe"] == "1h"
    assert any("ATR " in value for value in readiness.indicators)
    if "donchian" in strategy:
        for name in ("prior_entry_low", "prior_exit_high"):
            assert isinstance(readiness.metrics[name], float)
        assert any("ENTRY CHANNEL" in value for value in readiness.indicators)
        assert any("EXIT CHANNEL" in value for value in readiness.indicators)
    else:
        assert any("BAND" in value for value in readiness.indicators)
