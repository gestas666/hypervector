"""Causal fixed-lifecycle consolidation-wick stop counterfactuals."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd

from hypervector.research.hypervelocity_candidate_eval import (
    CandidateBarrierConfig,
    position_terms,
)

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class StopCounterfactualTrade:
    """One exact filled lifecycle annotated with a causal structural stop."""

    direction: Direction
    status: Literal["target_completed", "time_exited", "liquidated"]
    signal_time_utc: str
    entry_time_utc: str
    outcome_time_utc: str
    entry_price: float
    liquidation_price: float
    stop_price: float | None
    effective_stop: bool
    stop_hit: bool
    full_bars_scanned: int
    original_net_pnl_usd: float
    counterfactual_net_pnl_usd: float


@dataclass(frozen=True)
class StopCounterfactualReport:
    """Aggregate fixed-lifecycle stop evidence before stateful replay."""

    filled_lifecycles: int
    effective_stops: int
    ineffective_stops: int
    missing_stops: int
    stop_hits: int
    target_stop_regret: int
    liquidations_avoided: int
    original_net_pnl_usd: float
    counterfactual_net_pnl_usd: float
    net_pnl_delta_usd: float
    trades: tuple[StopCounterfactualTrade, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe counterfactual report."""
        return asdict(self)


def _validate_bounds_inputs(
    bars: pd.DataFrame,
    bbwp: pd.Series,
    threshold: float,
) -> None:
    missing = {"high", "low"}.difference(bars.columns)
    if missing:
        raise ValueError(f"consolidation bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("consolidation bars require a DatetimeIndex")
    if not bars.index.equals(bbwp.index):
        raise ValueError("consolidation bars and BBWP require the same index")
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        raise ValueError("consolidation BBWP threshold must be within [0, 100]")


def last_bbwp_consolidation_bounds(
    bars: pd.DataFrame,
    bbwp: pd.Series,
    *,
    threshold: float,
) -> pd.DataFrame:
    """Return frozen low/high from the latest completed compression episode."""
    _validate_bounds_inputs(bars, bbwp, threshold)
    active_low: float | None = None
    active_high: float | None = None
    frozen_low: float | None = None
    frozen_high: float | None = None
    rows: list[tuple[float | None, float | None]] = []
    for low, high, percentile in zip(bars["low"], bars["high"], bbwp, strict=True):
        compressed = not pd.isna(percentile) and float(percentile) < threshold
        if compressed:
            active_low = float(low) if active_low is None else min(active_low, low)
            active_high = float(high) if active_high is None else max(active_high, high)
        elif active_low is not None and active_high is not None:
            frozen_low, frozen_high = active_low, active_high
            active_low, active_high = None, None
        rows.append((frozen_low, frozen_high))
    return pd.DataFrame(rows, index=bars.index, columns=("long_stop", "short_stop"))


def attach_consolidation_wick_stops(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    threshold: float = 25.0,
) -> pd.DataFrame:
    """Attach the direction-specific frozen consolidation wick to each decision."""
    required = {"bbwp_percentile", "entry_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"wick-stop decisions missing: {sorted(missing)}")
    if not bars.index.equals(decisions.index):
        raise ValueError("wick-stop bars and decisions require the same index")
    direction = decisions["entry_direction"].astype(object)
    invalid = direction.notna() & ~direction.isin(("long", "short"))
    if invalid.any():
        raise ValueError("wick-stop entry_direction must be long, short, or missing")
    bounds = last_bbwp_consolidation_bounds(
        bars,
        decisions["bbwp_percentile"],
        threshold=threshold,
    )
    stops = pd.Series(float("nan"), index=decisions.index, dtype="float64")
    stops.loc[direction.eq("long")] = bounds.loc[direction.eq("long"), "long_stop"]
    stops.loc[direction.eq("short")] = bounds.loc[direction.eq("short"), "short_stop"]
    output = decisions.copy()
    output["entry_stop_price"] = stops
    return output


def _effective_stop(
    direction: Direction,
    stop_price: float | None,
    entry_price: float,
    liquidation_price: float,
) -> bool:
    if stop_price is None or pd.isna(stop_price):
        return False
    if direction == "long":
        return bool(liquidation_price < stop_price < entry_price)
    return bool(entry_price < stop_price < liquidation_price)


def _full_bars(
    bars: pd.DataFrame,
    entry_time: pd.Timestamp,
    outcome_time: pd.Timestamp,
) -> pd.DataFrame:
    start = entry_time.ceil("min")
    end = outcome_time.floor("min")
    return bars.loc[(bars.index >= start) & (bars.index < end)]


def _stop_hit(
    direction: Direction,
    stop_price: float,
    observed: pd.DataFrame,
) -> bool:
    if observed.empty:
        return False
    if direction == "long":
        return bool(observed["low"].le(stop_price).any())
    return bool(observed["high"].ge(stop_price).any())


def _counterfactual_trade(
    row: object,
    stop_price: float | None,
    bars: pd.DataFrame,
    config: CandidateBarrierConfig,
) -> StopCounterfactualTrade:
    direction: Direction = getattr(row, "direction")
    entry_price = float(getattr(row, "entry_price"))
    quantity = float(getattr(row, "quantity"))
    terms = position_terms(direction, entry_price, config.initial_equity, config)
    liquidation_price = _measured_liquidation_price(row, terms.liquidation_price)
    effective = bool(
        _effective_stop(direction, stop_price, entry_price, liquidation_price)
    )
    entry_time = pd.Timestamp(getattr(row, "entry_time_utc"))
    outcome_time = pd.Timestamp(getattr(row, "outcome_time_utc"))
    observed = _full_bars(bars, entry_time, outcome_time)
    hit = effective and _stop_hit(direction, float(stop_price), observed)
    original = float(getattr(row, "net_pnl"))
    counterfactual = original
    if hit:
        sign = 1.0 if direction == "long" else -1.0
        gross = sign * quantity * (float(stop_price) - entry_price)
        fees = quantity * (
            entry_price * config.maker_fee_rate
            + float(stop_price) * config.liquidation_fee_rate
        )
        counterfactual = gross - fees
    return StopCounterfactualTrade(
        direction,
        getattr(row, "status"),
        str(getattr(row, "signal_time_utc")),
        str(getattr(row, "entry_time_utc")),
        str(getattr(row, "outcome_time_utc")),
        entry_price,
        liquidation_price,
        None if stop_price is None or pd.isna(stop_price) else float(stop_price),
        effective,
        hit,
        len(observed),
        original,
        counterfactual,
    )


def _validated_lifecycles(lifecycles: pd.DataFrame) -> pd.DataFrame:
    required = {
        "direction",
        "signal_time_utc",
        "entry_time_utc",
        "outcome_time_utc",
        "status",
        "entry_price",
        "quantity",
        "net_pnl",
    }
    missing = required.difference(lifecycles.columns)
    if missing:
        raise ValueError(f"stop lifecycles missing columns: {sorted(missing)}")
    filled = lifecycles.loc[
        lifecycles["status"].isin(("target_completed", "time_exited", "liquidated"))
    ].copy()
    if filled[list(required)].isna().any().any():
        raise ValueError("filled stop lifecycles contain missing values")
    return filled


def _aggregate_report(
    trades: tuple[StopCounterfactualTrade, ...],
) -> StopCounterfactualReport:
    original = sum(trade.original_net_pnl_usd for trade in trades)
    counterfactual = sum(trade.counterfactual_net_pnl_usd for trade in trades)
    return StopCounterfactualReport(
        len(trades),
        int(sum(trade.effective_stop for trade in trades)),
        int(
            sum(
                trade.stop_price is not None and not trade.effective_stop
                for trade in trades
            )
        ),
        int(sum(trade.stop_price is None for trade in trades)),
        int(sum(trade.stop_hit for trade in trades)),
        int(
            sum(
                trade.stop_hit and trade.status == "target_completed"
                for trade in trades
            )
        ),
        int(sum(trade.stop_hit and trade.status == "liquidated" for trade in trades)),
        float(original),
        float(counterfactual),
        float(counterfactual - original),
        trades,
    )


def evaluate_consolidation_wick_stops(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    lifecycles: pd.DataFrame,
    *,
    threshold: float = 25.0,
    config: CandidateBarrierConfig | None = None,
) -> StopCounterfactualReport:
    """Apply frozen consolidation wicks to exact filled replay lifecycles."""
    if "bbwp_percentile" not in decisions:
        raise ValueError("stop decisions require bbwp_percentile")
    bounds = last_bbwp_consolidation_bounds(
        bars, decisions["bbwp_percentile"], threshold=threshold
    )
    available = bounds.copy()
    available.index = available.index + pd.Timedelta(minutes=1)
    filled = _validated_lifecycles(lifecycles)
    signals = pd.DatetimeIndex(pd.to_datetime(filled["signal_time_utc"], utc=True))
    aligned = available.reindex(signals)
    resolved = config or CandidateBarrierConfig()
    trades = tuple(
        _counterfactual_trade(
            row,
            aligned.iloc[position][f"{row.direction}_stop"],
            bars,
            resolved,
        )
        for position, row in enumerate(filled.itertuples(index=False))
    )
    return _aggregate_report(trades)


def _measured_liquidation_price(row: object, fallback: float) -> float:
    if not hasattr(row, "liquidation_price"):
        return fallback
    value = float(getattr(row, "liquidation_price"))
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("measured liquidation_price must be finite and positive")
    return value


def evaluate_liquidation_proximity_stops(
    bars: pd.DataFrame,
    lifecycles: pd.DataFrame,
    *,
    distance_fraction: float,
) -> StopCounterfactualReport:
    """Place a frozen failsafe inside each modeled liquidation boundary."""
    if not math.isfinite(distance_fraction) or not 0.0 < distance_fraction < 1.0:
        raise ValueError("distance_fraction must be finite within (0, 1)")
    filled = _validated_lifecycles(lifecycles)
    config = CandidateBarrierConfig()
    stop_prices: list[float] = []
    for row in filled.itertuples(index=False):
        direction: Direction = row.direction
        entry_price = float(row.entry_price)
        liquidation = position_terms(
            direction, entry_price, config.initial_equity, config
        ).liquidation_price
        stop_price = entry_price + distance_fraction * (liquidation - entry_price)
        stop_prices.append(stop_price)
    return _evaluate_stop_prices(bars, filled, stop_prices, config)


def _evaluate_stop_prices(
    bars: pd.DataFrame,
    filled: pd.DataFrame,
    stop_prices: list[float],
    config: CandidateBarrierConfig,
) -> StopCounterfactualReport:
    trades = tuple(
        _counterfactual_trade(row, stop_price, bars, config)
        for row, stop_price in zip(
            filled.itertuples(index=False), stop_prices, strict=True
        )
    )
    return _aggregate_report(trades)


def evaluate_fixed_margin_stops(
    bars: pd.DataFrame,
    lifecycles: pd.DataFrame,
    *,
    margin_stop_pct: float,
) -> StopCounterfactualReport:
    """Apply one fixed margin-loss stop to exact filled lifecycles."""
    if not math.isfinite(margin_stop_pct) or not 0.0 < margin_stop_pct < 100.0:
        raise ValueError("margin_stop_pct must be finite within (0, 100)")
    filled = _validated_lifecycles(lifecycles)
    config = CandidateBarrierConfig()
    price_fraction = margin_stop_pct / 100.0 / config.leverage
    stop_prices = [
        float(row.entry_price)
        * (1.0 - price_fraction if row.direction == "long" else 1.0 + price_fraction)
        for row in filled.itertuples(index=False)
    ]
    return _evaluate_stop_prices(bars, filled, stop_prices, config)


def _validate_pivot_inputs(
    bars: pd.DataFrame,
    left_bars: int,
    right_bars: int,
    buffer_bps: float,
) -> None:
    missing = {"high", "low"}.difference(bars.columns)
    if missing:
        raise ValueError(f"pivot stop bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("pivot stop bars require a DatetimeIndex")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("pivot stop bars require a unique increasing index")
    for name, value in (("left_bars", left_bars), ("right_bars", right_bars)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if not math.isfinite(buffer_bps) or buffer_bps < 0.0:
        raise ValueError("pivot stop buffer_bps must be finite and non-negative")
    cadence = bars.index.to_series().diff().iloc[1:]
    if not cadence.eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("pivot stop bars require uninterrupted one-minute cadence")


def _strict_pivot(
    values: pd.Series,
    position: int,
    left_bars: int,
    right_bars: int,
    *,
    low: bool,
) -> bool:
    center = float(values.iloc[position])
    neighbors = pd.concat(
        [
            values.iloc[position - left_bars : position],
            values.iloc[position + 1 : position + right_bars + 1],
        ]
    ).astype(float)
    return bool(center < neighbors.min() if low else center > neighbors.max())


def confirmed_pivot_stop_events(
    bars: pd.DataFrame,
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    buffer_bps: float = 0.0,
) -> pd.DataFrame:
    """Publish strict swing stops only after all right-side bars complete."""
    _validate_pivot_inputs(bars, left_bars, right_bars, buffer_bps)
    long_scale = 1.0 - buffer_bps / 10_000.0
    short_scale = 1.0 + buffer_bps / 10_000.0
    rows: list[dict[str, float | None]] = []
    indexes: list[pd.Timestamp] = []
    for position in range(left_bars, len(bars) - right_bars):
        low = _strict_pivot(bars["low"], position, left_bars, right_bars, low=True)
        high = _strict_pivot(bars["high"], position, left_bars, right_bars, low=False)
        if not low and not high:
            continue
        indexes.append(bars.index[position] + pd.Timedelta(minutes=right_bars + 1))
        rows.append(
            {
                "long_stop": float(bars["low"].iloc[position]) * long_scale
                if low
                else None,
                "short_stop": float(bars["high"].iloc[position]) * short_scale
                if high
                else None,
            }
        )
    events = pd.DataFrame(rows, index=pd.DatetimeIndex(indexes))
    if events.empty:
        return pd.DataFrame(columns=("long_stop", "short_stop"))
    return events.ffill()


def evaluate_confirmed_pivot_stops(
    bars: pd.DataFrame,
    lifecycles: pd.DataFrame,
    *,
    left_bars: int = 2,
    right_bars: int = 2,
    buffer_bps: float = 0.0,
) -> StopCounterfactualReport:
    """Apply latest causally confirmed strict pivot to exact filled lifecycles."""
    events = confirmed_pivot_stop_events(
        bars,
        left_bars=left_bars,
        right_bars=right_bars,
        buffer_bps=buffer_bps,
    )
    filled = _validated_lifecycles(lifecycles)
    signals = pd.DatetimeIndex(
        pd.to_datetime(filled["signal_time_utc"], utc=True, format="ISO8601")
    )
    aligned = events.reindex(signals, method="ffill")
    stop_prices = [
        aligned.iloc[position][f"{row.direction}_stop"]
        for position, row in enumerate(filled.itertuples(index=False))
    ]
    return _evaluate_stop_prices(
        bars,
        filled,
        stop_prices,
        CandidateBarrierConfig(),
    )
