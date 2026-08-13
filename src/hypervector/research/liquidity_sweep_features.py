"""Causal five-minute aggregation and liquidity-sweep event construction."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.regime.composite import classify_multitimeframe
from hypervector.research.liquidity_sweep_contract import LiquiditySweepConfig


_FEATURE_COLUMNS = frozenset(
    {
        "bar_open_at",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "buy_volume",
        "sell_volume",
        "spread_bps_last",
        "imbalance_5_last",
        "micro_price_delta_bps",
        "context_15m",
        "segment_id",
    }
)


def build_liquidity_sweep_feature_rows(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    books: pd.DataFrame,
    config: LiquiditySweepConfig,
) -> pd.DataFrame:
    """Aggregate complete causal minutes into annotated five-minute bars."""
    _validate_minute_inputs(bars, trades, books)
    merged = bars.merge(trades, on="bar_open_at", validate="one_to_one")
    merged = merged.merge(books, on="bar_open_at", how="left", validate="one_to_one")
    merged["minute_segment"] = _segment_ids(merged["bar_open_at"], minutes=1)
    regimes = _classify_contiguous_regimes(merged)
    rows = _aggregate_complete_buckets(merged, config)
    terminal_times = pd.DatetimeIndex(rows["bar_open_at"]) + pd.Timedelta(minutes=4)
    rows["context_15m"] = regimes["context_15m"].reindex(terminal_times).to_numpy()
    rows["regime_strength"] = regimes["confidence"].reindex(terminal_times).to_numpy()
    rows["segment_id"] = _segment_ids(rows["bar_open_at"], minutes=5)
    rows["trade_flow_imbalance"] = _imbalance(rows["buy_volume"], rows["sell_volume"])
    return rows.reset_index(drop=True)


def build_liquidity_sweep_events(
    features: pd.DataFrame,
    *,
    symbol: str,
    config: LiquiditySweepConfig,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Emit fixed reclaim and acceptance arms and an exclusion audit."""
    missing = sorted(_FEATURE_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"liquidity sweep features missing columns: {missing}")
    normalized = symbol.strip().upper()
    if normalized not in config.symbols:
        raise ValueError(f"unsupported liquidity sweep symbol: {normalized}")
    rows = _attach_prior_structure(features, config)
    audit = _empty_audit()
    records: list[dict[str, object]] = []
    for row in rows.itertuples(index=False):
        reason, record = _classify_event(row, normalized)
        audit[reason] += 1
        if record is not None:
            records.append(record)
    return pd.DataFrame(records, columns=_event_columns()), audit


def _aggregate_complete_buckets(
    rows: pd.DataFrame, config: LiquiditySweepConfig
) -> pd.DataFrame:
    output = rows.copy()
    output["bucket"] = output["bar_open_at"].dt.floor("5min")
    grouped = output.groupby(["minute_segment", "bucket"], sort=True)
    complete = grouped.size().eq(config.bar_minutes)
    eligible = complete.loc[complete].index
    filtered = (
        output.set_index(["minute_segment", "bucket"]).loc[eligible].reset_index()
    )
    grouped = filtered.groupby(["minute_segment", "bucket"], sort=True)
    aggregated = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        buy_volume=("buy_volume", "sum"),
        sell_volume=("sell_volume", "sum"),
        imbalance_5_last=("imbalance_5_last", "last"),
        micro_price_delta_bps=("micro_price_delta_bps", "last"),
        spread_bps_last=("spread_bps_last", "last"),
    ).reset_index()
    return aggregated.rename(columns={"bucket": "bar_open_at"})


def _classify_contiguous_regimes(rows: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, segment in rows.groupby("minute_segment", sort=True):
        indexed = segment.set_index("bar_open_at")
        ohlcv = indexed.loc[:, ["open", "high", "low", "close", "volume"]]
        frames.append(classify_multitimeframe(ohlcv))
    if not frames:
        raise ValueError("liquidity sweep inputs contain no minute segments")
    return pd.concat(frames).sort_index()


def _attach_prior_structure(
    features: pd.DataFrame, config: LiquiditySweepConfig
) -> pd.DataFrame:
    output = features.copy().sort_values("bar_open_at").reset_index(drop=True)
    grouped = output.groupby("segment_id", sort=False)
    window = config.structure_lookback_bars
    output["prior_structure_high"] = grouped["high"].transform(
        lambda values: values.shift(1).rolling(window, min_periods=window).max()
    )
    output["prior_structure_low"] = grouped["low"].transform(
        lambda values: values.shift(1).rolling(window, min_periods=window).min()
    )
    return output


def _classify_event(row: object, symbol: str) -> tuple[str, dict[str, object] | None]:
    prior_high = float(getattr(row, "prior_structure_high"))
    prior_low = float(getattr(row, "prior_structure_low"))
    if not math.isfinite(prior_high) or not math.isfinite(prior_low):
        return "warmup_incomplete", None
    high_sweep = float(getattr(row, "high")) > prior_high
    low_sweep = float(getattr(row, "low")) < prior_low
    if high_sweep and low_sweep:
        return "dual_sweep_ambiguous", None
    if not high_sweep and not low_sweep:
        return "no_sweep", None
    choice = _event_choice(row, high_sweep, prior_high, prior_low)
    if choice is None:
        return "level_close_ambiguous", None
    arm, side, level = choice
    return "emitted", _event_record(row, symbol, arm, side, level)


def _event_choice(
    row: object, high_sweep: bool, prior_high: float, prior_low: float
) -> tuple[str, str, float] | None:
    close = float(getattr(row, "close"))
    if high_sweep and close < prior_high:
        return "sweep_reclaim_reversal", "short", prior_high
    if high_sweep and close > prior_high:
        return "sweep_acceptance_continuation", "long", prior_high
    if not high_sweep and close > prior_low:
        return "sweep_reclaim_reversal", "long", prior_low
    if not high_sweep and close < prior_low:
        return "sweep_acceptance_continuation", "short", prior_low
    return None


def _event_record(
    row: object, symbol: str, arm: str, side: str, level: float
) -> dict[str, object]:
    bar_open = pd.Timestamp(getattr(row, "bar_open_at"))
    return {
        "event_id": f"{symbol}:{bar_open.isoformat()}:{arm}",
        "symbol": symbol,
        "bar_open_at": bar_open,
        "available_at_utc": bar_open + pd.Timedelta(minutes=5),
        "arm": arm,
        "side": side,
        "structural_level": level,
        "protective_extreme": float(getattr(row, "low" if side == "long" else "high")),
        "spread_bps_last": float(getattr(row, "spread_bps_last")),
        "context_15m": str(getattr(row, "context_15m")),
        "regime_strength": float(getattr(row, "regime_strength", math.nan)),
        "trade_flow_imbalance": float(getattr(row, "trade_flow_imbalance", math.nan)),
        "imbalance_5_last": float(getattr(row, "imbalance_5_last")),
        "micro_price_delta_bps": float(getattr(row, "micro_price_delta_bps")),
    }


def _validate_minute_inputs(
    bars: pd.DataFrame, trades: pd.DataFrame, books: pd.DataFrame
) -> None:
    required = {
        "bars": {"bar_open_at", "open", "high", "low", "close", "volume"},
        "trades": {"bar_open_at", "buy_volume", "sell_volume"},
        "books": {
            "bar_open_at",
            "imbalance_5_last",
            "micro_price_delta_bps",
            "spread_bps_last",
        },
    }
    for name, frame in (("bars", bars), ("trades", trades), ("books", books)):
        missing = sorted(required[name].difference(frame.columns))
        if missing:
            raise ValueError(f"liquidity sweep {name} missing columns: {missing}")
    if bars.empty or trades.empty:
        raise ValueError("liquidity sweep price and trade inputs must be non-empty")
    if not bars["bar_open_at"].equals(trades["bar_open_at"]):
        raise ValueError("liquidity sweep trade bars must align with price bars")


def _segment_ids(times: pd.Series, *, minutes: int) -> pd.Series:
    expected = pd.Timedelta(minutes=minutes)
    return pd.to_datetime(times, utc=True).diff().ne(expected).cumsum()


def _imbalance(buy: pd.Series, sell: pd.Series) -> pd.Series:
    total = buy.astype(float) + sell.astype(float)
    return (buy.astype(float) - sell.astype(float)) / total.replace(0.0, np.nan)


def _empty_audit() -> dict[str, int]:
    return {
        "warmup_incomplete": 0,
        "dual_sweep_ambiguous": 0,
        "level_close_ambiguous": 0,
        "no_sweep": 0,
        "emitted": 0,
    }


def _event_columns() -> list[str]:
    return [
        "event_id",
        "symbol",
        "bar_open_at",
        "available_at_utc",
        "arm",
        "side",
        "structural_level",
        "protective_extreme",
        "spread_bps_last",
        "context_15m",
        "regime_strength",
        "trade_flow_imbalance",
        "imbalance_5_last",
        "micro_price_delta_bps",
    ]
