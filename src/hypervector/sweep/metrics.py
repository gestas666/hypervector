"""Trial metrics from VectorBT with costs, TP/SL modes, conviction sizing and leverage.

Model (reported on every result so rows can be told apart):

* **Time axis.** Research bars carry a RangeIndex plus a ``timestamp`` column.
  Bar times come from a DatetimeIndex or that column (never from integer
  positions); they set the Sharpe annualisation frequency (median bar step)
  and the funding hold time of each trade.
* **Leverage.** Position notional is ``size x init_cash`` (non-compounding).
  VectorBT caps long buys at free cash, so its broker is funded with a large
  virtual cash base and every reported figure (P&L, drawdown, Sharpe) is
  measured on the real equity ``init_cash + (value - virtual_cash)``. Leverage
  above the Hyperliquid venue cap is refused (ValueError), never clamped.
* **Isolated liquidation.** Each position carries a liquidation barrier at the
  adverse move where its margin (``notional / leverage``) falls to the venue
  maintenance margin; it merges with the strategy stop (whichever is nearer).
  A gap through the barrier still loses at most the margin: the excess is
  credited back (``loss_beyond_margin_absorbed``), as the venue backstop would.
  This is venue mechanics, not a strategy gate.
* **Intrabar stops.** SL/TP/trail/liquidation are evaluated against the bar's
  open/high/low and filled as stop-market orders, so configured slippage
  applies. Gaps fill at the open; SL wins a same-bar SL/TP tie.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from hypervector.sweep.costs import DEFAULT_COST_MODEL, CostModel, resolve_cost_model
from hypervector.sweep.exits import ExitConfig, apply_exit_mode
from hypervector.sweep.sizing import (
    RiskConfig,
    conviction_series,
    maintenance_margin_rate,
    risk_pct_from_conviction,
    size_frac_from_risk,
    validate_leverage,
    venue_leverage_cap,
)

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

# VectorBT's broker cash = init_cash x max notional fraction x this headroom, so
# free cash never limits an order (checked after every simulation).
_VIRTUAL_CASH_HEADROOM = 1_000.0
_YEAR = pd.Timedelta(days=365)


def compute_trial_metrics(
    close: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    *,
    direction: str = "long",
    init_cash: float = 10_000.0,
    freq: str | None = None,
    df: pd.DataFrame | None = None,
    cost: CostModel | None = None,
    exit_cfg: ExitConfig | None = None,
    risk_cfg: RiskConfig | None = None,
    conviction: float | pd.Series | None = None,
    apply_costs: bool = True,
    fixed_notional_fraction: float | None = None,
    fixed_margin_fraction: float | None = None,
    strategy_managed_exits: bool = False,
    symbol: str | None = None,
    venue_max_leverage: float | None = None,
    intrabar_stops: bool = True,
) -> dict[str, Any]:
    """VectorBT portfolio with costs, TP/SL, leverage, liquidation and funding drag.

    ``freq`` overrides the bar frequency inferred from bar timestamps.
    ``symbol`` / ``venue_max_leverage`` select the venue leverage cap and the
    maintenance margin; without them the charter maximum (40x) bounds the
    leverage and liquidation is placed at a full loss of margin.
    ``intrabar_stops=False`` reproduces legacy close-only, zero-slippage stops.
    """
    import vectorbt as vbt

    if direction not in ("long", "short"):
        raise ValueError(f"direction must be long|short, got {direction}")
    if not (math.isfinite(float(init_cash)) and init_cash > 0.0):
        raise ValueError(f"init_cash must be positive, got {init_cash!r}")
    cost = cost or resolve_cost_model(DEFAULT_COST_MODEL)
    exit_cfg = exit_cfg or ExitConfig(mode="atr")
    risk_cfg = risk_cfg or RiskConfig()

    close = close.astype(float)
    entries = entries.reindex(close.index).fillna(False).astype(bool)
    exits = exits.reindex(close.index).fillna(False).astype(bool)

    work = (
        df
        if df is not None
        else pd.DataFrame({"close": close, "high": close, "low": close})
    )
    work = work.reindex(close.index)

    bar_ns = _bar_times_ns(close.index, work)
    if freq is None:
        freq = _infer_freq(bar_ns) or "1min"
    bar_minutes = pd.Timedelta(freq).total_seconds() / 60.0

    if strategy_managed_exits:
        sl_frac = pd.Series(np.nan, index=close.index, dtype=float)
        tp_frac = pd.Series(np.nan, index=close.index, dtype=float)
    else:
        entries, exits, sl_frac, tp_frac = apply_exit_mode(
            work, entries, exits, direction=direction, cfg=exit_cfg
        )

    conv = conviction_series(close.index, conviction, risk_cfg)
    risk_pct = risk_pct_from_conviction(conv, risk_cfg)
    if fixed_notional_fraction is None:
        size = size_frac_from_risk(risk_pct, sl_frac, risk_cfg)
        leverage_cap = float(risk_cfg.max_size_frac)
        position_leverage = size.to_numpy(dtype=float)
    else:
        if not fixed_notional_fraction > 0.0:
            raise ValueError("fixed_notional_fraction must be positive")
        size = pd.Series(fixed_notional_fraction, index=close.index, dtype=float)
        leverage_cap = float(fixed_notional_fraction)
        if fixed_margin_fraction is not None:
            if not fixed_margin_fraction > 0.0:
                raise ValueError("fixed_margin_fraction must be positive")
            leverage_cap = float(fixed_notional_fraction) / float(fixed_margin_fraction)
        position_leverage = np.full(len(close), leverage_cap)

    venue_known = symbol is not None or venue_max_leverage is not None
    venue_cap = venue_leverage_cap(symbol, venue_max_leverage)
    validate_leverage(leverage_cap, symbol=symbol, venue_max_leverage=venue_max_leverage)
    mmr = maintenance_margin_rate(venue_cap) if venue_known else 0.0
    liq_frac = _liquidation_distance(position_leverage, mmr, direction)
    sl_raw = sl_frac.to_numpy(dtype=float)
    sl_effective = np.fmin(sl_raw, liq_frac)

    fees = cost.fees if apply_costs else 0.0
    slippage = cost.slippage if apply_costs else 0.0

    notional_size = (size * init_cash).to_numpy(dtype=float)
    max_fraction = float(np.nanmax(notional_size)) / init_cash if len(close) else 0.0
    virtual_cash = init_cash * max(1.0, max_fraction) * _VIRTUAL_CASH_HEADROOM
    common: dict[str, Any] = dict(
        init_cash=virtual_cash,
        freq=freq,
        fees=fees,
        slippage=slippage,
        size=notional_size,
        size_type="value",
        upon_opposite_entry="ignore",
    )

    # One stop slot: strategy SL / ATR trail merged with the liquidation barrier.
    common["sl_stop"] = sl_effective
    if exit_cfg.mode == "trail" and not strategy_managed_exits:
        common["sl_trail"] = True
    if exit_cfg.mode in ("fixed_rr", "atr") and tp_frac.notna().any():
        common["tp_stop"] = tp_frac.fillna(0.0).to_numpy(dtype=float)
    if intrabar_stops:
        for column in ("open", "high", "low"):
            if column in work.columns:
                common[column] = work[column].astype(float).to_numpy()
        common["stop_exit_price"] = "stopmarket"

    if direction == "long":
        pf = vbt.Portfolio.from_signals(close, entries=entries, exits=exits, **common)
    else:
        pf = vbt.Portfolio.from_signals(
            close,
            entries=False,
            exits=False,
            short_entries=entries,
            short_exits=exits,
            **common,
        )

    _require_unbound_cash(pf, virtual_cash)
    records = pf.trades.records_arr
    real_equity = init_cash + (pf.value().to_numpy(dtype=float) - virtual_cash)
    margin_credit = _loss_beyond_margin(records, position_leverage, len(real_equity))
    real_equity = real_equity + margin_credit
    net_pnl = float(real_equity[-1] - init_cash) if len(real_equity) else 0.0
    sharpe = _sharpe(real_equity, init_cash, freq)
    max_dd = _max_drawdown(real_equity, init_cash)
    min_equity = float(min(init_cash, real_equity.min())) if len(real_equity) else init_cash

    trade_count = int(len(records))
    pnls = records["pnl"].astype(float)
    wins = int((pnls > 0).sum())
    losses = int((pnls <= 0).sum())
    win_pct = float(wins) / trade_count if trade_count else 0.0
    entry_idx = records["entry_idx"].astype(np.int64)
    exit_idx = records["exit_idx"].astype(np.int64)
    notional = np.abs(records["size"] * records["entry_price"]).astype(float)

    funding_cost = 0.0
    if trade_count and apply_costs and (cost.funding_rate_1h or cost.funding_rate_8h):
        funding_cost = _funding(notional, entry_idx, exit_idx, bar_ns, bar_minutes, cost)
        net_pnl -= funding_cost
    total_return = net_pnl / init_cash

    liquidations = _count_liquidations(
        records, close.to_numpy(dtype=float), liq_frac, sl_raw, direction
    )

    avg_risk = (
        float(pd.Series(risk_pct).mean())
        if trade_count
        else float(risk_pct_from_conviction(risk_cfg.default_conviction, risk_cfg))
    )
    requested_risk = avg_risk
    if trade_count and isinstance(risk_pct, pd.Series):
        requested_risk = float(risk_pct.to_numpy(dtype=float)[entry_idx].mean())
    if fixed_margin_fraction is not None:
        avg_risk = requested_risk = fixed_margin_fraction
    effective_risk = _effective_risk_pct(notional, sl_effective[entry_idx], init_cash)
    cap_bound = None
    if fixed_notional_fraction is None and trade_count:
        requested_size = np.asarray(risk_pct, dtype=float) / sl_raw.clip(min=1e-6)
        requested_size = np.broadcast_to(requested_size, sl_raw.shape)[entry_idx]
        cap_bound = float(np.mean(requested_size > risk_cfg.max_size_frac))

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
        "requested_risk_pct": requested_risk * 100.0,
        "effective_risk_pct": effective_risk,
        "size_cap_bound_fraction": cap_bound,
        "exit_mode": exit_cfg.mode,
        "init_cash": float(init_cash),
        "fees": fees,
        "slippage_bps": cost.slippage_bps if apply_costs else 0.0,
        "position_notional_fraction": fixed_notional_fraction,
        "strategy_managed_exits": strategy_managed_exits,
        "sizing_model": (
            "fixed_initial_equity_proxy"
            if fixed_notional_fraction is not None
            else "conviction_stop_risk"
        ),
        "bar_freq": freq,
        "funding_hold_basis": "bar_timestamps" if bar_ns is not None else "bar_count",
        "leverage_cap": leverage_cap,
        "max_position_leverage": (
            float(notional.max() / init_cash) if trade_count else 0.0
        ),
        "venue_leverage_cap": venue_cap,
        "maintenance_margin_rate": mmr,
        "liquidations": liquidations,
        "loss_beyond_margin_absorbed": (
            float(margin_credit[-1]) if len(margin_credit) else 0.0
        ),
        "min_equity": min_equity,
        "equity_depleted": bool(min_equity <= 0.0),
        "leverage_model": "virtual_cash_isolated_liquidation",
        "stop_fill_model": (
            "intrabar_ohlc_stopmarket" if intrabar_stops else "close_only_stoplimit"
        ),
    }


def _bar_times_ns(index: pd.Index, work: pd.DataFrame) -> np.ndarray | None:
    """UTC bar times as int64 nanoseconds, from the index or a timestamp column."""
    if isinstance(index, pd.DatetimeIndex):
        times = index
    elif "timestamp" in work.columns:
        column = work["timestamp"]
        if column.isna().any() or pd.api.types.is_numeric_dtype(column):
            return None  # never reinterpret integers as nanoseconds
        if pd.api.types.is_datetime64_any_dtype(column.dtype):
            # Already datetime (the cached frames): no per-trial re-parse.
            # A naive column is read as UTC, exactly as to_datetime(utc=True).
            times = pd.DatetimeIndex(column)
        else:
            times = pd.DatetimeIndex(pd.to_datetime(column, utc=True))
    else:
        return None
    if times.tz is not None:
        times = times.tz_convert("UTC").tz_localize(None)
    return np.asarray(times.as_unit("ns").asi8, dtype=np.int64)


def _infer_freq(bar_ns: np.ndarray | None) -> str | None:
    """Median bar step as a pandas frequency string (robust to data gaps)."""
    if bar_ns is None or len(bar_ns) < 2:
        return None
    steps = np.diff(bar_ns)
    steps = steps[steps > 0]
    if not len(steps):
        return None
    step_s = int(round(float(np.median(steps)) / 1e9))
    if step_s <= 0:
        return None
    if step_s % 3600 == 0:
        return f"{step_s // 3600}h"
    if step_s % 60 == 0:
        return f"{step_s // 60}min"
    return f"{step_s}s"


def _liquidation_distance(
    leverage: np.ndarray, mmr: float, direction: str
) -> np.ndarray:
    """Adverse price move (fraction of entry) at which isolated margin hits maintenance.

    Long: (1/L - mmr) / (1 - mmr); short: (1/L - mmr) / (1 + mmr). NaN where no
    position can open (zero size) or the barrier lies at or beyond a zero price.
    """
    lev = np.asarray(leverage, dtype=float)
    out = np.full(lev.shape, np.nan)
    live = np.isfinite(lev) & (lev > 0.0)
    margin = 1.0 / lev[live]
    if direction == "long":
        dist = (margin - mmr) / (1.0 - mmr)
        dist = np.where(dist < 1.0, dist, np.nan)
    else:
        dist = (margin - mmr) / (1.0 + mmr)
    out[live] = dist
    return out


def _loss_beyond_margin(
    records: np.ndarray, position_leverage: np.ndarray, n_bars: int
) -> np.ndarray:
    """Cumulative per-bar credit for closed losses beyond the position's margin.

    A position cannot lose more than its margin (notional / leverage at entry):
    the venue's backstop liquidation absorbs the rest. VectorBT fills a gap
    through the liquidation barrier at the bar open, which can exceed the
    margin, so the excess is credited back from that trade's exit bar.
    """
    credit = np.zeros(n_bars)
    if not len(records) or not n_bars:
        return credit
    entry_idx = records["entry_idx"].astype(np.int64)
    leverage = np.asarray(position_leverage, dtype=float)[entry_idx]
    notional = np.abs(records["size"] * records["entry_price"]).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        margin = np.where(
            np.isfinite(leverage) & (leverage > 0.0), notional / leverage, np.inf
        )
    excess = np.maximum(-records["pnl"].astype(float) - margin, 0.0)
    excess = np.where(records["status"] == 1, excess, 0.0)
    hit = excess > 0.0
    np.add.at(credit, records["exit_idx"].astype(np.int64)[hit], excess[hit])
    return np.cumsum(credit)


def _require_unbound_cash(pf: Any, virtual_cash: float) -> None:
    """Fail the trial (technical error) if the virtual broker ever ran out of cash."""
    cash = np.asarray(pf.cash(), dtype=float)
    if len(cash) and float(np.min(cash)) <= virtual_cash * 1e-9:
        raise RuntimeError(
            "virtual cash base exhausted; leverage accounting would be cash-capped"
        )


def _sharpe(real_equity: np.ndarray, init_cash: float, freq: str) -> float:
    """Annualised Sharpe of real-equity bar returns (same definition as VectorBT).

    Returns are undefined once equity is gone, so a depleted account is
    measured up to the bar that wiped it out, with that bar's return at -100%.
    """
    if len(real_equity) < 2:
        return 0.0
    previous = np.concatenate([[init_cash], real_equity[:-1]])
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = real_equity / previous - 1.0
    depleted = np.flatnonzero(real_equity <= 0.0)
    if len(depleted):
        returns = returns[: depleted[0] + 1].copy()
        returns[-1] = -1.0
        if len(returns) < 2:
            return 0.0
    try:
        ann_factor = _YEAR / pd.Timedelta(freq)
        mean = float(np.nanmean(returns))
        std = float(np.nanstd(returns, ddof=1))
        sharpe = mean / std * math.sqrt(ann_factor) if std > 0.0 else 0.0
    except (ValueError, ZeroDivisionError, FloatingPointError):
        return 0.0
    return sharpe if math.isfinite(sharpe) else 0.0


def _max_drawdown(real_equity: np.ndarray, init_cash: float) -> float:
    """Largest peak-to-trough fall of real equity, as a negative fraction.

    Floored at -1.0 (the whole account); ``min_equity`` reports how far the
    non-compounding P&L went below zero.
    """
    if not len(real_equity):
        return 0.0
    peaks = np.maximum.accumulate(np.concatenate([[init_cash], real_equity]))[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = real_equity / peaks - 1.0
    value = float(np.nanmin(drawdown)) if np.isfinite(drawdown).any() else 0.0
    return max(value, -1.0) if math.isfinite(value) else 0.0


def _funding(
    notional: np.ndarray,
    entry_idx: np.ndarray,
    exit_idx: np.ndarray,
    bar_ns: np.ndarray | None,
    bar_minutes: float,
    cost: CostModel,
) -> float:
    """Sum |notional| x |hourly rate| x hold hours over trades (hold >= 1 minute)."""
    if bar_ns is not None:
        hold_min = (bar_ns[exit_idx] - bar_ns[entry_idx]) / 6.0e10
    else:
        hold_min = (exit_idx - entry_idx) * bar_minutes
    hold_min = np.maximum(hold_min.astype(float), 1.0)
    live = notional > 0.0
    periods = hold_min[live] / cost.minutes_per_funding
    return float(np.sum(notional[live] * abs(cost.funding_rate_1h) * periods))


def _count_liquidations(
    records: np.ndarray,
    close: np.ndarray,
    liq_frac: np.ndarray,
    sl_frac: np.ndarray,
    direction: str,
) -> int:
    """Closed trades whose exit reached the liquidation barrier set at entry."""
    if not len(records):
        return 0
    closed = records["status"] == 1
    entry_idx = records["entry_idx"].astype(np.int64)
    liq = liq_frac[entry_idx]
    binds = np.isfinite(liq) & ~(sl_frac[entry_idx] < liq)
    ref = close[entry_idx]
    exit_price = records["exit_price"].astype(float)
    if direction == "long":
        hit = exit_price <= ref * (1.0 - liq) * (1.0 + 1e-12)
    else:
        hit = exit_price >= ref * (1.0 + liq) * (1.0 - 1e-12)
    return int(np.sum(closed & binds & hit))


def _effective_risk_pct(
    notional: np.ndarray, stop_frac: np.ndarray, init_cash: float
) -> float | None:
    """Mean realised risk per trade: filled notional x stop distance / equity, in %."""
    finite = np.isfinite(stop_frac)
    if not finite.any():
        return None
    return float(np.mean(notional[finite] * stop_frac[finite]) / init_cash * 100.0)
