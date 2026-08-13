"""Causal one-minute replay of the deployed BTC source-follow mechanics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Protocol, Sequence

import pandas as pd

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.regime.source_follow_runtime import SourceFollowDecision
from hypervector.research.source_follow_live_shape_models import (
    SourceLiveExitReason,
    SourceLiveShapeConfig,
    SourceLiveShapeFunding,
    SourceLiveShapeReport,
    SourceLiveShapeSignal,
    SourceLiveShapeTrade,
    SourceSide,
)

_REQUIRED_BAR_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}


class SourceMinuteSignal(Protocol):
    """Minute-feed boundary needed to reproduce source decisions."""

    def update_minute(
        self,
        *,
        timestamp_utc: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> SourceFollowDecision | None:
        """Consume one completed minute and return the latest decision."""


@dataclass(frozen=True)
class _Exit:
    row: int
    price: float
    reason: SourceLiveExitReason
    fee_rate: float
    ambiguous: bool = False


@dataclass(frozen=True)
class _Entry:
    row: int
    time: pd.Timestamp
    price: float
    quantity: float
    fee: float
    stop: float
    target: float
    liquidation: float


def collect_source_live_shape_signals(
    bars: pd.DataFrame,
    signal: SourceMinuteSignal,
) -> tuple[SourceLiveShapeSignal, ...]:
    """Reconstruct every unique eligible bidirectional source onset."""
    frame = _normalized_bars(bars)
    decisions: list[SourceLiveShapeSignal] = []
    last_label: object | None = None
    for row in frame.itertuples(index=False):
        decision = signal.update_minute(
            timestamp_utc=row.timestamp.to_pydatetime(),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        if decision is None or decision.label_time_utc == last_label:
            continue
        last_label = decision.label_time_utc
        if not decision.entry_eligible or decision.entry_direction is None:
            continue
        decisions.append(
            SourceLiveShapeSignal(
                pd.Timestamp(decision.available_at_utc),
                decision.entry_direction,
                decision.bar_close,
                decision.confidence,
                decision.signal_range_bps,
            )
        )
    return tuple(decisions)


def replay_source_live_shape(
    bars: pd.DataFrame,
    funding: Sequence[SourceLiveShapeFunding],
    signals: Sequence[SourceLiveShapeSignal],
    config: SourceLiveShapeConfig | None = None,
) -> SourceLiveShapeReport:
    """Replay one BTC position at a time through exact deployed mechanics."""
    cfg = config or SourceLiveShapeConfig()
    frame = _normalized_bars(bars)
    ordered_funding = _ordered_funding(funding)
    ordered_signals = _ordered_signals(signals)
    equity = cfg.initial_equity
    peak = equity
    maximum_drawdown = 0.0
    occupied = 0
    rejected = 0
    ambiguous = 0
    trades: list[SourceLiveShapeTrade] = []
    busy_until: pd.Timestamp | None = None
    for signal in ordered_signals:
        if busy_until is not None and signal.decision_time <= busy_until:
            occupied += 1
            continue
        entry_row = int(frame.index.searchsorted(signal.decision_time, side="left"))
        if entry_row >= len(frame):
            break
        trade = _replay_trade(frame, ordered_funding, signal, entry_row, equity, cfg)
        if trade is None:
            rejected += 1
            continue
        trades.append(trade)
        equity += trade.net_pnl_usd
        peak = max(peak, equity)
        maximum_drawdown = min(maximum_drawdown, (equity - peak) / peak * 100.0)
        busy_until = pd.Timestamp(trade.exit_time_utc)
        ambiguous += int(trade.ambiguous_bar_exit)
    return _report(
        cfg,
        ordered_signals,
        trades,
        equity,
        maximum_drawdown,
        occupied,
        rejected,
        ambiguous,
    )


def _replay_trade(
    bars: pd.DataFrame,
    funding: tuple[SourceLiveShapeFunding, ...],
    signal: SourceLiveShapeSignal,
    entry_row: int,
    equity: float,
    config: SourceLiveShapeConfig,
) -> SourceLiveShapeTrade | None:
    entry = _open_trade(bars, signal.side, entry_row, equity, config)
    if entry is None:
        return None
    exit_ = _find_exit(
        bars,
        entry.row,
        signal.side,
        entry.stop,
        entry.target,
        entry.liquidation,
        config,
    )
    return _settle_trade(bars, funding, signal, entry, exit_, config)


def _open_trade(
    bars: pd.DataFrame,
    side: SourceSide,
    entry_row: int,
    equity: float,
    config: SourceLiveShapeConfig,
) -> _Entry | None:
    entry_bar = bars.iloc[entry_row]
    entry_price = _market_price(float(entry_bar.open), side, True, config)
    notional = min(
        config.maximum_notional_usd,
        equity * config.margin_fraction * config.leverage,
    )
    quantity = _quantize_down(notional / entry_price, config.size_decimals)
    if quantity <= 0.0:
        return None
    entry_fee = quantity * entry_price * config.entry_fee_rate
    stop = _barrier(entry_price, config.stop_bps, side, favorable=False)
    target = _barrier(entry_price, config.target_bps, side, favorable=True)
    margin = quantity * entry_price / config.leverage
    liquidation = _liquidation(side, quantity, entry_price, margin, entry_fee, config)
    return _Entry(
        entry_row,
        pd.Timestamp(entry_bar.timestamp),
        entry_price,
        quantity,
        entry_fee,
        stop,
        target,
        liquidation,
    )


def _settle_trade(
    bars: pd.DataFrame,
    funding: tuple[SourceLiveShapeFunding, ...],
    signal: SourceLiveShapeSignal,
    entry: _Entry,
    exit_: _Exit,
    config: SourceLiveShapeConfig,
) -> SourceLiveShapeTrade:
    exit_time = pd.Timestamp(bars.iloc[exit_.row].timestamp)
    funding_cash = _funding_cashflow(
        funding,
        signal.side,
        entry.quantity,
        entry.price,
        entry.time,
        exit_time,
    )
    gross = _signed_pnl(signal.side, entry.quantity, entry.price, exit_.price)
    exit_fee = entry.quantity * exit_.price * exit_.fee_rate
    penalty = (
        entry.quantity * exit_.price * config.liquidation_penalty_rate
        if exit_.reason == "liquidation"
        else 0.0
    )
    net = gross - entry.fee - exit_fee - penalty + funding_cash
    gap = bars.iloc[entry.row : exit_.row + 1].source.ne("hl").any()
    return SourceLiveShapeTrade(
        signal.decision_time_utc,
        signal.side,
        entry.time.isoformat(),
        exit_time.isoformat(),
        entry.price,
        exit_.price,
        entry.quantity,
        entry.stop,
        entry.target,
        entry.liquidation,
        entry.fee,
        exit_fee,
        funding_cash,
        penalty,
        net,
        exit_.reason,
        bool(gap),
        exit_.ambiguous,
    )


def _find_exit(
    bars: pd.DataFrame,
    entry_row: int,
    side: SourceSide,
    stop: float,
    target: float,
    liquidation: float,
    config: SourceLiveShapeConfig,
) -> _Exit:
    entry_time = pd.Timestamp(bars.iloc[entry_row].timestamp)
    deadline = entry_time + pd.Timedelta(minutes=config.maximum_hold_minutes)
    for row_number in range(entry_row, len(bars)):
        row = bars.iloc[row_number]
        timestamp = pd.Timestamp(row.timestamp)
        if row_number > entry_row and timestamp >= deadline:
            price = _market_price(float(row.open), side, False, config)
            return _Exit(row_number, price, "maximum_hold", config.market_exit_fee_rate)
        liquidation_gap = _beyond(float(row.open), liquidation, side, adverse=True)
        if liquidation_gap:
            return _Exit(row_number, liquidation, "liquidation", 0.0)
        stop_hit = _touches(row, stop, side, favorable=False)
        target_hit = _touches(row, target, side, favorable=True, strict=True)
        if stop_hit:
            reference = _worse_stop_reference(float(row.open), stop, side)
            price = _market_price(reference, side, False, config)
            return _Exit(
                row_number, price, "stop", config.market_exit_fee_rate, target_hit
            )
        if target_hit:
            return _Exit(row_number, target, "target", config.target_fee_rate)
    last = len(bars) - 1
    price = _market_price(float(bars.iloc[last].close), side, False, config)
    return _Exit(last, price, "end_of_data", config.market_exit_fee_rate)


def _report(
    config: SourceLiveShapeConfig,
    signals: Sequence[SourceLiveShapeSignal],
    trades: list[SourceLiveShapeTrade],
    equity: float,
    maximum_drawdown: float,
    occupied: int,
    rejected: int,
    ambiguous: int,
) -> SourceLiveShapeReport:
    gains = sum(max(trade.net_pnl_usd, 0.0) for trade in trades)
    losses = -sum(min(trade.net_pnl_usd, 0.0) for trade in trades)
    reasons = [trade.exit_reason for trade in trades]
    return SourceLiveShapeReport(
        config.initial_equity,
        equity,
        len(signals),
        len(trades),
        sum(trade.net_pnl_usd > 0.0 for trade in trades),
        sum(trade.net_pnl_usd < 0.0 for trade in trades),
        reasons.count("target"),
        reasons.count("stop"),
        reasons.count("liquidation"),
        reasons.count("maximum_hold"),
        reasons.count("end_of_data"),
        occupied,
        rejected,
        ambiguous,
        sum(trade.gap_evidence_overlap for trade in trades),
        sum(trade.entry_fee_usd + trade.exit_fee_usd for trade in trades),
        sum(trade.funding_cashflow_usd for trade in trades),
        equity - config.initial_equity,
        gains / losses if losses > 0.0 else None,
        maximum_drawdown,
        "realized_trade_closes_only",
        tuple(trades),
        (
            "One-minute OHLC cannot identify intrabar path; stop wins a shared bar.",
            "Target requires strict bar trade-through and is credited at the maker limit.",
            "Fixed slippage cannot reproduce every live IOC fill.",
            "Funding notional uses entry price rather than historical hourly mark.",
            "Maximum drawdown is sampled only after resolved trade closes.",
            "An end-of-data lifecycle is force-marked and remains right-censored.",
            "Rows marked hl_gap_fill make overlapping lifecycles evidence-incomplete.",
        ),
    )


def _normalized_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_BAR_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"source live-shape bars missing columns: {missing}")
    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if "source" not in frame:
        frame["source"] = "unspecified"
    frame = frame.sort_values("timestamp", kind="stable").set_index(
        "timestamp", drop=False
    )
    if frame.index.has_duplicates:
        raise ValueError("source live-shape bars contain duplicate timestamps")
    if (
        len(frame) < 2
        or not frame.index.to_series().diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all()
    ):
        raise ValueError("source live-shape bars must be contiguous one-minute data")
    return frame


def _ordered_signals(
    signals: Sequence[SourceLiveShapeSignal],
) -> tuple[SourceLiveShapeSignal, ...]:
    ordered = tuple(sorted(signals, key=lambda signal: signal.decision_time))
    if len({signal.decision_time for signal in ordered}) != len(ordered):
        raise ValueError("source live-shape signals must have unique timestamps")
    return ordered


def _ordered_funding(
    funding: Sequence[SourceLiveShapeFunding],
) -> tuple[SourceLiveShapeFunding, ...]:
    ordered = tuple(sorted(funding, key=lambda value: value.timestamp))
    if len({value.timestamp for value in ordered}) != len(ordered):
        raise ValueError("source funding timestamps must be unique")
    return ordered


def _funding_cashflow(
    funding: Sequence[SourceLiveShapeFunding],
    side: SourceSide,
    quantity: float,
    entry_price: float,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
) -> float:
    signed = -1.0 if side == "long" else 1.0
    return sum(
        signed * quantity * entry_price * value.rate
        for value in funding
        if entry_time <= value.timestamp < exit_time
    )


def _liquidation(
    side: SourceSide,
    quantity: float,
    entry_price: float,
    margin: float,
    entry_fee: float,
    config: SourceLiveShapeConfig,
) -> float:
    return IsolatedMarginPosition(
        symbol="BTC",
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        isolated_margin=margin,
        maintenance_rate=maintenance_rate_for_max_leverage(config.venue_max_leverage),
        fees_paid_usd=entry_fee,
    ).liquidation_price()


def _market_price(
    reference: float,
    side: SourceSide,
    entry: bool,
    config: SourceLiveShapeConfig,
) -> float:
    buy = side == "long" if entry else side == "short"
    bps = config.entry_slippage_bps if entry else config.market_exit_slippage_bps
    return reference * (1.0 + bps / 10_000.0 if buy else 1.0 - bps / 10_000.0)


def _barrier(entry: float, bps: float, side: SourceSide, *, favorable: bool) -> float:
    upward = side == "long" if favorable else side == "short"
    return entry * (1.0 + bps / 10_000.0 if upward else 1.0 - bps / 10_000.0)


def _touches(
    row: object,
    price: float,
    side: SourceSide,
    *,
    favorable: bool,
    strict: bool = False,
) -> bool:
    upward = side == "long" if favorable else side == "short"
    observed = float(row.high if upward else row.low)
    return (
        observed > price
        if upward and strict
        else observed < price
        if strict
        else observed >= price
        if upward
        else observed <= price
    )


def _beyond(value: float, barrier: float, side: SourceSide, *, adverse: bool) -> bool:
    upward = side == "short" if adverse else side == "long"
    return value >= barrier if upward else value <= barrier


def _worse_stop_reference(open_price: float, stop: float, side: SourceSide) -> float:
    return min(open_price, stop) if side == "long" else max(open_price, stop)


def _signed_pnl(side: SourceSide, quantity: float, entry: float, exit_: float) -> float:
    sign = 1.0 if side == "long" else -1.0
    return sign * quantity * (exit_ - entry)


def _quantize_down(value: float, decimals: int) -> float:
    scale = 10**decimals
    return math.floor(value * scale) / scale
