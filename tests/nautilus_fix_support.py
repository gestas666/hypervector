"""Shared synthetic data, exports and test strategies for the Nautilus fix tests.

Offline only: synthetic OHLCV, tmp_path exports, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from hypervector.export.phase2 import export_candidate
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import StrategySpec, register

FIXTEST_ENTER_AT = "fixtest_enter_at"
FIXTEST_RAISE_AFTER = "fixtest_raise_after"
FIXTEST_LOOKAHEAD = "fixtest_lookahead_long"


def synth_ohlcv(
    n: int = 600,
    *,
    freq: str = "15min",
    seed: int = 7,
    start: str = "2026-01-01",
    base: float = 60_000.0,
    vol: float = 0.004,
    decimals: int = 1,
) -> pd.DataFrame:
    """Seeded random-walk OHLCV with a slow sine drift (research column layout)."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0, vol, n) + 0.0004 * np.sin(np.arange(n) / 60.0)
    close = base * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[base], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
            "open": open_.round(decimals),
            "high": high.round(decimals),
            "low": low.round(decimals),
            "close": close.round(decimals),
            "volume": rng.uniform(1, 100, n).round(3),
        }
    )
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    return df


def write_export(
    root: Path,
    *,
    strategy: str = "ma_cross_long",
    params: dict[str, Any] | None = None,
    exit_mode: str = "fixed_rr",
    symbol: str = "BTC",
    timeframe: str = "15m",
    costs: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    extra_meta: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    run_id: str = "fix01",
    exits: dict[str, Any] | None = None,
) -> Path:
    """Strict Phase 1.5 export (same shape the runner tests use)."""
    exit_dict: dict[str, Any] = {
        "mode": exit_mode,
        "sl_pct": 0.01,
        "rr": 2.0,
        "atr_length": 14,
        "sl_atr_mult": 1.5,
        "trail_atr_mult": 2.0,
    }
    exit_dict.update(exits or {})
    meta: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "track": "uptrend",
        "lookback_days": 30,
        "init_cash": 10_000.0,
        "tp_sl_mode": exit_mode,
        "exits": exit_dict,
        "costs": costs
        if costs is not None
        else {
            "taker_fee": 0.00035,
            "slippage_bps": 2.0,
            "funding_rate_8h": 0.0001,
            "minutes_per_funding": 480,
        },
        "risk": risk
        if risk is not None
        else {
            "risk_pct_min": 0.01,
            "risk_pct_max": 0.05,
            "default_conviction": 0.5,
            "max_size_frac": 1.0,
        },
        "data_provenance": {"sources": {"fixture": 1}},
    }
    if extra_meta:
        meta.update(extra_meta)
    base_params: dict[str, Any] = {"strategy": strategy, "exit_mode": exit_mode}
    if strategy == "ma_cross_long" and not params:
        base_params.update({"fast": 5, "slow": 20})
    if params:
        base_params.update(params)
    return export_candidate(
        root / "exports",
        run_id=run_id,
        meta=meta,
        params=base_params,
        metrics=metrics
        or {"net_pnl": 0.0, "total_return_pct": 0.0, "sharpe": 0.0, "trade_count": 0},
        candidate_id=f"fix_{strategy}_{run_id}",
        strict=True,
    )


def _enter_at(
    df: pd.DataFrame,
    *,
    entry_ts: str = "",
    direction: str = "long",
    exit_ts: str = "",
) -> tuple[pd.Series, pd.Series, str]:
    """Enter exactly at ``entry_ts`` (bar-open label); optional exit; causal."""
    index = (
        df.index
        if isinstance(df.index, pd.DatetimeIndex)
        else pd.DatetimeIndex(df["timestamp"])
    )
    entries = pd.Series(index == pd.Timestamp(entry_ts), index=df.index)
    exits = pd.Series(
        index == pd.Timestamp(exit_ts) if exit_ts else False, index=df.index
    ).astype(bool)
    return entries, exits, direction


def _raise_after(
    df: pd.DataFrame, *, max_rows: int = 50
) -> tuple[pd.Series, pd.Series, str]:
    """Builder that fails once it sees more than ``max_rows`` bars."""
    if len(df) > int(max_rows):
        raise ValueError(f"fixtest builder refuses {len(df)} rows")
    flat = pd.Series(False, index=df.index)
    return flat, flat.copy(), "long"


def _lookahead(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, str]:
    """Non-causal builder: peeks at the next close (lookahead)."""
    close = df["close"].astype(float)
    nxt = close.shift(-1)
    entries = (nxt > close * 1.002).fillna(False)
    exits = (nxt < close * 0.998).fillna(False)
    return entries.astype(bool), exits.astype(bool), "long"


def register_fix_strategies() -> None:
    register_all_strategies()
    register(StrategySpec(FIXTEST_ENTER_AT, "other", {}, _enter_at, "test only"))
    register(StrategySpec(FIXTEST_RAISE_AFTER, "other", {}, _raise_after, "test only"))
    register(StrategySpec(FIXTEST_LOOKAHEAD, "other", {}, _lookahead, "test only"))


def capture_engine(monkeypatch: Any) -> dict[str, Any]:
    """Patch the runner's engine class to snapshot orders/fills before dispose."""
    import hypervector.nautilus.runner as runner_mod

    captured: dict[str, Any] = {}
    base_cls = runner_mod.BacktestEngine

    class _CapturingEngine(base_cls):  # type: ignore[misc, valid-type]
        def dispose(self) -> None:
            orders = []
            for order in self.cache.orders():
                orders.append(
                    {
                        "side": str(order.side_string()),
                        "type": str(order.type_string()),
                        "status": str(order.status_string()),
                        "ts_init": int(order.ts_init),
                        "ts_last": int(order.ts_last),
                        "quantity": float(order.quantity.as_double()),
                        "filled_qty": float(order.filled_qty.as_double()),
                        "avg_px": float(order.avg_px) if order.avg_px else None,
                    }
                )
            captured["orders"] = sorted(orders, key=lambda r: (r["ts_init"], r["side"]))
            captured["fills"] = [o for o in captured["orders"] if o["filled_qty"] > 0]
            captured["instrument"] = next(iter(self.cache.instruments()), None)
            try:
                captured["positions_report_rows"] = len(
                    self.trader.generate_positions_report()
                )
                captured["equity"] = sum(
                    m.as_double()
                    for m in self.portfolio.equity(self.list_venues()[0]).values()
                )
            except Exception as exc:  # pragma: no cover - diagnostics only
                captured["report_error"] = repr(exc)
            super().dispose()

    monkeypatch.setattr(runner_mod, "BacktestEngine", _CapturingEngine)
    return captured
