"""Regression: research bars carry a RangeIndex plus a ``timestamp`` column.

Sharpe annualisation and funding hold time must come from the bar timestamps,
not from integer positions (which were read as nanoseconds, so every trade paid
one minute of funding and 15m/1h Sharpe was annualised as 1m).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from hypervector.data.provenance import normalize_ohlcv
from hypervector.sweep.costs import CostModel
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics


def _bars(n: int, freq: str, *, seed: int = 5) -> pd.DataFrame:
    """normalize_ohlcv output: RangeIndex with a tz-aware timestamp column."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.004, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-03-01", periods=n, freq=freq, tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) * 1.001,
            "low": np.minimum(open_, close) * 0.999,
            "close": close,
            "volume": 1.0,
            "source": "synthetic",
        }
    )
    out = normalize_ohlcv(frame)
    assert isinstance(out.index, pd.RangeIndex)
    return out


def _signals(index: pd.Index, pairs: list[tuple[int, int]]) -> tuple[pd.Series, pd.Series]:
    entries = pd.Series(False, index=index)
    exits = pd.Series(False, index=index)
    for entry, exit_ in pairs:
        entries.iloc[entry] = True
        exits.iloc[exit_] = True
    return entries, exits


_FUNDING_ONLY = CostModel(taker_fee=0.0, slippage_bps=0.0, funding_rate_1h=0.0001)


def test_funding_uses_real_hold_time_on_15m_rangeindex_bars() -> None:
    df = _bars(200, "15min")
    entries, exits = _signals(df.index, [(10, 30)])  # 20 bars * 15 min = 5 hours

    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        df=df,
        cost=_FUNDING_ONLY,
        fixed_notional_fraction=1.0,
        strategy_managed_exits=True,
    )

    assert m["trade_count"] == 1
    # 10,000 notional * 1 bp/hour * 5 hours
    assert m["funding_cost"] == pytest.approx(10_000.0 * 0.0001 * 5.0, rel=1e-9)
    assert m["bar_freq"] == "15min"


def test_rangeindex_and_datetimeindex_frames_give_identical_metrics() -> None:
    df = _bars(2_000, "15min")
    pairs = [(i, i + 7) for i in range(30, 1_950, 40)]
    entries, exits = _signals(df.index, pairs)
    timed = df.set_axis(pd.DatetimeIndex(df["timestamp"]).rename(None), axis=0)
    kwargs = dict(
        cost=CostModel(taker_fee=0.00045, slippage_bps=2.0, funding_rate_1h=0.0000125),
        exit_cfg=ExitConfig(mode="atr"),
    )

    positional = compute_trial_metrics(df["close"], entries, exits, df=df, **kwargs)
    by_time = compute_trial_metrics(
        timed["close"],
        entries.set_axis(timed.index),
        exits.set_axis(timed.index),
        df=timed,
        **kwargs,
    )

    for key in ("sharpe", "funding_cost", "net_pnl", "trade_count", "max_drawdown"):
        assert positional[key] == pytest.approx(by_time[key], rel=1e-9, abs=1e-12), key
    assert positional["bar_freq"] == by_time["bar_freq"] == "15min"


def test_sharpe_is_annualised_with_the_bar_frequency() -> None:
    """Same per-bar P&L path: 15m Sharpe must be sqrt(15) smaller than the 1m one."""
    one_minute = _bars(3_000, "1min", seed=9)
    fifteen = one_minute.assign(
        timestamp=pd.date_range("2026-03-01", periods=3_000, freq="15min", tz="UTC")
    )
    pairs = [(i, i + 9) for i in range(20, 2_950, 30)]
    entries, exits = _signals(one_minute.index, pairs)
    common = dict(
        cost=_FUNDING_ONLY.__class__(taker_fee=0.0, slippage_bps=0.0, funding_rate_1h=0.0),
        fixed_notional_fraction=1.0,
        strategy_managed_exits=True,
    )

    fast = compute_trial_metrics(one_minute["close"], entries, exits, df=one_minute, **common)
    slow = compute_trial_metrics(fifteen["close"], entries, exits, df=fifteen, **common)

    assert fast["bar_freq"] == "1min"
    assert slow["bar_freq"] == "15min"
    assert fast["sharpe"] != 0.0
    assert slow["sharpe"] == pytest.approx(fast["sharpe"] / math.sqrt(15.0), rel=1e-9)


def test_real_equity_sharpe_matches_the_vectorbt_definition() -> None:
    import vectorbt  # noqa: F401  (registers the .vbt accessor)

    from hypervector.sweep.metrics import _sharpe

    rng = np.random.default_rng(3)
    equity = 10_000.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.003, 500))
    returns = pd.Series(np.concatenate([[equity[0] / 10_000.0 - 1.0], equity[1:] / equity[:-1] - 1.0]))

    expected = returns.vbt.returns(freq="15min").sharpe_ratio()
    assert _sharpe(equity, 10_000.0, "15min") == pytest.approx(expected, rel=1e-12)


def test_frequency_inference_ignores_a_leading_gap() -> None:
    df = _bars(400, "1h")
    shifted = df.copy()
    shifted.loc[0, "timestamp"] = shifted.loc[1, "timestamp"] - pd.Timedelta(days=3)
    entries, exits = _signals(df.index, [(50, 60)])

    m = compute_trial_metrics(
        shifted["close"],
        entries,
        exits,
        df=shifted,
        cost=_FUNDING_ONLY,
        fixed_notional_fraction=1.0,
        strategy_managed_exits=True,
    )

    assert m["bar_freq"] == "1h"
    assert m["funding_cost"] == pytest.approx(10_000.0 * 0.0001 * 10.0, rel=1e-9)


def test_close_only_series_without_timestamps_uses_bar_count() -> None:
    close = pd.Series(np.linspace(100.0, 110.0, 120))
    entries, exits = _signals(close.index, [(10, 70)])

    m = compute_trial_metrics(
        close,
        entries,
        exits,
        cost=_FUNDING_ONLY,
        fixed_notional_fraction=1.0,
        strategy_managed_exits=True,
    )

    assert m["bar_freq"] == "1min"
    # 60 one-minute bars = one funding hour
    assert m["funding_cost"] == pytest.approx(10_000.0 * 0.0001 * 1.0, rel=1e-9)


def test_explicit_frequency_is_honoured_without_timestamps() -> None:
    close = pd.Series(np.linspace(100.0, 110.0, 120))
    entries, exits = _signals(close.index, [(10, 14)])

    m = compute_trial_metrics(
        close,
        entries,
        exits,
        freq="1h",
        cost=_FUNDING_ONLY,
        fixed_notional_fraction=1.0,
        strategy_managed_exits=True,
    )

    assert m["bar_freq"] == "1h"
    assert m["funding_cost"] == pytest.approx(10_000.0 * 0.0001 * 4.0, rel=1e-9)


def test_regime_trend_router_accepts_rangeindex_research_bars() -> None:
    from hypervector.strategies.source_derived import regime_trend_router_signals

    df = _bars(3_000, "1min", seed=21)
    timed = df.set_axis(pd.DatetimeIndex(df["timestamp"]).rename(None), axis=0)

    entries, exits, direction = regime_trend_router_signals(df, direction="long")
    ref_entries, ref_exits, _ = regime_trend_router_signals(timed, direction="long")

    assert direction == "long"
    assert entries.index.equals(df.index)
    assert entries.tolist() == ref_entries.tolist()
    assert exits.tolist() == ref_exits.tolist()
