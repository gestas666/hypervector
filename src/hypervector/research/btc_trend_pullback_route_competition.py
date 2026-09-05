"""Report-only one-position competition for current V58 BTC routes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from typing import Literal

import pandas as pd

from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import (
    Direction,
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.shared_portfolio_pricing import adverse_price


BarrierPolicy = Literal["fixed_60_60", "structural_20_75_3r"]


@dataclass(frozen=True)
class BtcRouteEvent:
    """One completed-bar V58 BTC entry event with explicit priority."""

    strategy_id: str
    direction: Direction
    priority: int
    signal_time: pd.Timestamp
    barrier_policy: BarrierPolicy
    stop_anchor: float | None = None

    def __post_init__(self) -> None:
        """Reject incomplete identities, times, priorities, or barriers."""
        timestamp = pd.Timestamp(self.signal_time)
        if not self.strategy_id.strip() or timestamp.tz is None:
            raise ValueError("BTC route event requires identity and aware time")
        if self.priority < 0:
            raise ValueError("BTC route priority must be non-negative")
        if self.barrier_policy == "structural_20_75_3r":
            if self.direction != "short" or not _positive(self.stop_anchor):
                raise ValueError("structural BTC short requires a positive stop anchor")
        elif self.stop_anchor is not None:
            raise ValueError("fixed BTC route cannot carry a structural stop")

    @classmethod
    def fixed(
        cls,
        strategy_id: str,
        direction: Direction,
        priority: int,
        signal_time: pd.Timestamp,
    ) -> BtcRouteEvent:
        """Build a frozen 60-bps stop and target route event."""
        return cls(strategy_id, direction, priority, signal_time, "fixed_60_60")

    @classmethod
    def structural(
        cls,
        strategy_id: str,
        priority: int,
        signal_time: pd.Timestamp,
        stop_anchor: float,
    ) -> BtcRouteEvent:
        """Build a frozen V58 structural-clamped 3R short event."""
        return cls(
            strategy_id,
            "short",
            priority,
            signal_time,
            "structural_20_75_3r",
            stop_anchor,
        )


@dataclass(frozen=True)
class BtcRouteCase:
    """One chronological shared BTC case and its displacement attribution."""

    report: SharedPortfolioReport
    raw_events: int
    scheduled_events: int
    same_minute_priority_displacements: int
    occupancy_displacements: int


@dataclass(frozen=True)
class BtcRouteComparison:
    """Baseline and candidate cases with exact reported deltas."""

    baseline: BtcRouteCase
    candidate: BtcRouteCase
    incremental_net_pnl_usd: float
    incremental_maximum_drawdown_pct: float


def evaluate_btc_route_case(
    minute_bars: pd.DataFrame,
    events: Sequence[BtcRouteEvent],
    slippage_bps_per_taker_side: float,
) -> BtcRouteCase:
    """Replay prioritized mixed-exit BTC events through one funded position."""
    slippage = _slippage(slippage_bps_per_taker_side)
    ordered, priority_displacements = _prioritized_events(events)
    signals = _signal_frame(minute_bars, ordered, slippage)
    report = evaluate_shared_bar_portfolio(
        _market(minute_bars), signals, _portfolio_config(slippage)
    )
    occupancy = _occupancy_displacements(ordered, report)
    return BtcRouteCase(
        report=report,
        raw_events=len(events),
        scheduled_events=len(ordered),
        same_minute_priority_displacements=priority_displacements,
        occupancy_displacements=occupancy,
    )


def compare_btc_route_cases(
    minute_bars: pd.DataFrame,
    baseline_events: Sequence[BtcRouteEvent],
    candidate_events: Sequence[BtcRouteEvent],
    slippage_bps_per_taker_side: float,
) -> BtcRouteComparison:
    """Compare unchanged V58 routes with the additive candidate case."""
    baseline = evaluate_btc_route_case(
        minute_bars, baseline_events, slippage_bps_per_taker_side
    )
    candidate = evaluate_btc_route_case(
        minute_bars,
        (*baseline_events, *candidate_events),
        slippage_bps_per_taker_side,
    )
    return BtcRouteComparison(
        baseline=baseline,
        candidate=candidate,
        incremental_net_pnl_usd=(
            candidate.report.net_pnl_usd - baseline.report.net_pnl_usd
        ),
        incremental_maximum_drawdown_pct=(
            candidate.report.maximum_drawdown_pct - baseline.report.maximum_drawdown_pct
        ),
    )


def identity_unavailable(missing_dependencies: Sequence[str]) -> dict[str, object]:
    """Publish an explicit no-substitution identity failure."""
    missing = sorted({value.strip() for value in missing_dependencies if value.strip()})
    if not missing:
        raise ValueError("identity-unavailable result requires a missing dependency")
    return {
        "status": "identity_unavailable",
        "missing_dependencies": missing,
        "substitute_profile_used": False,
    }


def _prioritized_events(
    events: Sequence[BtcRouteEvent],
) -> tuple[tuple[BtcRouteEvent, ...], int]:
    grouped: dict[pd.Timestamp, list[BtcRouteEvent]] = {}
    for event in events:
        timestamp = pd.Timestamp(event.signal_time).tz_convert("UTC")
        grouped.setdefault(timestamp, []).append(event)
    selected: list[BtcRouteEvent] = []
    displaced = 0
    for timestamp in sorted(grouped):
        ranked = sorted(
            grouped[timestamp], key=lambda value: (-value.priority, value.strategy_id)
        )
        selected.append(ranked[0])
        displaced += len(ranked) - 1
    return tuple(selected), displaced


def _signal_frame(
    bars: pd.DataFrame,
    events: Sequence[BtcRouteEvent],
    slippage: float,
) -> pd.DataFrame:
    signals = pd.DataFrame(
        {
            "entry_direction": None,
            "exit_signal": False,
            "signal_name": None,
            "target_price": math.nan,
            "stop_price": math.nan,
        },
        index=bars.index,
    )
    positions = {timestamp: position for position, timestamp in enumerate(bars.index)}
    for event in events:
        timestamp = pd.Timestamp(event.signal_time).tz_convert("UTC")
        position = positions.get(timestamp)
        if position is None or position + 1 >= len(bars):
            continue
        entry = adverse_price(
            float(bars["open"].iloc[position + 1]),
            event.direction,
            slippage,
            entering=True,
        )
        target, stop = _barriers(event, entry)
        signals.loc[timestamp, "entry_direction"] = event.direction
        signals.loc[timestamp, "signal_name"] = event.strategy_id
        signals.loc[timestamp, "target_price"] = target
        signals.loc[timestamp, "stop_price"] = stop
    return signals


def _barriers(event: BtcRouteEvent, entry: float) -> tuple[float, float]:
    if event.barrier_policy == "fixed_60_60":
        sign = 1.0 if event.direction == "long" else -1.0
        return entry * (1.0 + sign * 0.006), entry * (1.0 - sign * 0.006)
    anchor = float(event.stop_anchor)
    minimum = entry * 1.002
    maximum = entry * 1.0075
    stop = min(max(anchor, minimum), maximum)
    return entry - 3.0 * (stop - entry), stop


def _market(bars: pd.DataFrame) -> pd.DataFrame:
    if "funding_rate" not in bars:
        raise ValueError("BTC route competition requires exact funding_rate")
    output = bars.copy()
    if "gap_before_bars" not in output:
        output["gap_before_bars"] = 0
    return output


def _portfolio_config(slippage: float) -> SharedPortfolioConfig:
    return SharedPortfolioConfig(
        symbol="BTC",
        initial_equity=5_000.0,
        margin_fraction=0.10,
        leverage=10.0,
        venue_max_leverage=40.0,
        maximum_notional_usd=5_000.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=slippage,
        market_exit_slippage_bps=slippage,
        liquidation_slippage_bps=slippage,
        max_hold_seconds=86_400,
        reentry_cooldown_bars=1,
        same_direction_reentry_requires_reset=False,
        close_on_opposite_signal=False,
    )


def _occupancy_displacements(
    events: Sequence[BtcRouteEvent], report: SharedPortfolioReport
) -> int:
    filled = {(trade.signal_time_utc, trade.signal_name) for trade in report.trades}
    occupied = 0
    for event in events:
        identity = (pd.Timestamp(event.signal_time).isoformat(), event.strategy_id)
        if identity in filled:
            continue
        timestamp = pd.Timestamp(event.signal_time)
        if any(
            pd.Timestamp(trade.signal_time_utc)
            <= timestamp
            <= pd.Timestamp(trade.exit_time_utc)
            for trade in report.trades
        ):
            occupied += 1
    return occupied


def _slippage(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError("BTC route slippage must be finite and non-negative")
    return numeric


def _positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0
