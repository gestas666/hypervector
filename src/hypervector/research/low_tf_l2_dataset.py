"""Causal five-minute price, trade-flow, and L2 feature assembly."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEATURE_NAMES: tuple[str, ...] = (
    "return_1_bps",
    "return_3_bps",
    "return_12_bps",
    "realized_vol_12_bps",
    "range_bps",
    "volume_z_36",
    "trade_flow_imbalance",
    "trade_count_z_36",
    "imbalance_5_last",
    "imbalance_5_mean_60s",
    "imbalance_5_delta_60s",
    "imbalance_10_last",
    "spread_bps_last",
    "micro_price_delta_bps",
    "log_depth_10",
)
_BAR_COLUMNS = frozenset(
    {"bar_open_at", "open", "high", "low", "close", "volume", "trade_count"}
)
_TRADE_COLUMNS = frozenset({"bar_open_at", "buy_volume", "sell_volume"})
_BOOK_COLUMNS = frozenset(
    {
        "bar_open_at",
        "last_book_at",
        "imbalance_5_last",
        "imbalance_5_mean_60s",
        "imbalance_5_delta_60s",
        "imbalance_10_last",
        "spread_bps_last",
        "micro_price_delta_bps",
        "bid_depth_10_last",
        "ask_depth_10_last",
    }
)
_BOOK_VALUE_COLUMNS = tuple(sorted(_BOOK_COLUMNS.difference({"bar_open_at"})))


@dataclass(frozen=True)
class LowTimeframeDatasetConfig:
    """Frozen timing and warmup contract for one symbol's feature rows."""

    symbol: str
    bar_minutes: int = 5
    history_bars: int = 36
    volatility_bars: int = 12

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("dataset symbol must be non-empty")
        if self.bar_minutes != 5:
            raise ValueError("low-timeframe dataset requires five-minute bars")
        if self.history_bars < 36:
            raise ValueError("dataset history must include at least 36 bars")
        if self.volatility_bars != 12:
            raise ValueError("dataset volatility window must equal 12 bars")


@dataclass(frozen=True)
class LowTimeframeDataset:
    """Validated point-in-time feature rows and their stable column identity."""

    rows: pd.DataFrame
    feature_names: tuple[str, ...] = FEATURE_NAMES
    excluded_book_bars: int = 0

    def __post_init__(self) -> None:
        if self.rows.empty:
            raise ValueError("low-timeframe dataset rows must be non-empty")
        if self.excluded_book_bars < 0:
            raise ValueError("excluded book bar count cannot be negative")


def build_low_timeframe_dataset(
    bars: pd.DataFrame,
    trade_features: pd.DataFrame,
    book_features: pd.DataFrame,
    config: LowTimeframeDatasetConfig,
) -> LowTimeframeDataset:
    """Build completed-bar features from preaggregated causal venue inputs."""
    _validate_frame(bars, _BAR_COLUMNS, "bars")
    _validate_frame(trade_features, _TRADE_COLUMNS, "trades")
    _validate_frame(book_features, _BOOK_COLUMNS, "books")
    _validate_alignment(bars, trade_features, book_features)
    if len(bars) <= config.history_bars:
        raise ValueError("dataset has insufficient feature history")
    rows = bars.copy()
    rows["available_at_utc"] = rows["bar_open_at"] + pd.Timedelta(
        minutes=config.bar_minutes
    )
    rows = rows.merge(trade_features, on="bar_open_at", validate="one_to_one")
    rows = rows.merge(
        book_features,
        on="bar_open_at",
        how="left",
        validate="one_to_one",
    )
    _validate_book_timing(rows)
    rows = _add_features(rows, config)
    rows.insert(0, "symbol", config.symbol.strip().upper())
    rows = rows.iloc[config.history_bars :].reset_index(drop=True)
    book_complete = rows.loc[:, _BOOK_VALUE_COLUMNS].notna().all(axis=1)
    excluded_book_bars = int((~book_complete).sum())
    rows = rows.loc[book_complete].reset_index(drop=True)
    _validate_output(rows)
    return LowTimeframeDataset(
        rows=rows,
        excluded_book_bars=excluded_book_bars,
    )


def _validate_frame(
    frame: pd.DataFrame,
    required: frozenset[str],
    label: str,
) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{label} missing columns: {missing}")
    if frame.empty:
        raise ValueError(f"{label} must be non-empty")
    times = pd.DatetimeIndex(frame["bar_open_at"])
    if times.tz is None:
        raise ValueError(f"{label} timestamps must be timezone-aware")
    if not times.is_monotonic_increasing:
        raise ValueError(f"{label} timestamps must be ordered")
    if times.has_duplicates:
        raise ValueError(f"{label} contains duplicate bar identity")


def _validate_alignment(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    books: pd.DataFrame,
) -> None:
    expected = pd.DatetimeIndex(bars["bar_open_at"])
    observed_trades = pd.DatetimeIndex(trades["bar_open_at"])
    if not expected.equals(observed_trades):
        raise ValueError("trades bar identities do not align with bars")
    observed_books = pd.DatetimeIndex(books["bar_open_at"])
    unknown_books = observed_books.difference(expected)
    if not unknown_books.empty:
        raise ValueError("books contain identities outside the price bars")


def _validate_book_timing(rows: pd.DataFrame) -> None:
    present = rows.loc[rows["last_book_at"].notna()]
    observed = pd.DatetimeIndex(present["last_book_at"])
    if not observed.empty and observed.tz is None:
        raise ValueError("book timestamps must be timezone-aware")
    available = pd.DatetimeIndex(present["available_at_utc"])
    if (observed > available).any():
        raise ValueError("future book observation would leak into decision")


def _add_features(
    rows: pd.DataFrame,
    config: LowTimeframeDatasetConfig,
) -> pd.DataFrame:
    output = rows.copy()
    close = output["close"].astype(float)
    one_bar = close.pct_change() * 10_000.0
    output["return_1_bps"] = one_bar
    output["return_3_bps"] = close.pct_change(3) * 10_000.0
    output["return_12_bps"] = close.pct_change(12) * 10_000.0
    output["realized_vol_12_bps"] = one_bar.rolling(config.volatility_bars).std(ddof=0)
    output["range_bps"] = (output["high"] - output["low"]) / output["open"] * 10_000.0
    output["volume_z_36"] = _zscore(output["volume"], config.history_bars)
    total_flow = output["buy_volume"] + output["sell_volume"]
    output["trade_flow_imbalance"] = (
        output["buy_volume"] - output["sell_volume"]
    ) / total_flow
    output["trade_count_z_36"] = _zscore(output["trade_count"], config.history_bars)
    depth = output["bid_depth_10_last"] + output["ask_depth_10_last"]
    output["log_depth_10"] = np.log1p(depth)
    return output


def _zscore(values: pd.Series, window: int) -> pd.Series:
    numeric = values.astype(float)
    mean = numeric.rolling(window).mean()
    deviation = numeric.rolling(window).std(ddof=0)
    return (numeric - mean) / deviation.replace(0.0, np.nan)


def _validate_output(rows: pd.DataFrame) -> None:
    values = rows.loc[:, FEATURE_NAMES].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("dataset features contain missing or non-finite values")
