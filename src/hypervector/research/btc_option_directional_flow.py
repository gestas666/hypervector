"""Causal primitives for the frozen BTC option directional-flow candidate."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from hypervector.research.deribit_option_trade_acquisition import (
    DAY_MS,
    OptionInstrument,
    OptionTrade,
)


_DAYS_PER_YEAR = 365.0
_MINIMUM_EXPIRY_DAYS = 1.0
_MAXIMUM_EXPIRY_DAYS = 21.0
_MINIMUM_ABSOLUTE_DELTA = 0.02
_MAXIMUM_ABSOLUTE_DELTA = 0.375
_MINIMUM_TRADES_PER_HOUR = 20
_ROLLING_PRIOR_HOURS = 2_160
_MINIMUM_PRIOR_HOURS = 1_440
_BULLISH_QUANTILE = 0.99
_BEARISH_QUANTILE = 0.01
_AVAILABILITY_DELAY = pd.Timedelta(hours=1, seconds=60)


@dataclass(frozen=True)
class WeightedDirectionalTrade:
    """One eligible option trade with its causal directional USD weight."""

    trade_id: str
    timestamp_ms: int
    absolute_delta: float
    weight_usd: float
    signed_weight_usd: float


def absolute_spot_delta(
    spot: float,
    strike: float,
    volatility: float,
    time_years: float,
    option_type: str,
) -> float:
    """Return zero-rate Black-Scholes absolute spot delta."""
    _require_positive(spot, "spot")
    _require_positive(strike, "strike")
    _require_positive(volatility, "volatility")
    _require_positive(time_years, "time_years")
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    denominator = volatility * math.sqrt(time_years)
    d1 = (
        math.log(spot / strike) + 0.5 * volatility * volatility * time_years
    ) / denominator
    call_delta = 0.5 * (1.0 + math.erf(d1 / math.sqrt(2.0)))
    return call_delta if option_type == "call" else 1.0 - call_delta


def eligible_absolute_delta(value: float) -> bool:
    """Return whether delta lies in the frozen (0.02, 0.375] population."""
    if not math.isfinite(value):
        raise ValueError("absolute delta must be finite")
    return _MINIMUM_ABSOLUTE_DELTA < value <= _MAXIMUM_ABSOLUTE_DELTA


def bullish_option_flow_sign(direction: str, option_type: str) -> int:
    """Return the frozen bullish sign for taker direction and option type."""
    if direction not in ("buy", "sell"):
        raise ValueError("direction must be buy or sell")
    if option_type not in ("call", "put"):
        raise ValueError("option_type must be call or put")
    direction_sign = 1 if direction == "buy" else -1
    option_sign = 1 if option_type == "call" else -1
    return direction_sign * option_sign


def weighted_directional_trade(
    trade: OptionTrade,
    instrument: OptionInstrument,
) -> WeightedDirectionalTrade | None:
    """Return one frozen eligible trade weight or None when excluded."""
    if trade.instrument_name != instrument.instrument_name:
        raise ValueError("option trade and instrument identities do not match")
    if _nonordinary(trade) or trade.iv <= 0.0:
        return None
    expiry_days = (instrument.expiration_timestamp_ms - trade.timestamp_ms) / DAY_MS
    if not _MINIMUM_EXPIRY_DAYS <= expiry_days <= _MAXIMUM_EXPIRY_DAYS:
        return None
    delta = absolute_spot_delta(
        trade.index_price,
        instrument.strike,
        trade.iv / 100.0,
        expiry_days / _DAYS_PER_YEAR,
        instrument.option_type,
    )
    if not eligible_absolute_delta(delta):
        return None
    weight = trade.amount * instrument.contract_size * trade.index_price * delta
    _require_positive(weight, "trade weight")
    sign = bullish_option_flow_sign(trade.direction, instrument.option_type)
    return WeightedDirectionalTrade(
        trade.trade_id,
        trade.timestamp_ms,
        delta,
        weight,
        sign * weight,
    )


def aggregate_weighted_trades(
    trades: Sequence[WeightedDirectionalTrade],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Aggregate weighted trades onto a complete frozen hourly grid."""
    start_at, end_at = _hour_bounds(start, end)
    records = [_weighted_record(value, start_at, end_at) for value in trades]
    if len({value.trade_id for value in trades}) != len(trades):
        raise ValueError("weighted option trades contain duplicate trade IDs")
    columns = ["timestamp", "weight_usd", "signed_weight_usd"]
    frame = pd.DataFrame.from_records(records, columns=columns)
    grouped = _group_weighted_rows(frame)
    hours = pd.date_range(start_at, end_at, freq="1h", inclusive="left")
    output = grouped.reindex(hours)
    output.index.name = "timestamp"
    output["eligible_trade_count"] = (
        output["eligible_trade_count"].fillna(0).astype(int)
    )
    output[["weight_usd", "signed_weight_usd"]] = output[
        ["weight_usd", "signed_weight_usd"]
    ].fillna(0.0)
    eligible = output["eligible_trade_count"].ge(_MINIMUM_TRADES_PER_HOUR)
    output["directional_imbalance"] = (
        output["signed_weight_usd"] / output["weight_usd"]
    ).where(eligible)
    return output.reset_index()


def build_causal_flow_signals(hourly: pd.DataFrame) -> pd.DataFrame:
    """Add frozen prior-window thresholds and causal flow-onset signals."""
    output = _validated_hourly(hourly)
    feature = output["directional_imbalance"].where(
        output["eligible_trade_count"].ge(_MINIMUM_TRADES_PER_HOUR)
    )
    output["directional_imbalance"] = feature
    prior = feature.shift(1).rolling(
        _ROLLING_PRIOR_HOURS,
        min_periods=_MINIMUM_PRIOR_HOURS,
    )
    output["upper_threshold"] = prior.quantile(_BULLISH_QUANTILE)
    output["lower_threshold"] = prior.quantile(_BEARISH_QUANTILE)
    previous = _previous_eligible(output, feature)
    current_eligible = feature.notna()
    output["long_onset"] = (
        current_eligible
        & feature.ge(output["upper_threshold"])
        & previous["flow"].lt(previous["upper"])
    )
    output["opposing_onset"] = (
        current_eligible
        & feature.le(output["lower_threshold"])
        & previous["flow"].gt(previous["lower"])
    )
    output["available_at"] = output["timestamp"] + _AVAILABILITY_DELAY
    return output


def _hour_bounds(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_at, end_at = pd.Timestamp(start), pd.Timestamp(end)
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("option-flow hourly bounds must be timezone-aware")
    start_at, end_at = start_at.tz_convert("UTC"), end_at.tz_convert("UTC")
    if start_at != start_at.floor("h") or end_at != end_at.floor("h"):
        raise ValueError("option-flow hourly bounds must be hour-aligned")
    if end_at <= start_at:
        raise ValueError("option-flow hourly bounds must be increasing")
    return start_at, end_at


def _weighted_record(
    value: WeightedDirectionalTrade,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, object]:
    _require_positive(value.weight_usd, "trade weight")
    if not math.isfinite(value.signed_weight_usd):
        raise ValueError("signed trade weight must be finite")
    timestamp = pd.to_datetime(value.timestamp_ms, unit="ms", utc=True)
    if not start <= timestamp < end:
        raise ValueError("weighted option trade timestamp is outside hourly bounds")
    return {
        "timestamp": timestamp.floor("h"),
        "weight_usd": value.weight_usd,
        "signed_weight_usd": value.signed_weight_usd,
    }


def _group_weighted_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=["eligible_trade_count", "weight_usd", "signed_weight_usd"]
        )
    return frame.groupby("timestamp", sort=True).agg(
        eligible_trade_count=("weight_usd", "size"),
        weight_usd=("weight_usd", "sum"),
        signed_weight_usd=("signed_weight_usd", "sum"),
    )


def _validated_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "eligible_trade_count", "directional_imbalance"}
    missing = sorted(required.difference(hourly.columns))
    if missing:
        raise ValueError(f"option-flow hourly rows missing columns: {missing}")
    output = hourly.loc[:, sorted(required)].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    timestamps = pd.DatetimeIndex(output["timestamp"])
    if (
        timestamps.hasnans
        or timestamps.has_duplicates
        or not timestamps.is_monotonic_increasing
    ):
        raise ValueError("option-flow hourly timestamps must be ordered and unique")
    expected = pd.date_range(timestamps.min(), timestamps.max(), freq="1h")
    if not timestamps.equals(expected):
        raise ValueError("option-flow hourly timestamps must have complete cadence")
    counts = pd.to_numeric(output["eligible_trade_count"], errors="raise")
    if counts.isna().any() or (counts < 0).any() or not counts.mod(1).eq(0).all():
        raise ValueError(
            "option-flow eligible trade counts must be nonnegative integers"
        )
    output["eligible_trade_count"] = counts.astype(int)
    _validate_imbalances(output)
    return output


def _validate_imbalances(frame: pd.DataFrame) -> None:
    values = pd.to_numeric(frame["directional_imbalance"], errors="raise")
    required = frame["eligible_trade_count"].ge(_MINIMUM_TRADES_PER_HOUR)
    if values[required].isna().any():
        raise ValueError("eligible option-flow hours require directional imbalance")
    finite = values.dropna().map(math.isfinite)
    if not finite.all() or values.dropna().abs().gt(1.0).any():
        raise ValueError("option-flow directional imbalance must be finite in [-1, 1]")
    frame["directional_imbalance"] = values.astype(float)


def _previous_eligible(
    output: pd.DataFrame,
    feature: pd.Series,
) -> pd.DataFrame:
    eligible = feature.notna()
    return pd.DataFrame(
        {
            "flow": feature.ffill().shift(1),
            "upper": output["upper_threshold"].where(eligible).ffill().shift(1),
            "lower": output["lower_threshold"].where(eligible).ffill().shift(1),
        }
    )


def _nonordinary(trade: OptionTrade) -> bool:
    return any(
        value is not None
        for value in (
            trade.block_trade_id,
            trade.block_rfq_id,
            trade.combo_id,
            trade.combo_trade_id,
        )
    )


def _require_positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
