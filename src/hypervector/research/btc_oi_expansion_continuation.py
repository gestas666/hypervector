"""Receipt-causal count-only BTC OI-expansion continuation measurements."""

from __future__ import annotations

import math
from typing import Final

import numpy as np
import pandas as pd


_MINUTE: Final = pd.Timedelta(minutes=1)
_SUPPORTED_QUANTILES: Final = frozenset({0.75, 0.8, 0.9})
_REQUIRED_COLUMNS: Final = frozenset(
    {
        "minute",
        "close",
        "trade_imbalance",
        "book_imbalance",
        "open_interest",
        "first_bid",
        "first_ask",
        "first_quote_at",
    }
)
_NUMERIC_COLUMNS: Final = (
    "close",
    "trade_imbalance",
    "book_imbalance",
    "open_interest",
    "first_bid",
    "first_ask",
)
_ARMS: Final = (
    "positive_price_shock",
    "positive_price_and_oi_expansion",
    "positive_price_oi_and_trade_flow",
    "full_price_oi_trade_and_book_candidate",
)
_OUTPUT_COLUMNS: Final = (
    "decision_at",
    "segment_id",
    "quantile",
    "arm",
    "qualifies",
    "onset",
    "shock_bps",
    "oi_change_pct",
    "price_threshold_bps",
    "oi_threshold_pct",
    "terminal_trade_imbalance",
    "terminal_book_imbalance",
)


def build_oi_expansion_preflight(
    minutes: pd.DataFrame,
    *,
    quantile: float,
    minimum_shock_bps: float = 13.0,
    minimum_oi_expansion_pct: float = 0.0005,
    warmup_bars: int = 288,
    non_overlap_minutes: int = 60,
) -> pd.DataFrame:
    """Return receipt-causal count-only BTC continuation attribution rows."""
    _validate_parameters(
        quantile,
        minimum_shock_bps,
        minimum_oi_expansion_pct,
        warmup_bars,
        non_overlap_minutes,
    )
    rows = _validated_minutes(minutes)
    bars = _completed_five_minute_bars(rows)
    featured = _attach_prior_thresholds(bars, quantile, warmup_bars)
    attributed = _attribute_arms(
        featured,
        quantile,
        minimum_shock_bps,
        minimum_oi_expansion_pct,
    )
    return _attach_non_overlapping_onsets(attributed, non_overlap_minutes)


def _validate_parameters(
    quantile: float,
    minimum_shock_bps: float,
    minimum_oi_expansion_pct: float,
    warmup_bars: int,
    non_overlap_minutes: int,
) -> None:
    if isinstance(quantile, bool) or float(quantile) not in _SUPPORTED_QUANTILES:
        raise ValueError(f"unsupported quantile: {quantile}")
    for name, value in (
        ("minimum shock", minimum_shock_bps),
        ("minimum OI expansion", minimum_oi_expansion_pct),
    ):
        if not math.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"{name} must be finite and positive")
    for name, value in (
        ("warmup bars", warmup_bars),
        ("non-overlap", non_overlap_minutes),
    ):
        if isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")


def _validated_minutes(minutes: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(minutes.columns))
    if missing:
        raise ValueError(f"BTC OI-expansion minutes missing columns: {missing}")
    if minutes.empty:
        raise ValueError("BTC OI-expansion minutes must be non-empty")
    rows = minutes.loc[:, sorted(_REQUIRED_COLUMNS)].copy()
    minute_index = _aware_utc_index(rows["minute"], "minute")
    quote_index = _aware_utc_index(rows["first_quote_at"], "first_quote_at")
    if minute_index.has_duplicates or not minute_index.is_monotonic_increasing:
        raise ValueError("BTC OI-expansion minutes require ordered unique timestamps")
    rows["minute"] = minute_index
    rows["first_quote_at"] = quote_index
    _validate_numeric(rows)
    _validate_quotes(rows)
    return rows.reset_index(drop=True)


def _aware_utc_index(values: pd.Series, label: str) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(values)
    if index.tz is None or any(value.utcoffset() != pd.Timedelta(0) for value in index):
        raise ValueError(f"BTC OI-expansion {label} must be timezone-aware UTC")
    return index.tz_convert("UTC")


def _validate_numeric(rows: pd.DataFrame) -> None:
    numeric = rows.loc[:, _NUMERIC_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("BTC OI-expansion source features must be finite")
    rows.loc[:, _NUMERIC_COLUMNS] = numeric.astype(float)
    positive = rows.loc[:, ["close", "open_interest", "first_bid", "first_ask"]]
    if (positive.to_numpy(dtype=float) <= 0.0).any():
        raise ValueError("BTC OI-expansion prices and open interest must be positive")
    imbalances = rows.loc[:, ["trade_imbalance", "book_imbalance"]]
    if (imbalances.abs() > 1.0).any().any():
        raise ValueError("BTC OI-expansion imbalances must be between -1 and 1")


def _validate_quotes(rows: pd.DataFrame) -> None:
    if (rows["first_bid"].astype(float) >= rows["first_ask"].astype(float)).any():
        raise ValueError("BTC OI-expansion source book must not be crossed")
    minute = pd.DatetimeIndex(rows["minute"])
    quote = pd.DatetimeIndex(rows["first_quote_at"])
    if (quote < minute).any() or (quote >= minute + _MINUTE).any():
        raise ValueError(
            "BTC OI-expansion first quote must belong to its receipt minute"
        )


def _completed_five_minute_bars(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    frame["segment_id"] = frame["minute"].diff().ne(_MINUTE).cumsum().astype(int)
    frame["bar_open"] = frame["minute"].dt.floor("5min")
    records: list[dict[str, object]] = []
    for (segment, bar_open), group in frame.groupby(
        ["segment_id", "bar_open"], sort=False
    ):
        if not _is_complete_group(group, pd.Timestamp(bar_open)):
            continue
        terminal = group.iloc[-1]
        records.append(_bar_record(int(segment), pd.Timestamp(bar_open), terminal))
    return pd.DataFrame.from_records(records, columns=_bar_columns())


def _is_complete_group(group: pd.DataFrame, bar_open: pd.Timestamp) -> bool:
    expected = pd.date_range(bar_open, periods=5, freq="1min")
    return len(group) == 5 and pd.DatetimeIndex(group["minute"]).equals(expected)


def _bar_record(
    segment: int, bar_open: pd.Timestamp, terminal: pd.Series
) -> dict[str, object]:
    return {
        "decision_at": bar_open + pd.Timedelta(minutes=5),
        "segment_id": segment,
        "close": float(terminal["close"]),
        "open_interest": float(terminal["open_interest"]),
        "terminal_trade_imbalance": float(terminal["trade_imbalance"]),
        "terminal_book_imbalance": float(terminal["book_imbalance"]),
    }


def _bar_columns() -> list[str]:
    return [
        "decision_at",
        "segment_id",
        "close",
        "open_interest",
        "terminal_trade_imbalance",
        "terminal_book_imbalance",
    ]


def _attach_prior_thresholds(
    bars: pd.DataFrame, quantile: float, warmup_bars: int
) -> pd.DataFrame:
    if bars.empty:
        return bars.assign(
            shock_bps=pd.Series(dtype=float),
            oi_change_pct=pd.Series(dtype=float),
            price_threshold_bps=pd.Series(dtype=float),
            oi_threshold_pct=pd.Series(dtype=float),
        )
    output = bars.copy()
    grouped = output.groupby("segment_id", sort=False)
    output["shock_bps"] = grouped["close"].pct_change() * 10_000.0
    output["oi_change_pct"] = grouped["open_interest"].pct_change()
    output["price_threshold_bps"] = _prior_quantile(
        output, "shock_bps", warmup_bars, quantile, absolute=True
    )
    output["oi_threshold_pct"] = _prior_quantile(
        output, "oi_change_pct", warmup_bars, quantile, absolute=False
    )
    return output


def _prior_quantile(
    rows: pd.DataFrame,
    column: str,
    window: int,
    quantile: float,
    *,
    absolute: bool,
) -> pd.Series:
    values = rows[column].abs() if absolute else rows[column]
    return values.groupby(rows["segment_id"], sort=False).transform(
        lambda group: group.shift(1)
        .rolling(window, min_periods=window)
        .quantile(quantile)
    )


def _attribute_arms(
    rows: pd.DataFrame,
    quantile: float,
    minimum_shock_bps: float,
    minimum_oi_expansion_pct: float,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in rows.itertuples(index=False):
        flags = _arm_flags(row, minimum_shock_bps, minimum_oi_expansion_pct)
        for arm, qualifies in zip(_ARMS, flags, strict=True):
            records.append(_attribution_record(row, quantile, arm, qualifies))
    return pd.DataFrame.from_records(records, columns=_OUTPUT_COLUMNS)


def _arm_flags(
    row: object,
    minimum_shock_bps: float,
    minimum_oi_expansion_pct: float,
) -> tuple[bool, bool, bool, bool]:
    shock = float(getattr(row, "shock_bps"))
    oi_change = float(getattr(row, "oi_change_pct"))
    price_threshold = float(getattr(row, "price_threshold_bps"))
    oi_threshold = float(getattr(row, "oi_threshold_pct"))
    price = math.isfinite(price_threshold) and shock >= max(
        minimum_shock_bps, price_threshold
    )
    price_oi = (
        price
        and math.isfinite(oi_threshold)
        and oi_change >= max(minimum_oi_expansion_pct, oi_threshold)
    )
    flow = price_oi and float(getattr(row, "terminal_trade_imbalance")) > 0.0
    full = flow and float(getattr(row, "terminal_book_imbalance")) > 0.0
    return price, price_oi, flow, full


def _attribution_record(
    row: object, quantile: float, arm: str, qualifies: bool
) -> dict[str, object]:
    return {
        "decision_at": pd.Timestamp(getattr(row, "decision_at")),
        "segment_id": int(getattr(row, "segment_id")),
        "quantile": float(quantile),
        "arm": arm,
        "qualifies": qualifies,
        "onset": False,
        "shock_bps": float(getattr(row, "shock_bps")),
        "oi_change_pct": float(getattr(row, "oi_change_pct")),
        "price_threshold_bps": float(getattr(row, "price_threshold_bps")),
        "oi_threshold_pct": float(getattr(row, "oi_threshold_pct")),
        "terminal_trade_imbalance": float(getattr(row, "terminal_trade_imbalance")),
        "terminal_book_imbalance": float(getattr(row, "terminal_book_imbalance")),
    }


def _attach_non_overlapping_onsets(
    rows: pd.DataFrame, non_overlap_minutes: int
) -> pd.DataFrame:
    if rows.empty:
        return rows
    output = rows.copy()
    for _, group in output.groupby(["segment_id", "arm"], sort=False):
        unavailable_until: pd.Timestamp | None = None
        for index in group.index[group["qualifies"]]:
            decision = pd.Timestamp(output.at[index, "decision_at"])
            if unavailable_until is not None and decision <= unavailable_until:
                continue
            output.at[index, "onset"] = True
            unavailable_until = decision + pd.Timedelta(minutes=non_overlap_minutes)
    output["qualifies"] = output["qualifies"].astype(bool)
    output["onset"] = output["onset"].astype(bool)
    return output.reset_index(drop=True)
