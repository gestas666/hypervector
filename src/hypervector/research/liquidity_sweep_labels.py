"""Pessimistic lifecycle labels for five-minute liquidity-sweep events."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.liquidity_sweep_contract import LiquiditySweepConfig


_EVENT_COLUMNS = frozenset(
    {
        "event_id",
        "symbol",
        "bar_open_at",
        "available_at_utc",
        "arm",
        "side",
        "protective_extreme",
        "spread_bps_last",
    }
)
_BAR_COLUMNS = frozenset({"bar_open_at", "open", "high", "low", "close"})


def label_liquidity_sweep_events(
    bars: pd.DataFrame,
    events: pd.DataFrame,
    funding: pd.DataFrame,
    config: LiquiditySweepConfig,
) -> pd.DataFrame:
    """Label fixed structural barriers with stop-first intrabar ordering."""
    market = _validated_bars(bars)
    ordered = _validated_events(events, config)
    funding_rates = _validated_funding(funding)
    records = [
        _label_event(market, row, funding_rates, config)
        for _, row in ordered.iterrows()
    ]
    return pd.DataFrame(records)


def serialize_liquidity_sweep_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Apply one-position-per-symbol independently to each research arm."""
    required = {"arm", "symbol", "entry_time_utc", "outcome_time_utc", "status"}
    missing = sorted(required.difference(outcomes.columns))
    if missing:
        raise ValueError(f"liquidity sweep outcomes missing columns: {missing}")
    output = outcomes.copy().sort_values(
        ["arm", "symbol", "entry_time_utc", "event_id"]
    )
    output["accepted"] = False
    output["displacement_reason"] = None
    occupied: dict[tuple[str, str], pd.Timestamp] = {}
    minimum = pd.Timestamp.min.tz_localize("UTC")
    for index, row in output.iterrows():
        key = (str(row["arm"]), str(row["symbol"]))
        entry = pd.Timestamp(row["entry_time_utc"])
        if entry < occupied.get(key, minimum):
            output.at[index, "displacement_reason"] = "symbol_position_open"
            continue
        accepted = str(row["status"]) not in {"truncated", "invalid_barrier"}
        output.at[index, "accepted"] = accepted
        if accepted:
            occupied[key] = pd.Timestamp(row["outcome_time_utc"])
    order = ["bar_open_at", "arm", "symbol", "event_id"]
    return output.sort_values(order).reset_index(drop=True)


def _label_event(
    market: pd.DataFrame,
    row: pd.Series,
    funding: pd.Series,
    config: LiquiditySweepConfig,
) -> dict[str, object]:
    entry_time = pd.Timestamp(row["available_at_utc"])
    base = row.to_dict()
    if entry_time not in market.index:
        return _invalid(base, entry_time, "truncated")
    side = str(row["side"])
    raw_entry = float(market.loc[entry_time, "open"])
    entry = _adverse_price(raw_entry, side, config, entering=True)
    barriers = _structural_barriers(entry, side, row, config)
    if barriers is None:
        return _invalid(base, entry_time, "invalid_barrier")
    target, stop = barriers
    resolved = _walk_path(
        market, entry_time, side, entry, target, stop, funding, config
    )
    if resolved is None:
        return _invalid(base, entry_time, "truncated")
    resolved["funding_bps"] = _funding_bps(
        side, funding, entry_time, pd.Timestamp(resolved["outcome_time_utc"])
    )
    return _outcome(base, entry_time, side, entry, target, stop, resolved, config)


def _structural_barriers(
    entry: float,
    side: str,
    row: pd.Series,
    config: LiquiditySweepConfig,
) -> tuple[float, float] | None:
    extreme = float(row["protective_extreme"])
    spread_bps = float(row["spread_bps_last"])
    if not all(math.isfinite(value) for value in (extreme, spread_bps)):
        return None
    if spread_bps < 0.0:
        return None
    pad = extreme * spread_bps / 10_000.0
    stop = extreme - pad if side == "long" else extreme + pad
    risk = entry - stop if side == "long" else stop - entry
    if risk <= 0.0:
        return None
    target = entry + risk * config.reward_risk_multiple
    if side == "short":
        target = entry - risk * config.reward_risk_multiple
    return target, stop


def _walk_path(
    market: pd.DataFrame,
    entry_time: pd.Timestamp,
    side: str,
    entry: float,
    target: float,
    stop: float,
    funding: pd.Series,
    config: LiquiditySweepConfig,
) -> dict[str, object] | None:
    path = _PathState()
    for offset in range(config.maximum_hold_bars):
        timestamp = entry_time + pd.Timedelta(minutes=offset * config.bar_minutes)
        if timestamp not in market.index:
            return None
        bar = market.loc[timestamp]
        outcome_time = timestamp + pd.Timedelta(minutes=config.bar_minutes)
        _update_path(path, bar, side, entry, funding, entry_time, outcome_time, config)
        target_hit, stop_hit = _touches(bar, side, target, stop)
        if stop_hit:
            status = "ambiguous_stop_first" if target_hit else "stop"
            return _resolved(path, status, outcome_time, stop)
        if target_hit:
            return _resolved(path, "target", outcome_time, target)
    final_time = entry_time + pd.Timedelta(
        minutes=(config.maximum_hold_bars - 1) * config.bar_minutes
    )
    outcome_time = final_time + pd.Timedelta(minutes=config.bar_minutes)
    return _resolved(
        path, "timeout", outcome_time, float(market.loc[final_time, "close"])
    )


class _PathState:
    """Mutable intratrade path extrema for one isolated label."""

    def __init__(self) -> None:
        self.maximum_favorable_bps = 0.0
        self.maximum_adverse_bps = 0.0
        self.sampled_peak_bps = -math.inf
        self.sampled_trough_bps = math.inf
        self.sampled_maximum_drawdown_bps = 0.0


def _update_path(
    path: _PathState,
    bar: pd.Series,
    side: str,
    entry: float,
    funding: pd.Series,
    entry_time: pd.Timestamp,
    outcome_time: pd.Timestamp,
    config: LiquiditySweepConfig,
) -> None:
    favorable_price = float(bar["high"] if side == "long" else bar["low"])
    adverse_price = float(bar["low"] if side == "long" else bar["high"])
    favorable = _signed_return_bps(side, entry, favorable_price)
    adverse = -_signed_return_bps(side, entry, adverse_price)
    path.maximum_favorable_bps = max(path.maximum_favorable_bps, favorable)
    path.maximum_adverse_bps = max(path.maximum_adverse_bps, adverse)
    funding_bps = _funding_bps(side, funding, entry_time, outcome_time)
    entry_fee = config.fee_bps_per_side
    favorable_net = favorable - entry_fee + funding_bps
    adverse_net = -adverse - entry_fee + funding_bps
    path.sampled_peak_bps = max(path.sampled_peak_bps, favorable_net)
    path.sampled_maximum_drawdown_bps = max(
        path.sampled_maximum_drawdown_bps,
        path.sampled_peak_bps - adverse_net,
    )
    path.sampled_trough_bps = min(path.sampled_trough_bps, adverse_net)


def _resolved(
    path: _PathState, status: str, outcome_time: pd.Timestamp, raw_exit: float
) -> dict[str, object]:
    return {
        "status": status,
        "outcome_time_utc": outcome_time,
        "raw_exit_price": raw_exit,
        "maximum_favorable_excursion_bps": path.maximum_favorable_bps,
        "maximum_adverse_excursion_bps": path.maximum_adverse_bps,
        "sampled_mtm_peak_bps": path.sampled_peak_bps,
        "sampled_mtm_trough_bps": path.sampled_trough_bps,
        "sampled_mtm_maximum_drawdown_bps": path.sampled_maximum_drawdown_bps,
    }


def _outcome(
    base: dict[str, object],
    entry_time: pd.Timestamp,
    side: str,
    entry: float,
    target: float,
    stop: float,
    resolved: dict[str, object],
    config: LiquiditySweepConfig,
) -> dict[str, object]:
    exit_price = _adverse_price(
        float(resolved["raw_exit_price"]), side, config, entering=False
    )
    outcome_time = pd.Timestamp(resolved["outcome_time_utc"])
    gross = _signed_return_bps(side, entry, exit_price)
    funding = float(resolved.pop("funding_bps", 0.0))
    fee_bps = 2.0 * config.fee_bps_per_side
    nominal = gross - fee_bps + funding
    return {
        **base,
        **resolved,
        "entry_time_utc": entry_time,
        "entry_price": entry,
        "exit_price": exit_price,
        "target_price": target,
        "stop_price": stop,
        "gross_return_bps": gross,
        "fee_bps": fee_bps,
        "funding_bps": funding,
        "net_return_bps_nominal": nominal,
        "net_return_bps_stress": nominal - config.stress_haircut_bps,
        "hold_minutes": (outcome_time - entry_time).total_seconds() / 60.0,
    }


def _touches(
    bar: pd.Series, side: str, target: float, stop: float
) -> tuple[bool, bool]:
    if side == "long":
        return float(bar["high"]) >= target, float(bar["low"]) <= stop
    return float(bar["low"]) <= target, float(bar["high"]) >= stop


def _adverse_price(
    raw: float, side: str, config: LiquiditySweepConfig, *, entering: bool
) -> float:
    direction = 1.0 if side == "long" else -1.0
    operation = direction if entering else -direction
    return raw * (1.0 + operation * config.slippage_bps_per_side / 10_000.0)


def _signed_return_bps(side: str, entry: float, price: float) -> float:
    sign = 1.0 if side == "long" else -1.0
    return sign * (price / entry - 1.0) * 10_000.0


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


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_BAR_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"liquidity sweep label bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["bar_open_at"])
    if bars.empty or times.tz is None or times.has_duplicates:
        raise ValueError("liquidity sweep bars require unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("liquidity sweep bars must be ordered")
    values = bars[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("liquidity sweep prices must be finite and positive")
    return bars.set_index("bar_open_at")


def _validated_events(
    events: pd.DataFrame, config: LiquiditySweepConfig
) -> pd.DataFrame:
    missing = sorted(_EVENT_COLUMNS.difference(events.columns))
    if missing:
        raise ValueError(f"liquidity sweep events missing columns: {missing}")
    if events.empty:
        return events.copy()
    output = events.copy()
    for name in ("available_at_utc", "bar_open_at"):
        output[name] = pd.to_datetime(output[name], utc=True)
    if not output["side"].isin(("long", "short")).all():
        raise ValueError("liquidity sweep side must be long or short")
    if not output["symbol"].isin(config.symbols).all():
        raise ValueError("liquidity sweep event contains unsupported symbol")
    return output.sort_values(["available_at_utc", "arm", "symbol"])


def _validated_funding(funding: pd.DataFrame) -> pd.Series:
    required = {"timestamp", "funding_rate"}
    missing = sorted(required.difference(funding.columns))
    if missing:
        raise ValueError(f"liquidity sweep funding missing columns: {missing}")
    if funding.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    times = pd.DatetimeIndex(pd.to_datetime(funding["timestamp"], utc=True))
    rates = funding["funding_rate"].astype(float).to_numpy()
    if times.has_duplicates or not times.is_monotonic_increasing:
        raise ValueError("liquidity sweep funding must be ordered and unique")
    if not np.isfinite(rates).all():
        raise ValueError("liquidity sweep funding rates must be finite")
    return pd.Series(rates, index=times)


def _invalid(
    base: dict[str, object], entry_time: pd.Timestamp, status: str
) -> dict[str, object]:
    values = {
        name: math.nan
        for name in (
            "entry_price",
            "exit_price",
            "target_price",
            "stop_price",
            "gross_return_bps",
            "fee_bps",
            "funding_bps",
            "net_return_bps_nominal",
            "net_return_bps_stress",
            "maximum_favorable_excursion_bps",
            "maximum_adverse_excursion_bps",
            "sampled_mtm_peak_bps",
            "sampled_mtm_trough_bps",
            "sampled_mtm_maximum_drawdown_bps",
            "hold_minutes",
        )
    }
    return {
        **base,
        **values,
        "entry_time_utc": entry_time,
        "outcome_time_utc": entry_time,
        "status": status,
    }
