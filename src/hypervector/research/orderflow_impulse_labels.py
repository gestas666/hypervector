"""Pessimistic one-minute lifecycle labels for order-flow impulse arms."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.orderflow_impulse_contract import OrderFlowImpulseConfig


_EVENT_COLUMNS = frozenset(
    {"event_id", "symbol", "bar_open_at", "available_at_utc", "arm", "side"}
)
_BAR_COLUMNS = frozenset({"bar_open_at", "open", "high", "low", "close"})


def label_orderflow_arms(
    bars: pd.DataFrame,
    events: pd.DataFrame,
    funding: pd.DataFrame,
    config: OrderFlowImpulseConfig,
) -> pd.DataFrame:
    """Label every fixed arm with next-bar entry and adverse barrier ordering."""
    market = _validated_bars(bars)
    ordered = _validated_events(events, config)
    funding_rates = _validated_funding(funding)
    records = [
        _label_event(market, row, funding_rates, config)
        for _, row in ordered.iterrows()
    ]
    return pd.DataFrame(records)


def serialize_orderflow_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Apply one-position-per-symbol independently to every research arm."""
    required = {"arm", "symbol", "entry_time_utc", "outcome_time_utc", "status"}
    missing = sorted(required.difference(outcomes.columns))
    if missing:
        raise ValueError(f"order-flow outcomes missing columns: {missing}")
    output = outcomes.copy().sort_values(
        ["arm", "symbol", "entry_time_utc", "event_id"]
    )
    output["accepted"] = False
    output["displacement_reason"] = None
    occupied: dict[tuple[str, str], pd.Timestamp] = {}
    for index, row in output.iterrows():
        key = (str(row["arm"]), str(row["symbol"]))
        entry = pd.Timestamp(row["entry_time_utc"])
        if entry < occupied.get(key, pd.Timestamp.min.tz_localize("UTC")):
            output.at[index, "displacement_reason"] = "symbol_position_open"
            continue
        output.at[index, "accepted"] = str(row["status"]) != "truncated"
        if bool(output.at[index, "accepted"]):
            occupied[key] = pd.Timestamp(row["outcome_time_utc"])
    return output.sort_values(["bar_open_at", "arm", "symbol"]).reset_index(drop=True)


def _label_event(
    market: pd.DataFrame,
    row: pd.Series,
    funding: pd.Series,
    config: OrderFlowImpulseConfig,
) -> dict[str, object]:
    entry_time = pd.Timestamp(row["available_at_utc"])
    base = row.to_dict()
    if entry_time not in market.index:
        return _truncated(base, entry_time)
    side = str(row["side"])
    raw_entry = float(market.loc[entry_time, "open"])
    entry = _adverse_price(raw_entry, side, config, entering=True)
    target, stop = _barriers(entry, side, config)
    resolved = _walk_path(market, entry_time, side, entry, target, stop, config)
    if resolved is None:
        return _truncated(base, entry_time)
    status, outcome_time, raw_exit = resolved
    exit_price = _adverse_price(raw_exit, side, config, entering=False)
    gross = _signed_return_bps(side, entry, exit_price)
    funding_bps = _funding_bps(side, funding, entry_time, outcome_time)
    fee_bps = 2.0 * config.fee_bps_per_side
    nominal = gross - fee_bps + funding_bps
    return {
        **base,
        "entry_time_utc": entry_time,
        "outcome_time_utc": outcome_time,
        "entry_price": entry,
        "exit_price": exit_price,
        "target_price": target,
        "stop_price": stop,
        "status": status,
        "gross_return_bps": gross,
        "fee_bps": fee_bps,
        "funding_bps": funding_bps,
        "net_return_bps_nominal": nominal,
        "net_return_bps_stress": nominal - config.stress_haircut_bps,
    }


def _walk_path(
    market: pd.DataFrame,
    entry_time: pd.Timestamp,
    side: str,
    entry: float,
    target: float,
    stop: float,
    config: OrderFlowImpulseConfig,
) -> tuple[str, pd.Timestamp, float] | None:
    expected = entry_time
    for offset in range(config.maximum_hold_minutes):
        timestamp = entry_time + pd.Timedelta(minutes=offset)
        if timestamp not in market.index or timestamp != expected:
            return None
        row = market.loc[timestamp]
        target_hit, stop_hit = _touches(row, side, target, stop)
        outcome_time = timestamp + pd.Timedelta(minutes=1)
        if target_hit and stop_hit:
            return "ambiguous_stop_first", outcome_time, stop
        if stop_hit:
            return "stop", outcome_time, stop
        if target_hit:
            return "target", outcome_time, target
        expected += pd.Timedelta(minutes=1)
    final_time = entry_time + pd.Timedelta(minutes=config.maximum_hold_minutes - 1)
    return (
        "timeout",
        final_time + pd.Timedelta(minutes=1),
        float(market.loc[final_time, "close"]),
    )


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_BAR_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"order-flow label bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if bars.empty or times.tz is None or times.has_duplicates:
        raise ValueError("order-flow label bars require unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("order-flow label bars must be ordered")
    values = bars[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("order-flow label prices must be finite and positive")
    return bars.set_index("bar_open_at")


def _validated_events(
    events: pd.DataFrame, config: OrderFlowImpulseConfig
) -> pd.DataFrame:
    missing = sorted(_EVENT_COLUMNS.difference(events.columns))
    if missing:
        raise ValueError(f"order-flow events missing columns: {missing}")
    if events.empty:
        raise ValueError("order-flow events must be non-empty")
    output = events.copy()
    output["available_at_utc"] = pd.to_datetime(output["available_at_utc"], utc=True)
    output["bar_open_at"] = pd.to_datetime(output["bar_open_at"], utc=True)
    if not output["side"].isin(("long", "short")).all():
        raise ValueError("order-flow event side must be long or short")
    if not output["symbol"].isin(config.symbols).all():
        raise ValueError("order-flow event contains unsupported symbol")
    return output.sort_values(["available_at_utc", "arm", "symbol"])


def _validated_funding(funding: pd.DataFrame) -> pd.Series:
    required = {"timestamp", "funding_rate"}
    missing = sorted(required.difference(funding.columns))
    if missing:
        raise ValueError(f"order-flow funding missing columns: {missing}")
    if funding.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    times = pd.DatetimeIndex(pd.to_datetime(funding["timestamp"], utc=True))
    rates = funding["funding_rate"].astype(float).to_numpy()
    if times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError("order-flow funding timestamps must be ordered and unique")
    if not np.isfinite(rates).all():
        raise ValueError("order-flow funding rates must be finite")
    return pd.Series(rates, index=times)


def _funding_bps(
    side: str,
    funding: pd.Series,
    entry_time: pd.Timestamp,
    outcome_time: pd.Timestamp,
) -> float:
    selected = funding.loc[
        (funding.index >= entry_time) & (funding.index < outcome_time)
    ]
    sign = 1.0 if side == "long" else -1.0
    return float(-sign * selected.sum() * 10_000.0)


def _barriers(
    entry: float, side: str, config: OrderFlowImpulseConfig
) -> tuple[float, float]:
    sign = 1.0 if side == "long" else -1.0
    target = entry * (1.0 + sign * config.target_bps / 10_000.0)
    stop = entry * (1.0 - sign * config.stop_bps / 10_000.0)
    return target, stop


def _touches(
    row: pd.Series, side: str, target: float, stop: float
) -> tuple[bool, bool]:
    if side == "long":
        return float(row["high"]) >= target, float(row["low"]) <= stop
    return float(row["low"]) <= target, float(row["high"]) >= stop


def _adverse_price(
    raw: float,
    side: str,
    config: OrderFlowImpulseConfig,
    *,
    entering: bool,
) -> float:
    direction = 1.0 if side == "long" else -1.0
    operation = direction if entering else -direction
    return raw * (1.0 + operation * config.slippage_bps_per_side / 10_000.0)


def _signed_return_bps(side: str, entry: float, exit_price: float) -> float:
    sign = 1.0 if side == "long" else -1.0
    return sign * (exit_price / entry - 1.0) * 10_000.0


def _truncated(base: dict[str, object], entry_time: pd.Timestamp) -> dict[str, object]:
    return {
        **base,
        "entry_time_utc": entry_time,
        "outcome_time_utc": entry_time,
        "entry_price": math.nan,
        "exit_price": math.nan,
        "target_price": math.nan,
        "stop_price": math.nan,
        "status": "truncated",
        "gross_return_bps": math.nan,
        "fee_bps": math.nan,
        "funding_bps": math.nan,
        "net_return_bps_nominal": math.nan,
        "net_return_bps_stress": math.nan,
    }
