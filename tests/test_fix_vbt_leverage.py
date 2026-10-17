"""Regression: leverage must size positions in both directions and respect the venue.

VectorBT caps long buys at free cash (shorts are uncapped), so ``max_size_frac``
above 1 was a no-op for longs and unbounded for shorts. Hyperliquid isolated
liquidation also caps a position's loss near its margin.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from hypervector.sweep.costs import ZERO_COST, CostModel
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import (
    DEFAULT_ALT_LEVERAGE_CAP,
    MAX_VENUE_LEVERAGE,
    RiskConfig,
    maintenance_margin_rate,
    validate_leverage,
    venue_leverage_cap,
)


def _frame(close: list[float]) -> pd.DataFrame:
    """Consistent bars: open = previous close, high/low span open and close."""
    c = np.asarray(close, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-04-01", periods=len(c), freq="1min", tz="UTC"),
            "open": o,
            "high": np.maximum(o, c),
            "low": np.minimum(o, c),
            "close": c,
            "volume": 1.0,
        }
    )


def _one_trade(n: int, entry: int, exit_: int) -> tuple[pd.Series, pd.Series]:
    entries = pd.Series(False, index=pd.RangeIndex(n))
    exits = pd.Series(False, index=pd.RangeIndex(n))
    entries.iloc[entry] = True
    exits.iloc[exit_] = True
    return entries, exits


# Wide fixed stop and target so only the strategy exit closes the trade; the
# requested risk (5%) / stop (1%) = 5x is clipped by max_size_frac (the leverage).
_WIDE = ExitConfig(mode="fixed_rr", sl_pct=0.01, rr=500.0)
_FULL_RISK = dict(risk_pct_min=0.05, risk_pct_max=0.05)


def _run(df: pd.DataFrame, direction: str, leverage: float, **kw: object) -> dict:
    entries, exits = _one_trade(len(df), 2, len(df) - 2)
    return compute_trial_metrics(
        df["close"],
        entries,
        exits,
        direction=direction,
        df=df,
        cost=kw.pop("cost", ZERO_COST),
        exit_cfg=kw.pop("exit_cfg", _WIDE),
        risk_cfg=RiskConfig(max_size_frac=leverage, **_FULL_RISK),
        **kw,
    )


def test_long_pnl_scales_with_leverage() -> None:
    df = _frame([100.0, 100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 104.0])
    one = _run(df, "long", 1.0)
    three = _run(df, "long", 3.0)

    assert one["net_pnl"] == pytest.approx(10_000.0 * 0.04, rel=1e-9)
    assert three["net_pnl"] == pytest.approx(3.0 * one["net_pnl"], rel=1e-9)
    assert three["max_position_leverage"] == pytest.approx(3.0)


def test_short_pnl_scales_with_leverage() -> None:
    df = _frame([100.0, 100.0, 100.0, 99.0, 98.0, 97.0, 96.0, 96.0])
    one = _run(df, "short", 1.0)
    four = _run(df, "short", 4.0)

    assert one["net_pnl"] == pytest.approx(10_000.0 * 0.04, rel=1e-9)
    assert four["net_pnl"] == pytest.approx(4.0 * one["net_pnl"], rel=1e-9)


def test_one_x_long_is_not_shrunk_by_entry_fees() -> None:
    """A 1x long used to be cut to the cash left after fees ($9,998.50)."""
    df = _frame([100.0, 100.0, 100.0, 100.0, 110.0, 110.0])
    taker = CostModel(taker_fee=0.00015, slippage_bps=0.0, funding_rate_1h=0.0)
    m = _run(df, "long", 1.0, cost=taker)

    units = 10_000.0 / 100.0
    expected = units * (110.0 - 100.0) - 0.00015 * units * (100.0 + 110.0)
    assert m["net_pnl"] == pytest.approx(expected, rel=1e-9)


def test_isolated_loss_is_capped_near_margin_by_liquidation() -> None:
    """30x isolated on 70% margin: a 21% adverse move cannot lose 21 x equity."""
    closes = [100.0, 100.0, 100.0] + list(np.linspace(99.5, 79.0, 20)) + [79.0, 79.0]
    df = _frame(closes)
    entries, exits = _one_trade(len(df), 2, len(df) - 2)

    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        df=df,
        cost=ZERO_COST,
        fixed_notional_fraction=21.0,
        fixed_margin_fraction=0.70,
        strategy_managed_exits=True,
        symbol="BTC",
    )

    margin = 0.70 * 10_000.0
    mmr = 1.0 / (2.0 * 40.0)
    liq_move = (1.0 / 30.0 - mmr) / (1.0 - mmr)
    assert m["liquidations"] == 1
    assert m["maintenance_margin_rate"] == pytest.approx(mmr)
    assert -m["net_pnl"] <= margin
    assert m["net_pnl"] == pytest.approx(-210_000.0 * liq_move, rel=1e-9)


def test_short_liquidation_bounds_loss_at_high_leverage() -> None:
    closes = [100.0, 100.0, 100.0] + list(np.linspace(100.5, 110.0, 12)) + [110.0, 110.0]
    df = _frame(closes)
    entries, exits = _one_trade(len(df), 2, len(df) - 2)
    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        direction="short",
        df=df,
        cost=ZERO_COST,
        fixed_notional_fraction=40.0,
        strategy_managed_exits=True,
        symbol="BTC",
    )

    mmr = 1.0 / 80.0
    liq_move = (1.0 / 40.0 - mmr) / (1.0 + mmr)
    assert m["liquidations"] == 1
    assert m["net_pnl"] == pytest.approx(-400_000.0 * liq_move, rel=1e-9)
    assert -m["net_pnl"] < 10_000.0


def test_drawdown_is_measured_on_real_equity() -> None:
    closes = [100.0, 100.0, 100.0, 100.5, 101.0, 101.0, 101.0, 100.7, 100.5, 100.5]
    df = _frame(closes)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[[2, 6]] = True
    exits.iloc[[4, 8]] = True

    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        df=df,
        cost=ZERO_COST,
        fixed_notional_fraction=21.0,
        fixed_margin_fraction=0.70,
        strategy_managed_exits=True,
    )

    peak = 10_000.0 + 210_000.0 * 0.01
    trough = peak + 210_000.0 * (100.5 / 101.0 - 1.0)
    assert m["net_pnl"] == pytest.approx(trough - 10_000.0, rel=1e-9)
    assert m["max_drawdown"] == pytest.approx(trough / peak - 1.0, rel=1e-9)
    assert m["min_equity"] == pytest.approx(10_000.0)
    assert m["equity_depleted"] is False


def test_depleted_account_is_reported_not_hidden() -> None:
    """Fixed notional keeps trading after ruin; the result says so explicitly."""
    closes = [100.0, 100.0, 100.0, 95.0, 88.0, 85.0, 85.0, 80.0, 74.0, 70.0, 70.0]
    df = _frame(closes)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[[2, 6]] = True
    exits.iloc[[5, 9]] = True

    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        df=df,
        cost=ZERO_COST,
        fixed_notional_fraction=10.0,
        strategy_managed_exits=True,
    )

    # 10x, no venue symbol: liquidation at a full loss of margin (-10%)
    assert m["liquidations"] == 2
    assert m["net_pnl"] == pytest.approx(-20_000.0, rel=1e-9)
    assert m["min_equity"] == pytest.approx(-10_000.0, rel=1e-9)
    assert m["equity_depleted"] is True
    assert m["max_drawdown"] == -1.0
    assert math.isfinite(m["sharpe"]) and m["sharpe"] < 0.0


def test_venue_leverage_caps() -> None:
    assert venue_leverage_cap("BTC") == 40.0
    assert venue_leverage_cap("eth") == 25.0
    assert venue_leverage_cap("SOL") == 20.0
    assert venue_leverage_cap("HYPE") == 10.0
    assert venue_leverage_cap("SOMEALT") == DEFAULT_ALT_LEVERAGE_CAP
    assert venue_leverage_cap(None) == MAX_VENUE_LEVERAGE == 40.0
    # venue metadata wins for unlisted assets but never lifts a charter cap
    assert venue_leverage_cap("SOMEALT", venue_max_leverage=3) == 3.0
    assert venue_leverage_cap("BTC", venue_max_leverage=50) == 40.0
    assert maintenance_margin_rate(40.0) == pytest.approx(0.0125)

    assert validate_leverage(40.0, symbol="BTC") == 40.0
    for bad, symbol in ((41.0, "BTC"), (26.0, "ETH"), (21.0, "SOL"), (11.0, "HYPE"), (11.0, "SOMEALT")):
        with pytest.raises(ValueError, match="leverage"):
            validate_leverage(bad, symbol=symbol)
    for bad in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(ValueError, match="leverage"):
            validate_leverage(bad, symbol="BTC")


def test_risk_config_rejects_non_positive_leverage() -> None:
    for bad in (0.0, -2.0, math.nan, math.inf):
        with pytest.raises(ValueError):
            RiskConfig(max_size_frac=bad)


def test_grid_search_applies_the_symbol_venue_cap() -> None:
    from hypervector.data.sources import fixture_ohlcv
    from hypervector.strategies.registry import StrategySpec
    from hypervector.sweep.search import run_grid_search

    df = fixture_ohlcv(n_bars=300, drift=2.0, wave_period=40)
    spec = StrategySpec(
        name="probe_long",
        role="uptrend",
        param_grid={},
        build_signals=lambda frame: (
            pd.Series([i % 60 == 5 for i in range(len(frame))], index=frame.index),
            pd.Series([i % 60 == 30 for i in range(len(frame))], index=frame.index),
            "long",
        ),
    )
    risk = RiskConfig(max_size_frac=25.0)

    [eth] = run_grid_search(df, spec, risk_cfg=risk, symbol="ETH")
    [sol] = run_grid_search(df, spec, risk_cfg=risk, symbol="SOL")

    assert eth.status == "ok"
    assert eth.metrics["venue_leverage_cap"] == 25.0
    assert eth.metrics["maintenance_margin_rate"] == pytest.approx(0.02)
    assert sol.status == "error" and "20x" in (sol.error or "")


def test_trial_refuses_leverage_above_the_venue_cap() -> None:
    df = _frame([100.0] * 10)
    with pytest.raises(ValueError, match="ETH"):
        _run(df, "long", 26.0, symbol="ETH")
    with pytest.raises(ValueError, match="leverage"):
        _run(df, "short", 200.0)  # no symbol: the charter maximum still applies
    with pytest.raises(ValueError, match="leverage"):
        compute_trial_metrics(
            df["close"],
            *_one_trade(len(df), 2, 5),
            df=df,
            cost=ZERO_COST,
            fixed_notional_fraction=21.0,
            fixed_margin_fraction=0.70,
            strategy_managed_exits=True,
            symbol="SOMEALT",
        )
