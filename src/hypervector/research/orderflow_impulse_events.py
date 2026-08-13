"""Causal feature and fixed-arm event construction for 1m order flow."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.orderflow_impulse_contract import OrderFlowImpulseConfig


MODEL_FEATURE_NAMES: tuple[str, ...] = (
    "body_return_bps",
    "absolute_body_return_bps",
    "return_threshold_bps",
    "trade_volume",
    "volume_threshold",
    "trade_flow_imbalance",
    "imbalance_5_last",
    "imbalance_5_delta",
    "micro_price_delta_bps",
    "spread_bps_last",
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
        "imbalance_5_delta",
        "micro_price_delta_bps",
        "spread_bps_last",
        "bid_depth_10_last",
        "ask_depth_10_last",
    }
)


def build_orderflow_feature_rows(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    books: pd.DataFrame,
    config: OrderFlowImpulseConfig,
) -> pd.DataFrame:
    """Build append-invariant completed-minute features and causal thresholds."""
    _validate_frame(bars, _BAR_COLUMNS, "bars")
    _validate_frame(trades, _TRADE_COLUMNS, "trades")
    _validate_frame(books, _BOOK_COLUMNS, "books", allow_empty=True)
    _validate_trade_alignment(bars, trades)
    rows = bars.copy().merge(trades, on="bar_open_at", validate="one_to_one")
    rows = rows.merge(books, on="bar_open_at", how="left", validate="one_to_one")
    _validate_book_timing(rows)
    rows = _attach_features(rows, config)
    complete = rows["return_threshold_bps"].notna() & rows["volume_threshold"].notna()
    if not complete.any():
        raise ValueError("order-flow inputs do not cover the configured warmup")
    return rows.loc[complete].reset_index(drop=True)


def build_orderflow_event_arms(
    features: pd.DataFrame,
    *,
    symbol: str,
    config: OrderFlowImpulseConfig | None = None,
) -> pd.DataFrame:
    """Emit every fixed continuation and reversion arm for each base event."""
    resolved = config or OrderFlowImpulseConfig()
    missing = sorted(set(MODEL_FEATURE_NAMES).difference(features.columns))
    if missing:
        raise ValueError(f"order-flow features missing columns: {missing}")
    normalized = symbol.strip().upper()
    if normalized not in resolved.symbols:
        raise ValueError(f"unsupported order-flow impulse symbol: {normalized}")
    events = features.loc[_base_event_mask(features)].copy()
    records: list[dict[str, object]] = []
    for row in events.itertuples(index=False):
        records.extend(_event_records(row, normalized, resolved))
    return pd.DataFrame(records, columns=_event_columns())


def _attach_features(
    rows: pd.DataFrame, config: OrderFlowImpulseConfig
) -> pd.DataFrame:
    output = rows.copy()
    output["available_at_utc"] = output["bar_open_at"] + pd.Timedelta(minutes=1)
    output["body_return_bps"] = (output["close"] / output["open"] - 1.0) * 10_000.0
    output["absolute_body_return_bps"] = output["body_return_bps"].abs()
    output["trade_volume"] = output["buy_volume"] + output["sell_volume"]
    output["trade_flow_imbalance"] = _imbalance(
        output["buy_volume"], output["sell_volume"]
    )
    times = pd.DatetimeIndex(output["bar_open_at"])
    output["segment_id"] = (
        times.to_series(index=output.index).diff().ne(pd.Timedelta(minutes=1)).cumsum()
    )
    output["return_threshold_bps"] = _segmented_quantile(
        output,
        "absolute_body_return_bps",
        config.warmup_minutes,
        config.return_quantile,
    )
    output["volume_threshold"] = _segmented_quantile(
        output,
        "trade_volume",
        config.warmup_minutes,
        config.volume_quantile,
    )
    depth = output["bid_depth_10_last"] + output["ask_depth_10_last"]
    output["log_depth_10"] = np.log1p(depth)
    return output


def _segmented_quantile(
    rows: pd.DataFrame, name: str, window: int, quantile: float
) -> pd.Series:
    return rows.groupby("segment_id", sort=False)[name].transform(
        lambda values: values.shift(1)
        .rolling(window, min_periods=window)
        .quantile(quantile)
    )


def _base_event_mask(features: pd.DataFrame) -> pd.Series:
    direction = np.sign(features["body_return_bps"])
    aligned_flow = direction * features["trade_flow_imbalance"] > 0.0
    return (
        features["return_threshold_bps"].notna()
        & features["volume_threshold"].notna()
        & features["absolute_body_return_bps"].ge(features["return_threshold_bps"])
        & features["trade_volume"].ge(features["volume_threshold"])
        & aligned_flow
    )


def _event_records(
    row: object, symbol: str, config: OrderFlowImpulseConfig
) -> list[dict[str, object]]:
    move_sign = 1 if float(getattr(row, "body_return_bps")) > 0.0 else -1
    relations = _l2_relations(row, move_sign)
    available = all(math.isfinite(value) for value in relations)
    aligned = sum(value > 0.0 for value in relations)
    opposed = sum(value < 0.0 for value in relations)
    choices: list[tuple[str, int]] = [
        ("continuation_all", move_sign),
        ("reversion_all", -move_sign),
    ]
    if available and aligned >= config.l2_votes_required:
        choices.append(("continuation_l2_aligned", move_sign))
    if available and opposed >= config.l2_votes_required:
        choices.append(("reversion_l2_opposed", -move_sign))
    return [
        _record(row, symbol, arm, side_sign, aligned, opposed)
        for arm, side_sign in choices
    ]


def _l2_relations(row: object, move_sign: int) -> tuple[float, float, float]:
    return tuple(
        move_sign * float(getattr(row, name))
        for name in (
            "imbalance_5_last",
            "micro_price_delta_bps",
            "imbalance_5_delta",
        )
    )


def _record(
    row: object,
    symbol: str,
    arm: str,
    side_sign: int,
    aligned_votes: int,
    opposed_votes: int,
) -> dict[str, object]:
    bar_open = pd.Timestamp(getattr(row, "bar_open_at"))
    record = {
        "event_id": f"{symbol}:{bar_open.isoformat()}",
        "symbol": symbol,
        "bar_open_at": bar_open,
        "available_at_utc": pd.Timestamp(getattr(row, "available_at_utc")),
        "arm": arm,
        "side": "long" if side_sign > 0 else "short",
        "l2_aligned_votes": aligned_votes,
        "l2_opposed_votes": opposed_votes,
    }
    record.update({name: float(getattr(row, name)) for name in MODEL_FEATURE_NAMES})
    return record


def _validate_frame(
    frame: pd.DataFrame,
    required: frozenset[str],
    name: str,
    *,
    allow_empty: bool = False,
) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"order-flow {name} missing columns: {missing}")
    if frame.empty:
        if allow_empty:
            return
        raise ValueError(f"order-flow {name} must be non-empty")
    times = pd.DatetimeIndex(frame["bar_open_at"])
    if times.tz is None or times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError(f"order-flow {name} timestamps must be ordered unique UTC")


def _validate_trade_alignment(bars: pd.DataFrame, trades: pd.DataFrame) -> None:
    if not pd.DatetimeIndex(bars["bar_open_at"]).equals(
        pd.DatetimeIndex(trades["bar_open_at"])
    ):
        raise ValueError("order-flow trade bars must align with price bars")


def _validate_book_timing(rows: pd.DataFrame) -> None:
    present = rows.loc[rows["last_book_at"].notna()]
    observed = pd.DatetimeIndex(present["last_book_at"])
    if not observed.empty and observed.tz is None:
        raise ValueError("order-flow book timestamps must be timezone-aware")
    decision = pd.DatetimeIndex(present["bar_open_at"]) + pd.Timedelta(minutes=1)
    if (observed > decision).any():
        raise ValueError("future book observation would leak into decision")


def _imbalance(buy: pd.Series, sell: pd.Series) -> pd.Series:
    total = buy.astype(float) + sell.astype(float)
    return (buy.astype(float) - sell.astype(float)) / total.replace(0.0, np.nan)


def _event_columns() -> list[str]:
    return [
        "event_id",
        "symbol",
        "bar_open_at",
        "available_at_utc",
        "arm",
        "side",
        "l2_aligned_votes",
        "l2_opposed_votes",
        *MODEL_FEATURE_NAMES,
    ]
