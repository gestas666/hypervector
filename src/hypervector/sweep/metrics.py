"""Trial metrics from VectorBT with costs, TP/SL modes, conviction sizing."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from hypervector.sweep.costs import CostModel, resolve_cost_model
from hypervector.sweep.exits import ExitConfig, apply_exit_mode
from hypervector.sweep.sizing import RiskConfig, conviction_series, risk_pct_from_conviction, size_frac_from_risk

REQUIRED_METRIC_KEYS = (
    "net_pnl",
    "total_return_pct",
    "sharpe",
    "trade_count",
    "wins",
    "losses",
    "win_pct",
    "max_drawdown",
)

EXTENDED_METRIC_KEYS = REQUIRED_METRIC_KEYS + (
    "funding_cost",
    "avg_risk_pct",
    "exit_mode",
    "init_cash",
)


def compute_trial_metrics(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    *,
    direction: str = "long",
    init_cash: float = 10_000.0,
    freq: str = "1min",
    df: pd.DataFrame | None = None,
    cost: CostModel | None = None,
    exit_cfg: ExitConfig | None = None,
    risk_cfg: RiskConfig | None = None,
    conviction: float | pd.Series | None = None,
    apply_costs: bool = True,
) -> dict[str, Any]:
    """VectorBT portfolio with optional fees/slippage, TP/SL, risk sizing, funding drag."""
    import vectorbt as vbt

    cost = cost or resolve_cost_model("hl_taker_default")
    exit_cfg = exit_cfg or ExitConfig(mode="atr")
    risk_cfg = risk_cfg or RiskConfig()

    close = close.astype(float)
    entries = entries.reindex(close.index).fillna(False).astype(bool)
    exits = exits.reindex(close.index).fillna(False).astype(bool)

    work = df if df is not None else pd.DataFrame({"close": close, "high": close, "low": close})
    work = work.reindex(close.index)

    entries, exits, sl_frac, tp_frac = apply_exit_mode(
        work, entries, exits, direction=direction, cfg=exit_cfg
    )

    conv = conviction_series(close.index, conviction, risk_cfg)
    risk_pct = risk_pct_from_conviction(conv, risk_cfg)
    size = size_frac_from_risk(risk_pct, sl_frac, risk_cfg)

    # Infer bar frequency for accurate Sharpe ratio annualization (Bug B4)
    if freq == "1min" and df is not None and len(df) > 1 and isinstance(df.index, pd.DatetimeIndex):
        step_s = int((df.index[1] - df.index[0]).total_seconds())
        if step_s >= 3600:
            freq = f"{step_s // 3600}h"
        elif step_s >= 60:
            freq = f"{step_s // 60}min"

    fees = cost.fees if apply_costs else 0.0
    slippage = cost.slippage if apply_costs else 0.0

    # VectorBT: use size_type="value" with size in USD notional to support leverage > 1.0 (Bug B2)
    notional_size = (size * init_cash).to_numpy(dtype=float)
    common: dict[str, Any] = dict(
        init_cash=init_cash,
        freq=freq,
        fees=fees,
        slippage=slippage,
        size=notional_size,
        size_type="value",
        upon_opposite_entry="ignore",
    )

    # Barrier exits: fixed_rr / atr use hard SL+TP; trail uses VectorBT sl_trail
    if exit_cfg.mode == "trail":
        common["sl_stop"] = sl_frac.to_numpy(dtype=float)
        common["sl_trail"] = True
    elif exit_cfg.mode in ("fixed_rr", "atr"):
        common["sl_stop"] = sl_frac.to_numpy(dtype=float)
        if tp_frac.notna().any():
            common["tp_stop"] = tp_frac.fillna(0.0).to_numpy(dtype=float)

    if direction == "long":
        pf = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            exits=exits,
            **common,
        )
    elif direction == "short":
        pf = vbt.Portfolio.from_signals(
            close,
            entries=False,
            exits=False,
            short_entries=entries,
            short_exits=exits,
            **common,
        )
    else:
        raise ValueError(f"direction must be long|short, got {direction}")

    total_return = float(pf.total_return())
    final_value = float(pf.final_value())
    net_pnl = final_value - init_cash

    try:
        sharpe = float(pf.sharpe_ratio())
        if not np.isfinite(sharpe):
            sharpe = 0.0
    except Exception:
        sharpe = 0.0

    try:
        max_dd = float(pf.max_drawdown())
        if not np.isfinite(max_dd):
            max_dd = 0.0
    except Exception:
        max_dd = 0.0

    trades = pf.trades
    try:
        trade_count = int(trades.count())
    except Exception:
        trade_count = 0

    wins = losses = 0
    win_pct = 0.0
    funding_cost = 0.0
    if trade_count > 0:
        try:
            records = trades.records_readable
            pnl_col = None
            for cand in ("PnL", "pnl", "Return", "return"):
                if cand in records.columns:
                    pnl_col = cand
                    break
            if pnl_col is not None:
                pnls = records[pnl_col].astype(float)
                wins = int((pnls > 0).sum())
                losses = int((pnls <= 0).sum())
            else:
                wins = int(trades.winning.count())
                losses = int(trades.losing.count())
            win_pct = float(wins) / trade_count if trade_count else 0.0

            # Funding drag: duration * notional * rate (research estimate)
            if apply_costs and (cost.funding_rate_1h or cost.funding_rate_8h):
                funding_cost = _estimate_funding(records, cost, close)
                net_pnl -= funding_cost
                final_adj = init_cash + net_pnl
                total_return = (final_adj / init_cash) - 1.0 if init_cash else total_return
        except Exception:
            wins = losses = 0
            win_pct = 0.0

    avg_risk = float(pd.Series(risk_pct).mean()) if trade_count else float(
        risk_pct_from_conviction(risk_cfg.default_conviction, risk_cfg)
    )

    return {
        "net_pnl": float(net_pnl),
        "total_return_pct": float(total_return * 100.0),
        "sharpe": sharpe,
        "trade_count": trade_count,
        "wins": wins,
        "losses": losses,
        "win_pct": win_pct * 100.0 if win_pct <= 1.0 else win_pct,
        "max_drawdown": max_dd,
        "funding_cost": float(funding_cost),
        "avg_risk_pct": avg_risk * 100.0,
        "exit_mode": exit_cfg.mode,
        "init_cash": float(init_cash),
        "fees": fees,
        "slippage_bps": cost.slippage_bps if apply_costs else 0.0,
    }


def _estimate_funding(records: pd.DataFrame, cost: CostModel, close: pd.Series) -> float:
    """Sum |notional| * funding over hold time from trade records if available."""
    total = 0.0
    cols = {c.lower(): c for c in records.columns}
    entry_col = cols.get("avg entry price") or cols.get("entry price")
    size_col = cols.get("size")
    t_in = cols.get("entry timestamp")
    t_out = cols.get("exit timestamp")
    for _, row in records.iterrows():
        try:
            px = float(row[entry_col]) if entry_col else float(close.median())
            sz = abs(float(row[size_col])) if size_col else 0.0
            notional = abs(px * sz)
            if notional <= 0:
                continue
            hold_min = 60.0
            if t_in and t_out and pd.notna(row[t_in]) and pd.notna(row[t_out]):
                delta = pd.Timestamp(row[t_out]) - pd.Timestamp(row[t_in])
                hold_min = max(delta.total_seconds() / 60.0, 1.0)
            total += cost.funding_cost(notional, hold_min)
        except Exception:
            continue
    return total
