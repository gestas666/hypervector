"""Tests for the preregistered causal BTC option-flow feature."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from hypervector.research.btc_option_directional_flow import (
    WeightedDirectionalTrade,
    absolute_spot_delta,
    aggregate_weighted_trades,
    build_causal_flow_signals,
    bullish_option_flow_sign,
    eligible_absolute_delta,
    weighted_directional_trade,
)
from hypervector.research.deribit_option_trade_acquisition import (
    DAY_MS,
    OptionInstrument,
    OptionTrade,
)


def test_black_scholes_absolute_call_and_put_delta() -> None:
    """The frozen zero-rate spot-delta formula must match analytic values."""
    call = absolute_spot_delta(100.0, 100.0, 0.5, 1.0, "call")
    put = absolute_spot_delta(100.0, 100.0, 0.5, 1.0, "put")

    assert call == pytest.approx(0.5987063257)
    assert put == pytest.approx(0.4012936743)
    assert call + put == pytest.approx(1.0)


def test_delta_population_uses_exact_open_closed_bounds() -> None:
    """DOTM/OTM membership must be (0.02, 0.375] without tolerance drift."""
    assert eligible_absolute_delta(0.02) is False
    assert eligible_absolute_delta(math.nextafter(0.02, 1.0)) is True
    assert eligible_absolute_delta(0.375) is True
    assert eligible_absolute_delta(math.nextafter(0.375, 1.0)) is False


@pytest.mark.parametrize(
    ("direction", "option_type", "expected"),
    [
        ("buy", "call", 1),
        ("sell", "call", -1),
        ("buy", "put", -1),
        ("sell", "put", 1),
    ],
)
def test_bullish_sign_uses_taker_direction(
    direction: str,
    option_type: str,
    expected: int,
) -> None:
    """Every call/put and taker-side combination must retain its frozen sign."""
    assert bullish_option_flow_sign(direction, option_type) == expected


def test_weighted_trade_uses_contract_spot_and_delta_with_maturity_bounds() -> None:
    """Eligible flow weight must use exact event-time metadata and maturity."""
    trade = _trade(timestamp_ms=10 * DAY_MS)
    instrument = _instrument(expiration_ms=17 * DAY_MS)

    weighted = weighted_directional_trade(trade, instrument)

    assert weighted is not None
    expected = trade.amount * instrument.contract_size * trade.index_price
    assert weighted.weight_usd == pytest.approx(expected * weighted.absolute_delta)
    assert weighted.signed_weight_usd == pytest.approx(weighted.weight_usd)
    assert (
        weighted_directional_trade(
            trade,
            _instrument(expiration_ms=10 * DAY_MS + DAY_MS - 1),
        )
        is None
    )
    assert (
        weighted_directional_trade(
            trade,
            _instrument(expiration_ms=10 * DAY_MS + 21 * DAY_MS + 1),
        )
        is None
    )


def test_registered_nonordinary_and_invalid_iv_trades_are_excluded() -> None:
    """Block/RFQ/combo trades and unusable volatility cannot enter flow."""
    instrument = _instrument(expiration_ms=17 * DAY_MS)
    assert (
        weighted_directional_trade(_trade(block_trade_id="BLOCK-1"), instrument) is None
    )
    assert weighted_directional_trade(_trade(block_rfq_id=949), instrument) is None
    assert weighted_directional_trade(_trade(combo_id="BTC-COMB"), instrument) is None
    assert weighted_directional_trade(_trade(combo_trade_id="123"), instrument) is None
    assert weighted_directional_trade(_trade(iv=0.0), instrument) is None


def test_hourly_aggregation_requires_twenty_eligible_trades() -> None:
    """Sparse hours must remain missing rather than fabricate zero flow."""
    start = pd.Timestamp("2025-04-01T00:00:00Z")
    start_ms = int(start.timestamp() * 1_000)
    trades = tuple(
        WeightedDirectionalTrade(str(index), start_ms + index, 0.1, 10.0, 10.0)
        for index in range(19)
    )

    sparse = aggregate_weighted_trades(
        trades, start=start, end=start + pd.Timedelta(hours=1)
    )
    complete = aggregate_weighted_trades(
        trades + (WeightedDirectionalTrade("20", start_ms + 20, 0.1, 10.0, -10.0),),
        start=start,
        end=start + pd.Timedelta(hours=1),
    )

    assert sparse.loc[0, "eligible_trade_count"] == 19
    assert math.isnan(float(sparse.loc[0, "directional_imbalance"]))
    assert complete.loc[0, "eligible_trade_count"] == 20
    assert complete.loc[0, "directional_imbalance"] == pytest.approx(0.9)


def test_causal_threshold_excludes_current_hour_and_needs_prior_history() -> None:
    """Current flow cannot affect its own quantile or bypass the warmup."""
    values = [-0.9 + 1.8 * value / 1_439 for value in range(1_440)] + [1.0]

    signals = build_causal_flow_signals(_hourly(values))

    expected = pd.Series(values[:-1]).quantile(0.99, interpolation="linear")
    assert signals.loc[1_440, "upper_threshold"] == pytest.approx(expected)
    assert math.isnan(float(signals.loc[1_439, "upper_threshold"]))
    assert not bool(signals.loc[1_439, "long_onset"])


def test_signal_availability_and_preceding_eligible_hour_are_causal() -> None:
    """Onset must use the last eligible prior hour and a 60-second delay."""
    values = [0.0] * 1_440 + [-0.5, 0.0, 0.5]
    counts = [20] * len(values)
    counts[1_441] = 19

    signals = build_causal_flow_signals(_hourly(values, counts))

    assert math.isnan(float(signals.loc[1_441, "directional_imbalance"]))
    assert not bool(signals.loc[1_441, "long_onset"])
    assert bool(signals.loc[1_442, "long_onset"])
    assert signals.loc[1_442, "available_at"] == (
        signals.loc[1_442, "timestamp"] + pd.Timedelta(hours=1, seconds=60)
    )


def test_opposing_onset_requires_prior_eligible_hour_above_its_threshold() -> None:
    """The frozen bearish extreme must use the symmetric causal transition."""
    values = [0.0] * 1_440 + [0.5, -0.5]

    signals = build_causal_flow_signals(_hourly(values))

    assert bool(signals.loc[1_441, "opposing_onset"])
    assert not bool(signals.loc[1_441, "long_onset"])


def _trade(
    *,
    timestamp_ms: int = 10 * DAY_MS,
    iv: float = 50.0,
    block_trade_id: str | None = None,
    block_rfq_id: int | None = None,
    combo_id: str | None = None,
    combo_trade_id: str | None = None,
) -> OptionTrade:
    return OptionTrade(
        trade_id="trade-1",
        trade_seq=1,
        instrument_name="BTC-17JAN70-110-C",
        timestamp_ms=timestamp_ms,
        direction="buy",
        amount=2.0,
        price=0.01,
        index_price=100.0,
        mark_price=0.01,
        iv=iv,
        tick_direction=0,
        block_trade_id=block_trade_id,
        block_rfq_id=block_rfq_id,
        combo_id=combo_id,
        combo_trade_id=combo_trade_id,
    )


def _instrument(*, expiration_ms: int) -> OptionInstrument:
    return OptionInstrument(
        instrument_name="BTC-17JAN70-110-C",
        creation_timestamp_ms=1,
        expiration_timestamp_ms=expiration_ms,
        strike=110.0,
        option_type="call",
        contract_size=1.0,
    )


def _hourly(values: list[float], counts: list[int] | None = None) -> pd.DataFrame:
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=len(values), freq="1h"),
            "eligible_trade_count": counts or [20] * len(values),
            "directional_imbalance": values,
        }
    )
