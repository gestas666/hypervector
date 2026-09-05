"""Conservative report-only replay for the BTC delayed-component exit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path

import pandas as pd

from hypervector.cohort_profit_lock_policy import (
    POLICIES,
    ProfitLockTrigger,
    evaluate_profit_lock_path,
)
from hypervector.live.btc_hulk_delayed_component_floor import (
    BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
    build_btc_hulk_component_floor_observations,
    evaluate_delayed_component_floor,
)
from hypervector.live.multi_asset_market_bars import CohortMarketBar

_MINUTE_MS = 60_000


@dataclass(frozen=True)
class ReplayFriction:
    """Entry/market-exit fees and adverse market-exit slippage."""

    entry_fee_rate: float
    market_exit_fee_rate: float
    market_exit_slippage_bps: float

    def __post_init__(self) -> None:
        """Reject negative or non-finite friction assumptions."""
        values = (
            self.entry_fee_rate,
            self.market_exit_fee_rate,
            self.market_exit_slippage_bps,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError(
                "BTC component-exit friction must be finite and nonnegative"
            )


@dataclass(frozen=True)
class SourceTrade:
    """Frozen source lifecycle fields required for an exit counterfactual."""

    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    stop_price: float
    quantity: float
    control_net_pnl: float
    control_funding: float

    def __post_init__(self) -> None:
        """Reject malformed times, prices, or quantities."""
        prices = (self.entry_price, self.stop_price, self.quantity)
        if self.entry_time_ms < 0 or self.exit_time_ms < self.entry_time_ms:
            raise ValueError("BTC component-exit trade times are invalid")
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise ValueError("BTC component-exit trade prices must be positive")
        if not all(
            math.isfinite(value)
            for value in (self.control_net_pnl, self.control_funding)
        ):
            raise ValueError("BTC component-exit source economics are invalid")


def candidate_net_pnl(
    trade: SourceTrade,
    trigger: ProfitLockTrigger | None,
    friction: ReplayFriction,
) -> float:
    """Reprice one earlier short exit using frozen friction and elapsed funding."""
    if trigger is None:
        return trade.control_net_pnl
    slippage = friction.market_exit_slippage_bps / 10_000.0
    fill = trigger.reference_price * (1.0 + slippage)
    gross = trade.quantity * (trade.entry_price - fill)
    entry_fee = trade.quantity * trade.entry_price * friction.entry_fee_rate
    exit_fee = trade.quantity * fill * friction.market_exit_fee_rate
    control_duration = trade.exit_time_ms - trade.entry_time_ms
    candidate_duration = max(trigger.trigger_timestamp_ms - trade.entry_time_ms, 0)
    funding = (
        trade.control_funding * candidate_duration / control_duration
        if control_duration
        else 0.0
    )
    return gross - entry_fee - exit_fee + funding


def summarize_partition(
    values: Sequence[float], *, control_net: float, triggers: int
) -> dict[str, object]:
    """Return net, delta, leave-largest, win/loss, and trigger diagnostics."""
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("BTC component-exit partition values are invalid")
    net = float(sum(values))
    return {
        "net_pnl_usd": net,
        "improvement_usd": net - control_net,
        "net_without_largest_winner_usd": net - max(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value <= 0.0 for value in values),
        "triggers": triggers,
    }


def replay_partition(
    trades_path: Path,
    report_path: Path,
    candles: pd.DataFrame,
) -> dict[str, object]:
    """Replay V2 and frozen generic locks against one frozen source partition."""
    trades = pd.read_parquet(trades_path)
    friction = _friction(report_path)
    methods = (BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id,) + tuple(
        policy.policy_id for policy in POLICIES
    )
    values = {"control": []} | {method: [] for method in methods}
    triggers = {method: 0 for method in methods}
    modes = {"profit_floor": 0, "reversal_containment": 0}
    for raw in trades.to_dict("records"):
        trade = source_trade_from_record(raw)
        values["control"].append(trade.control_net_pnl)
        outcomes = _candidate_triggers(trade, candles)
        for method in methods:
            trigger = outcomes[method]
            values[method].append(candidate_net_pnl(trade, trigger, friction))
            triggers[method] += int(trigger is not None)
        mode = outcomes["component_activation_mode"]
        if isinstance(mode, str) and outcomes[methods[0]] is not None:
            modes[mode] += 1
    control = float(sum(values["control"]))
    return _partition_payload(values, triggers, modes, control, len(trades))


def load_minute_candles(path: Path) -> pd.DataFrame:
    """Load and validate one complete UTC minute-candle source."""
    frame = pd.read_parquet(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("BTC component-exit candles lack required columns")
    result = frame.set_index("timestamp").sort_index()
    if result.index.has_duplicates or not isinstance(result.index, pd.DatetimeIndex):
        raise ValueError("BTC component-exit candle index is invalid")
    return result


def _candidate_triggers(
    trade: SourceTrade,
    candles: pd.DataFrame,
) -> dict[str, ProfitLockTrigger | str | None]:
    methods = {policy.policy_id: None for policy in POLICIES}
    outcomes: dict[str, ProfitLockTrigger | str | None] = {
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id: None,
        "component_activation_mode": None,
    } | methods
    if trade.exit_time_ms <= trade.entry_time_ms + _MINUTE_MS:
        return outcomes
    bars = _trade_bars(trade, candles)
    first = trade.entry_time_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    observations = build_btc_hulk_component_floor_observations(
        bars, lifecycle_start_ms=first
    )
    state = evaluate_delayed_component_floor(
        BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY,
        side="short",
        observations=observations,
        opened_at_ms=trade.entry_time_ms,
        entry_price=trade.entry_price,
        protective_stop_price=trade.stop_price,
    )
    outcomes[BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id] = _prior_trigger(
        state.trigger, trade.exit_time_ms
    )
    outcomes["component_activation_mode"] = state.activation_mode
    lifecycle = tuple(bar for bar in bars if bar.timestamp_ms >= first)
    for policy in POLICIES:
        trigger = evaluate_profit_lock_path(
            policy, "short", lifecycle, trade.entry_price
        ).trigger
        outcomes[policy.policy_id] = _prior_trigger(trigger, trade.exit_time_ms)
    return outcomes


def _trade_bars(
    trade: SourceTrade,
    candles: pd.DataFrame,
) -> tuple[CohortMarketBar, ...]:
    first = trade.entry_time_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    seed = first - BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.warmup_ms
    last = trade.exit_time_ms - _MINUTE_MS
    scoped = candles.loc[_utc(seed) : _utc(last)]
    bars = tuple(_market_bar(timestamp, row) for timestamp, row in scoped.iterrows())
    expected = (last - seed) // _MINUTE_MS + 1
    if len(bars) != expected:
        raise ValueError(
            f"BTC component-exit candles are incomplete: expected={expected} "
            f"observed={len(bars)}"
        )
    return bars


def _market_bar(timestamp: object, row: pd.Series) -> CohortMarketBar:
    time = pd.Timestamp(timestamp)
    return CohortMarketBar(
        "BTC",
        int(time.timestamp() * 1_000),
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row["volume"]),
    )


def source_trade_from_record(raw: Mapping[str, object]) -> SourceTrade:
    """Validate BTC short route identity before applying BTC minute candles."""
    if raw.get("symbol") != "BTC" or raw.get("direction") != "short":
        raise ValueError("BTC component-exit replay requires BTC short source rows")
    return SourceTrade(
        _timestamp_ms(raw["entry_time_utc"]),
        _timestamp_ms(raw["exit_time_utc"]),
        _real(raw["entry_price"], "entry_price"),
        _real(raw["stop_price"], "stop_price"),
        _real(raw["initial_quantity"], "initial_quantity"),
        _real(raw["net_pnl_usd"], "net_pnl_usd"),
        _real(raw["funding_cashflow_usd"], "funding_cashflow_usd"),
    )


def _friction(report_path: Path) -> ReplayFriction:
    import json

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(
        payload.get("replay_parameters"), dict
    ):
        raise ValueError("BTC component-exit source report lacks replay parameters")
    values = payload["replay_parameters"]
    return ReplayFriction(
        _real(values["entry_fee_rate"], "entry_fee_rate"),
        _real(values["market_exit_fee_rate"], "market_exit_fee_rate"),
        _real(values["market_exit_slippage_bps"], "market_exit_slippage_bps"),
    )


def _partition_payload(
    values: Mapping[str, Sequence[float]],
    triggers: Mapping[str, int],
    modes: Mapping[str, int],
    control: float,
    trade_count: int,
) -> dict[str, object]:
    summaries = {
        method: summarize_partition(
            rows, control_net=control, triggers=triggers.get(method, 0)
        )
        for method, rows in values.items()
    }
    summaries[BTC_HULK_DELAYED_COMPONENT_EXIT_POLICY.policy_id]["activation_modes"] = (
        dict(modes)
    )
    return {"trades": trade_count, "methods": summaries}


def _prior_trigger(
    trigger: ProfitLockTrigger | None, control_exit_ms: int
) -> ProfitLockTrigger | None:
    return (
        trigger
        if trigger is not None and trigger.trigger_timestamp_ms < control_exit_ms
        else None
    )


def _timestamp_ms(value: object) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("BTC component-exit timestamp must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _utc(timestamp_ms: int) -> pd.Timestamp:
    return pd.Timestamp(timestamp_ms, unit="ms", tz="UTC")


def _real(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"BTC component-exit {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"BTC component-exit {label} must be finite")
    return result
