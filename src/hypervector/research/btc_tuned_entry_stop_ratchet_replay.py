"""Causal report-only replay for the BTC tuned-v2 entry-stop ratchet."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from numbers import Real

import pandas as pd

from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.research.btc_hulk_component_exit_replay import (
    ReplayFriction,
    SourceTrade,
)

_MINUTE_MS = 60_000
_ROUTE_CANDIDATE = "hulk_expansion_short_tuned_v2"
_ROUTE_SYMBOL = "BTC"
_ROUTE_DIRECTION = "short"


@dataclass(frozen=True)
class EntryStopRatchetPolicy:
    """Immutable activation and source-target contract for one candidate."""

    policy_id: str
    activation_r_multiple: float
    target_r_multiple: float

    def __post_init__(self) -> None:
        """Reject empty identity and invalid R multiples."""
        values = (self.activation_r_multiple, self.target_r_multiple)
        if not self.policy_id.strip() or any(
            not math.isfinite(value) or value <= 0.0 for value in values
        ):
            raise ValueError("BTC tuned entry-stop policy is invalid")


@dataclass(frozen=True)
class EntryStopRatchetTrigger:
    """First later-bar crossing of the activated raw-entry stop."""

    activation_timestamp_ms: int
    trigger_timestamp_ms: int
    reference_price: float
    stop_price: float


@dataclass(frozen=True)
class EntryStopRatchetPathState:
    """Causal candidate state through the frozen source lifecycle."""

    activation_timestamp_ms: int | None
    trigger: EntryStopRatchetTrigger | None
    control_boundary_reason: str | None
    control_boundary_timestamp_ms: int | None


BTC_TUNED_ENTRY_STOP_RATCHET = EntryStopRatchetPolicy(
    policy_id="btc_tuned_one_r_entry_stop_ratchet_v1",
    activation_r_multiple=1.0,
    target_r_multiple=3.0,
)


def evaluate_entry_stop_ratchet(
    trade: SourceTrade,
    bars: Sequence[CohortMarketBar],
    policy: EntryStopRatchetPolicy = BTC_TUNED_ENTRY_STOP_RATCHET,
) -> EntryStopRatchetPathState:
    """Evaluate the fixed short-only ratchet with source exits taking priority."""
    _validate_trade_path(trade, bars)
    risk = trade.stop_price - trade.entry_price
    if risk <= 0.0:
        raise ValueError("BTC tuned short stop must be above entry")
    activation_price = trade.entry_price - policy.activation_r_multiple * risk
    target_price = trade.entry_price - policy.target_r_multiple * risk
    if target_price <= 0.0:
        raise ValueError("BTC tuned structural target must be positive")
    activation: int | None = None
    for bar in bars:
        boundary = _structural_boundary(bar, trade.stop_price, target_price)
        if boundary is not None:
            return EntryStopRatchetPathState(
                activation, None, boundary, bar.timestamp_ms
            )
        if activation is not None and bar.high >= trade.entry_price:
            reference = max(trade.entry_price, bar.open)
            trigger = EntryStopRatchetTrigger(
                activation, bar.timestamp_ms, reference, trade.entry_price
            )
            return EntryStopRatchetPathState(activation, trigger, None, None)
        if activation is None and bar.close <= activation_price:
            activation = bar.timestamp_ms
    return EntryStopRatchetPathState(activation, None, None, None)


def ratchet_candidate_net_pnl(
    trade: SourceTrade,
    trigger: EntryStopRatchetTrigger | None,
    friction: ReplayFriction,
) -> float:
    """Reprice a candidate short exit or retain the exact control result."""
    if trigger is None:
        return trade.control_net_pnl
    slippage = friction.market_exit_slippage_bps / 10_000.0
    fill = trigger.reference_price * (1.0 + slippage)
    gross = trade.quantity * (trade.entry_price - fill)
    entry_fee = trade.quantity * trade.entry_price * friction.entry_fee_rate
    exit_fee = trade.quantity * fill * friction.market_exit_fee_rate
    control_duration = trade.exit_time_ms - trade.entry_time_ms
    candidate_duration = trigger.trigger_timestamp_ms - trade.entry_time_ms
    funding = (
        trade.control_funding * candidate_duration / control_duration
        if control_duration
        else 0.0
    )
    return gross - entry_fee - exit_fee + funding


def source_trade_from_record(raw: Mapping[str, object]) -> SourceTrade:
    """Validate exact route identity and project one frozen source trade."""
    identity = (raw.get("candidate"), raw.get("symbol"), raw.get("direction"))
    expected = (_ROUTE_CANDIDATE, _ROUTE_SYMBOL, _ROUTE_DIRECTION)
    if identity != expected:
        raise ValueError("row is not the exact BTC tuned-v2 short route")
    return SourceTrade(
        entry_time_ms=_timestamp_ms(raw.get("entry_time_utc")),
        exit_time_ms=_timestamp_ms(raw.get("exit_time_utc")),
        entry_price=_real(raw.get("entry_price"), "entry_price"),
        stop_price=_real(raw.get("stop_price"), "stop_price"),
        quantity=_real(raw.get("initial_quantity"), "initial_quantity"),
        control_net_pnl=_real(raw.get("net_pnl_usd"), "net_pnl_usd"),
        control_funding=_real(raw.get("funding_cashflow_usd"), "funding_cashflow_usd"),
    )


def summarize_ratchet_partition(
    control_values: Sequence[float],
    candidate_values: Sequence[float],
    *,
    triggers: int,
    activations: int,
    structural_boundaries: int,
) -> dict[str, object]:
    """Summarize control and candidate economics for one frozen partition."""
    _validate_summary_inputs(control_values, candidate_values)
    control = _economics_summary(control_values)
    candidate = _economics_summary(candidate_values)
    candidate["improvement_usd"] = _metric(candidate, "net_pnl_usd") - _metric(
        control, "net_pnl_usd"
    )
    candidate["leave_largest_improvement_usd"] = _metric(
        candidate, "net_without_largest_winner_usd"
    ) - _metric(control, "net_without_largest_winner_usd")
    candidate["worst_trade_improvement_usd"] = _metric(
        candidate, "worst_trade_net_pnl_usd"
    ) - _metric(control, "worst_trade_net_pnl_usd")
    return {
        "trades": len(control_values),
        "control": control,
        "candidate": candidate,
        "triggers": _nonnegative_count(triggers, "triggers"),
        "activations": _nonnegative_count(activations, "activations"),
        "structural_boundaries": _nonnegative_count(
            structural_boundaries, "structural_boundaries"
        ),
    }


def partition_passes_gates(summary: Mapping[str, object]) -> bool:
    """Apply every preregistered economic and exercise gate to a partition."""
    control = _mapping(summary.get("control"), "control")
    candidate = _mapping(summary.get("candidate"), "candidate")
    triggers = _integer(summary.get("triggers"), "triggers")
    candidate_net = _metric(candidate, "net_pnl_usd")
    control_net = _metric(control, "net_pnl_usd")
    candidate_tail = _metric(candidate, "net_without_largest_winner_usd")
    control_tail = _metric(control, "net_without_largest_winner_usd")
    candidate_worst = _metric(candidate, "worst_trade_net_pnl_usd")
    control_worst = _metric(control, "worst_trade_net_pnl_usd")
    return bool(
        triggers > 0
        and candidate_net >= control_net
        and candidate_tail >= control_tail
        and candidate_net >= 0.0
        and candidate_tail >= 0.0
        and candidate_worst >= control_worst
    )


def replay_route_records(
    records: Sequence[Mapping[str, object]],
    friction: ReplayFriction,
    candles: pd.DataFrame,
) -> dict[str, object]:
    """Replay exact BTC tuned rows and retain inspectable lifecycle evidence."""
    if not records:
        raise ValueError("BTC tuned route replay requires source records")
    _validate_candle_frame(candles)
    control_values: list[float] = []
    candidate_values: list[float] = []
    lifecycles: list[dict[str, object]] = []
    activations = 0
    triggers = 0
    structural = 0
    for raw in records:
        trade = source_trade_from_record(raw)
        state = evaluate_entry_stop_ratchet(trade, _trade_bars(trade, candles))
        candidate_net = ratchet_candidate_net_pnl(trade, state.trigger, friction)
        control_values.append(trade.control_net_pnl)
        candidate_values.append(candidate_net)
        activations += int(state.activation_timestamp_ms is not None)
        triggers += int(state.trigger is not None)
        structural += int(state.control_boundary_reason is not None)
        lifecycles.append(_lifecycle_payload(trade, state, candidate_net))
    result = summarize_ratchet_partition(
        control_values,
        candidate_values,
        triggers=triggers,
        activations=activations,
        structural_boundaries=structural,
    )
    result["passes_partition_gates"] = partition_passes_gates(result)
    result["lifecycles"] = lifecycles
    return result


def _validate_trade_path(trade: SourceTrade, bars: Sequence[CohortMarketBar]) -> None:
    duration = trade.exit_time_ms - trade.entry_time_ms
    if duration % _MINUTE_MS:
        raise ValueError("BTC tuned lifecycle boundaries must align to minutes")
    expected_count = duration // _MINUTE_MS
    if len(bars) != expected_count:
        raise ValueError(
            "BTC tuned minute path is incomplete: "
            f"expected={expected_count} observed={len(bars)}"
        )
    for offset, bar in enumerate(bars):
        expected_time = trade.entry_time_ms + offset * _MINUTE_MS
        if bar.symbol != _ROUTE_SYMBOL or bar.timestamp_ms != expected_time:
            raise ValueError("BTC tuned minute path is incomplete or misrouted")


def _validate_candle_frame(candles: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(candles.columns))
    index = candles.index
    if missing:
        raise ValueError(f"BTC tuned candles lack columns: {missing}")
    if not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC":
        raise ValueError("BTC tuned candles require a UTC datetime index")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("BTC tuned candle timestamps must be unique and ordered")


def _trade_bars(
    trade: SourceTrade, candles: pd.DataFrame
) -> tuple[CohortMarketBar, ...]:
    if trade.exit_time_ms == trade.entry_time_ms:
        return ()
    first = pd.Timestamp(trade.entry_time_ms, unit="ms", tz="UTC")
    last = pd.Timestamp(trade.exit_time_ms - _MINUTE_MS, unit="ms", tz="UTC")
    scoped = candles.loc[first:last]
    return tuple(
        CohortMarketBar(
            _ROUTE_SYMBOL,
            int(pd.Timestamp(timestamp).timestamp() * 1_000),
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["volume"]),
        )
        for timestamp, row in scoped.iterrows()
    )


def _lifecycle_payload(
    trade: SourceTrade,
    state: EntryStopRatchetPathState,
    candidate_net: float,
) -> dict[str, object]:
    trigger = state.trigger
    return {
        "entry_time_ms": trade.entry_time_ms,
        "control_exit_time_ms": trade.exit_time_ms,
        "control_net_pnl_usd": trade.control_net_pnl,
        "candidate_net_pnl_usd": candidate_net,
        "improvement_usd": candidate_net - trade.control_net_pnl,
        "activation_timestamp_ms": state.activation_timestamp_ms,
        "trigger_timestamp_ms": (
            None if trigger is None else trigger.trigger_timestamp_ms
        ),
        "trigger_reference_price": (
            None if trigger is None else trigger.reference_price
        ),
        "control_boundary_reason": state.control_boundary_reason,
        "control_boundary_timestamp_ms": state.control_boundary_timestamp_ms,
    }


def _validate_summary_inputs(
    control_values: Sequence[float], candidate_values: Sequence[float]
) -> None:
    if not control_values or len(control_values) != len(candidate_values):
        raise ValueError("BTC tuned partition outcomes are empty or misaligned")
    values = tuple(control_values) + tuple(candidate_values)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("BTC tuned partition outcomes must be finite")


def _economics_summary(values: Sequence[float]) -> dict[str, object]:
    net = float(sum(values))
    return {
        "net_pnl_usd": net,
        "net_without_largest_winner_usd": net - max(values),
        "worst_trade_net_pnl_usd": min(values),
        "largest_winner_net_pnl_usd": max(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value <= 0.0 for value in values),
    }


def _metric(values: Mapping[str, object], key: str) -> float:
    return _real(values.get(key), key)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"BTC tuned partition {label} must be a mapping")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"BTC tuned partition {label} must be an integer")
    return value


def _nonnegative_count(value: int, label: str) -> int:
    result = _integer(value, label)
    if result < 0:
        raise ValueError(f"BTC tuned partition {label} must be nonnegative")
    return result


def _structural_boundary(
    bar: CohortMarketBar, stop_price: float, target_price: float
) -> str | None:
    stop_crossed = bar.high >= stop_price
    target_crossed = bar.low <= target_price
    if stop_crossed and target_crossed:
        return "structural_ambiguous"
    if stop_crossed:
        return "structural_stop"
    if target_crossed:
        return "structural_target"
    return None


def _timestamp_ms(value: object) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("BTC tuned source timestamp must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"BTC tuned source {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"BTC tuned source {label} must be finite")
    return result
