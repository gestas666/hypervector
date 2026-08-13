"""Venue mark and public-trade path supplementation for HIP-3 L2 bars."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import duckdb
import pandas as pd

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_midpoint_bars import Hip3MidpointBars

_RISK_PATH_SOURCE = "0xarchive_mark_price_with_public_trade_context_v1"
_MAXIMUM_MARK_GAP_MS = 5_000.0


@dataclass(frozen=True)
class Hip3VenuePathBars:
    """Midpoint signal bars with mark-trigger and trade-tape path evidence."""

    bars: pd.DataFrame
    mark_rows: int
    trade_rows: int
    mark_complete_bars: int
    unresolved_mark_bars: int
    trade_bundle_complete: bool
    execution_authority: str = "none"


def load_hip3_public_trades(
    database_path: Path,
    *,
    symbol: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
) -> pd.DataFrame:
    """Load exact deduplicated venue trade prints from the research database."""
    validate_market_symbol(symbol, "hip3")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        frame = connection.execute(
            """
            SELECT trade_id, ts_exchange_ms, ts_utc, price, size, aggressor_side
            FROM replay_public_trades
            WHERE symbol = ? AND ts_utc >= ? AND ts_utc < ?
            ORDER BY ts_exchange_ms, trade_id
            """,
            [symbol, start_utc, end_utc],
        ).df()
    return frame


def build_hip3_venue_path_bars(
    midpoint: Hip3MidpointBars,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    bar_minutes: int,
    trade_bundle_complete: bool,
) -> Hip3VenuePathBars:
    """Attach causal mark extrema and independently measured trade context."""
    _validate_request(midpoint, trades, prices, bar_minutes, trade_bundle_complete)
    marks = _mark_bars(prices, midpoint.bars, bar_minutes)
    tape = _trade_bars(trades, bar_minutes)
    bars = midpoint.bars.join(marks, how="left").join(tape, how="left")
    _fill_path_fields(bars, trade_bundle_complete)
    _fill_signal_ohlc_fields(bars)
    complete = bars["mark_path_complete"].astype(bool)
    return Hip3VenuePathBars(
        bars,
        len(prices),
        len(trades),
        int(complete.sum()),
        int((~complete).sum()),
        trade_bundle_complete,
    )


def _mark_bars(
    prices: pd.DataFrame,
    midpoint_bars: pd.DataFrame,
    bar_minutes: int,
) -> pd.DataFrame:
    values = prices.sort_values("ts_ms", kind="stable").copy()
    values["timestamp"] = pd.to_datetime(values["ts_ms"], unit="ms", utc=True)
    values["bar_open"] = values["timestamp"].dt.floor(f"{bar_minutes}min")
    values["prior_ms"] = values.groupby("bar_open")["ts_ms"].diff()
    grouped = values.groupby("bar_open", sort=True)
    interval_ms = bar_minutes * 60_000
    output = grouped.agg(
        mark_high=("mark_price", "max"),
        mark_low=("mark_price", "min"),
        mark_snapshot_count=("mark_price", "size"),
        first_mark_ms=("ts_ms", "min"),
        last_mark_ms=("ts_ms", "max"),
        maximum_mark_interval_ms=("prior_ms", "max"),
    )
    open_ms = _epoch_ms(output.index)
    output["first_mark_boundary_delay_ms"] = output["first_mark_ms"] - open_ms
    output["end_mark_boundary_age_ms"] = open_ms + interval_ms - output["last_mark_ms"]
    output["maximum_mark_interval_ms"] = output["maximum_mark_interval_ms"].fillna(0.0)
    entry = _entry_mark_bars(values, midpoint_bars, interval_ms)
    return output.drop(columns=["first_mark_ms", "last_mark_ms"]).join(entry)


def _entry_mark_bars(
    values: pd.DataFrame,
    midpoint_bars: pd.DataFrame,
    interval_ms: int,
) -> pd.DataFrame:
    delays = midpoint_bars["first_boundary_delay_ms"].astype(float)
    threshold = pd.Series(_epoch_ms(delays.index), index=delays.index) + delays
    candidates = values.copy()
    candidates["entry_threshold_ms"] = candidates["bar_open"].map(threshold)
    candidates = candidates[
        candidates["entry_threshold_ms"].notna()
        & candidates["ts_ms"].ge(candidates["entry_threshold_ms"])
    ].copy()
    candidates["entry_prior_ms"] = candidates.groupby("bar_open")["ts_ms"].diff()
    grouped = candidates.groupby("bar_open", sort=True)
    output = grouped.agg(
        entry_mark_high=("mark_price", "max"),
        entry_mark_low=("mark_price", "min"),
        entry_mark_snapshot_count=("mark_price", "size"),
        entry_first_mark_ms=("ts_ms", "min"),
        entry_last_mark_ms=("ts_ms", "max"),
        entry_maximum_mark_interval_ms=("entry_prior_ms", "max"),
    )
    entry_threshold = threshold.reindex(output.index)
    open_ms = pd.Series(_epoch_ms(output.index), index=output.index)
    output["entry_first_mark_delay_ms"] = (
        output["entry_first_mark_ms"] - entry_threshold
    )
    output["entry_end_mark_age_ms"] = (
        open_ms + interval_ms - output["entry_last_mark_ms"]
    )
    output["entry_maximum_mark_interval_ms"] = output[
        "entry_maximum_mark_interval_ms"
    ].fillna(0.0)
    return output.drop(columns=["entry_first_mark_ms", "entry_last_mark_ms"])


def _epoch_ms(index: pd.Index) -> pd.Index:
    """Return UTC epoch milliseconds independent of pandas datetime unit."""
    values = pd.DatetimeIndex(index).as_unit("ns").asi8 // 1_000_000
    return pd.Index(values)


def _trade_bars(trades: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "trade_open",
                "trade_high",
                "trade_low",
                "trade_close",
                "trade_volume",
                "public_trade_count",
            ]
        ).rename_axis("bar_open")
    values = trades.sort_values(["ts_exchange_ms", "trade_id"], kind="stable").copy()
    values["timestamp"] = pd.to_datetime(values["ts_exchange_ms"], unit="ms", utc=True)
    values["bar_open"] = values["timestamp"].dt.floor(f"{bar_minutes}min")
    return values.groupby("bar_open", sort=True).agg(
        trade_open=("price", "first"),
        trade_high=("price", "max"),
        trade_low=("price", "min"),
        trade_close=("price", "last"),
        trade_volume=("size", "sum"),
        public_trade_count=("price", "size"),
    )


def _fill_path_fields(bars: pd.DataFrame, trade_bundle_complete: bool) -> None:
    for column in ("mark_high", "mark_low"):
        fallback = "high" if column == "mark_high" else "low"
        bars[column] = bars[column].fillna(bars[fallback]).astype(float)
    bars["mark_snapshot_count"] = bars["mark_snapshot_count"].fillna(0).astype(int)
    for column in (
        "first_mark_boundary_delay_ms",
        "end_mark_boundary_age_ms",
        "maximum_mark_interval_ms",
    ):
        bars[column] = bars[column].fillna(float("inf"))
    maximum_gap = bars[
        [
            "first_mark_boundary_delay_ms",
            "end_mark_boundary_age_ms",
            "maximum_mark_interval_ms",
        ]
    ].max(axis=1)
    bars["maximum_mark_interval_ms"] = maximum_gap
    bars["mark_path_complete"] = bars["mark_snapshot_count"].ge(2) & maximum_gap.le(
        _MAXIMUM_MARK_GAP_MS
    )
    bars["risk_high"] = bars["mark_high"]
    bars["risk_low"] = bars["mark_low"]
    _fill_entry_risk_fields(bars)
    bars["trade_bundle_complete"] = trade_bundle_complete
    bars["risk_path_source"] = _RISK_PATH_SOURCE
    bars["public_trade_count"] = bars["public_trade_count"].fillna(0).astype(int)


def _fill_entry_risk_fields(bars: pd.DataFrame) -> None:
    midpoint = (bars["entry_bid"].astype(float) + bars["entry_ask"].astype(float)) / 2
    bars["entry_mark_snapshot_count"] = (
        bars["entry_mark_snapshot_count"].fillna(0).astype(int)
    )
    diagnostic_columns = (
        "entry_first_mark_delay_ms",
        "entry_end_mark_age_ms",
        "entry_maximum_mark_interval_ms",
    )
    for column in diagnostic_columns:
        bars[column] = bars[column].fillna(float("inf"))
    maximum_gap = bars[list(diagnostic_columns)].max(axis=1)
    bars["entry_maximum_mark_interval_ms"] = maximum_gap
    bars["entry_mark_path_complete"] = bars["entry_mark_snapshot_count"].ge(
        1
    ) & maximum_gap.le(_MAXIMUM_MARK_GAP_MS)
    bars["risk_entry_high"] = bars["entry_mark_high"].fillna(midpoint).astype(float)
    bars["risk_entry_low"] = bars["entry_mark_low"].fillna(midpoint).astype(float)


def _fill_signal_ohlc_fields(bars: pd.DataFrame) -> None:
    """Use public-trade OHLC, explicitly carrying only genuine no-trade bars."""
    observed = bars["public_trade_count"].gt(0)
    if not bool(observed.iloc[0]):
        raise ValueError("HIP-3 signal OHLC cannot backfill a leading zero-trade bar")
    prior_trade_close = bars["trade_close"].ffill()
    for name in ("open", "high", "low", "close"):
        source = bars[f"trade_{name}"]
        bars[f"signal_{name}"] = source.where(observed, prior_trade_close).astype(float)
    bars["signal_volume"] = bars["trade_volume"].fillna(0.0).astype(float)
    bars["signal_ohlc_synthetic_no_trade"] = ~observed
    recovery = (~observed).shift(1, fill_value=False) & observed
    signal_gap = bars["gap_before_bars"].astype(int).copy()
    signal_gap.loc[(~observed) | recovery] = signal_gap.loc[
        (~observed) | recovery
    ].clip(lower=1)
    bars["signal_gap_before_bars"] = signal_gap
    bars["signal_ohlc_source"] = "0xarchive_public_trade_ohlc_v1"


def _validate_request(
    midpoint: Hip3MidpointBars,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
    bar_minutes: int,
    trade_bundle_complete: bool,
) -> None:
    validate_market_symbol(midpoint.symbol, "hip3")
    if bar_minutes not in {5, 15}:
        raise ValueError("HIP-3 venue-path bars require 5m or 15m")
    if not isinstance(trade_bundle_complete, bool):
        raise ValueError("trade_bundle_complete must be boolean")
    missing_midpoint = {
        "entry_bid",
        "entry_ask",
        "first_boundary_delay_ms",
    }.difference(midpoint.bars.columns)
    missing_prices = {"ts_ms", "mark_price"}.difference(prices.columns)
    missing_trades = {"trade_id", "ts_exchange_ms", "price", "size"}.difference(
        trades.columns
    )
    if missing_midpoint or missing_prices or missing_trades:
        raise ValueError("HIP-3 venue-path source columns are incomplete")
    raw_marks = prices["mark_price"]
    marks = pd.to_numeric(raw_marks, errors="coerce")
    if (
        (raw_marks.notna() & marks.isna()).any()
        or (~marks.dropna().map(isfinite)).any()
        or marks.dropna().le(0.0).any()
    ):
        raise ValueError("HIP-3 mark prices must be positive when present")
    for column in ("price", "size"):
        values = pd.to_numeric(trades[column], errors="raise").astype(float)
        if not values.map(isfinite).all() or values.le(0.0).any():
            raise ValueError(f"HIP-3 public-trade {column} must be finite and positive")
    identifiers = trades["trade_id"]
    if identifiers.isna().any() or identifiers.astype(str).str.strip().eq("").any():
        raise ValueError("HIP-3 public trades require non-empty trade_id values")
    if identifiers.astype(str).duplicated().any():
        raise ValueError("HIP-3 public trade_id values must be unique")
