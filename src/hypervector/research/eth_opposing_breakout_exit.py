"""Causal, report-only ETH exit on a fresh opposing five-minute breakout."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    HypeExitTrade,
    HypeSide,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)
from hypervector.research.hype_breakout_profit_research import (
    freeze_hype_entry_cohort,
)


@dataclass(frozen=True)
class EthOpposingBreakoutSpec:
    """One frozen opposing-breakout exit contract without live authority."""

    stop_bps: float = 60.0
    maximum_hold_minutes: int = 720
    fee_bps_per_side: float = 4.5
    slippage_bps_per_side: float = 2.0
    additional_decision_delay_minutes: int = 0

    def __post_init__(self) -> None:
        """Reject settings outside the two preregistered replay contracts."""
        _positive(self.stop_bps, "stop bps")
        if self.maximum_hold_minutes < 1:
            raise ValueError("ETH opposing-breakout maximum hold must be positive")
        _nonnegative(self.fee_bps_per_side, "fee bps")
        _nonnegative(self.slippage_bps_per_side, "slippage bps")
        if self.additional_decision_delay_minutes not in {0, 1}:
            raise ValueError("ETH opposing-breakout delay must be zero or one minute")


@dataclass(frozen=True)
class EthOpposingBreakoutTrigger:
    """One completed five-minute onset and its replay application time."""

    decision_time_utc: str
    applied_time_utc: str
    position_side: HypeSide
    breakout_side: HypeSide


@dataclass(frozen=True)
class EthOpposingBreakoutReplay:
    """Fixed-entry candidate replay plus directional evidence diagnostics."""

    report: HypeExitReplayReport
    triggers: tuple[EthOpposingBreakoutTrigger, ...]
    unavailable_direction_rows: tuple[str, ...]
    technical_status: str
    execution_authority: str = "none"


def replay_eth_opposing_breakout_exit(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
    spec: EthOpposingBreakoutSpec | None = None,
) -> EthOpposingBreakoutReplay:
    """Replay fixed ETH entries with a causal fresh adverse-breakout close."""
    candidate = spec or EthOpposingBreakoutSpec()
    _validate_market(market)
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    triggers, unavailable = _lifecycle_triggers(market, control_trades, candidate)
    replay_market = fixed_market.copy()
    replay_market["structural_direction"] = "neutral"
    if not unavailable:
        _apply_trigger_directions(replay_market, triggers)
    report = replay_hype_breakout_exits(
        replay_market,
        HypeExitPolicy(_policy_id(candidate), exit_on_reversal=True),
        _replay_config(candidate),
    )
    _require_entry_parity(control_trades, report.trades)
    return EthOpposingBreakoutReplay(
        report=report,
        triggers=() if unavailable else triggers,
        unavailable_direction_rows=unavailable,
        technical_status=(
            "resolved" if not unavailable else "unresolved_breakout_direction"
        ),
    )


def _lifecycle_triggers(
    market: pd.DataFrame,
    trades: tuple[HypeExitTrade, ...],
    spec: EthOpposingBreakoutSpec,
) -> tuple[tuple[EthOpposingBreakoutTrigger, ...], tuple[str, ...]]:
    fresh = market["state_5m"].eq("BREAKOUT") & market["state_5m"].shift().ne(
        "BREAKOUT"
    )
    triggers: list[EthOpposingBreakoutTrigger] = []
    unavailable: set[pd.Timestamp] = set()
    for trade in trades:
        trigger, missing = _trade_trigger(market, fresh, trade, spec)
        unavailable.update(missing)
        if trigger is not None:
            triggers.append(trigger)
    missing_rows = tuple(timestamp.isoformat() for timestamp in sorted(unavailable))
    return tuple(triggers), missing_rows


def _trade_trigger(
    market: pd.DataFrame,
    fresh: pd.Series,
    trade: HypeExitTrade,
    spec: EthOpposingBreakoutSpec,
) -> tuple[EthOpposingBreakoutTrigger | None, tuple[pd.Timestamp, ...]]:
    entry = pd.Timestamp(trade.entry_time_utc)
    end = pd.Timestamp(trade.exit_time_utc)
    if end < entry:
        raise ValueError("ETH opposing-breakout lifecycle exits before entry")
    if end == entry and trade.exit_reason == "protective_stop":
        return None, ()
    path = market.loc[(market.index >= entry) & (market.index < end)]
    for raw_timestamp in path.index[fresh.loc[path.index]]:
        timestamp = pd.Timestamp(raw_timestamp)
        side = _breakout_side(market.at[timestamp, "breakout_side"])
        if side is None:
            return None, (timestamp,)
        if side == trade.side:
            continue
        applied = _applied_timestamp(market.index, timestamp, spec)
        if applied is None or _next_timestamp(market.index, applied) > end:
            continue
        return _trigger(timestamp, applied, trade.side, side), ()
    return None, ()


def _applied_timestamp(
    index: pd.DatetimeIndex,
    timestamp: pd.Timestamp,
    spec: EthOpposingBreakoutSpec,
) -> pd.Timestamp | None:
    position = int(index.get_loc(timestamp)) + spec.additional_decision_delay_minutes
    return pd.Timestamp(index[position]) if position + 1 < len(index) else None


def _next_timestamp(index: pd.DatetimeIndex, timestamp: pd.Timestamp) -> pd.Timestamp:
    position = int(index.get_loc(timestamp))
    if position + 1 >= len(index):
        raise ValueError("ETH opposing-breakout trigger lacks a following open")
    return pd.Timestamp(index[position + 1])


def _trigger(
    decision: pd.Timestamp,
    applied: pd.Timestamp,
    position_side: HypeSide,
    breakout_side: HypeSide,
) -> EthOpposingBreakoutTrigger:
    return EthOpposingBreakoutTrigger(
        decision_time_utc=decision.isoformat(),
        applied_time_utc=applied.isoformat(),
        position_side=position_side,
        breakout_side=breakout_side,
    )


def _breakout_side(value: object) -> HypeSide | None:
    if pd.isna(value):
        return None
    normalized = str(value).strip().lower()
    if normalized == "long":
        return "long"
    if normalized == "short":
        return "short"
    return None


def _apply_trigger_directions(
    market: pd.DataFrame,
    triggers: tuple[EthOpposingBreakoutTrigger, ...],
) -> None:
    for trigger in triggers:
        market.at[pd.Timestamp(trigger.applied_time_utc), "structural_direction"] = (
            trigger.breakout_side
        )


def _replay_config(spec: EthOpposingBreakoutSpec) -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=spec.stop_bps,
        maximum_hold_minutes=spec.maximum_hold_minutes,
        fee_bps_per_side=spec.fee_bps_per_side,
        slippage_bps_per_side=spec.slippage_bps_per_side,
    )


def _policy_id(spec: EthOpposingBreakoutSpec) -> str:
    suffix = "next_open" if spec.additional_decision_delay_minutes == 0 else "delay_1m"
    return f"eth_opposing_breakout_{suffix}"


def _require_entry_parity(
    control: tuple[HypeExitTrade, ...],
    candidate: tuple[HypeExitTrade, ...],
) -> None:
    if [_entry_identity(trade) for trade in control] != [
        _entry_identity(trade) for trade in candidate
    ]:
        raise ValueError("ETH opposing-breakout replay changed the fixed entry cohort")


def _entry_identity(trade: HypeExitTrade) -> tuple[str, str, HypeSide]:
    return trade.signal_time_utc, trade.entry_time_utc, trade.side


def _validate_market(market: pd.DataFrame) -> None:
    if "breakout_side" not in market:
        raise ValueError("ETH opposing-breakout market is missing breakout_side")
    if not isinstance(market.index, pd.DatetimeIndex) or market.index.has_duplicates:
        raise ValueError(
            "ETH opposing-breakout market requires a unique datetime index"
        )
    if not market.index.is_monotonic_increasing:
        raise ValueError("ETH opposing-breakout market index must be ordered")


def _positive(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"ETH opposing-breakout {label} must be finite and positive")


def _nonnegative(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0.0:
        raise ValueError(
            f"ETH opposing-breakout {label} must be finite and nonnegative"
        )
