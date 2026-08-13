"""One-minute-path replay for one frozen low-timeframe strategy cell."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from hypervector.research.low_tf_multi_asset_replay_models import (
    LowTfExitReason,
    LowTfReplayConfig,
    LowTfReplayRejection,
    LowTfReplayReport,
    LowTfReplayTrade,
)
from hypervector.research.low_tf_multi_asset_replay_exits import (
    dynamic_low_tf_exit,
)
from hypervector.research.low_tf_multi_asset_replay_risk import (
    adverse_low_tf_price,
    low_tf_liquidation_price,
    low_tf_stop_is_adverse,
    low_tf_target_is_favorable,
)
from hypervector.research.low_tf_multi_asset_replay_reporting import (
    build_low_tf_replay_report,
)
from hypervector.research.shared_portfolio_models import Direction

_MINUTE_COLUMNS = {"timestamp", "open", "high", "low", "close", "funding_rate"}
_FEATURE_COLUMNS = {
    "bar_open_at",
    "close",
    "ema_fast_5m",
    "ema_slow_5m",
    "rsi",
    "rsi_signal",
    "pmarp",
}
_SIGNAL_COLUMNS = {
    "decision_time_utc",
    "symbol",
    "family",
    "side",
    "exit_variant",
    "stop_anchor_price",
    "target_anchor_price",
    "invalidation_mode",
    "max_hold_bars",
    "execution_authority",
}


@dataclass(frozen=True)
class _Candidate:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    symbol: str
    family: str
    direction: Direction
    exit_variant: str
    stop_anchor: float
    target_anchor: float | None
    invalidation_mode: str
    maximum_hold_bars: int


@dataclass
class _OpenPosition:
    candidate: _Candidate
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    target_price: float | None
    quantity: float
    risk_budget: float
    isolated_margin: float
    entry_fee: float
    equity_before: float
    initial_liquidation_price: float
    funding_cashflow: float = 0.0
    pending_exit: LowTfExitReason | None = None


@dataclass
class _State:
    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    position: _OpenPosition | None = None
    next_entry_eligible_at: pd.Timestamp | None = None
    trades: list[LowTfReplayTrade] = field(default_factory=list)
    rejections: list[LowTfReplayRejection] = field(default_factory=list)


def evaluate_low_tf_replay(
    minute_bars: pd.DataFrame,
    features: pd.DataFrame,
    signals: pd.DataFrame,
    config: LowTfReplayConfig | None = None,
) -> LowTfReplayReport:
    """Replay exactly one strategy cell through a causal one-minute price path."""
    cfg = config or LowTfReplayConfig()
    minutes = _validated_minutes(minute_bars)
    decision_features = _validated_features(features)
    scheduled, initial_rejections = _scheduled_candidates(minutes, signals)
    state = _State(cfg.initial_equity, cfg.initial_equity)
    state.rejections.extend(initial_rejections)
    completions = _feature_completions(decision_features)
    for timestamp, bar in minutes.iterrows():
        _execute_open_exit(state, timestamp, bar, cfg)
        _execute_maximum_hold(state, timestamp, bar, cfg)
        _fill_candidates(state, scheduled.get(timestamp, ()), bar, cfg)
        _settle_funding(state, bar)
        _process_minute_bar(state, timestamp, bar, cfg)
        _update_marked_drawdown(state, bar)
        completion = timestamp + pd.Timedelta(minutes=1)
        if completion in completions and state.position is not None:
            current, prior = completions[completion]
            _schedule_dynamic_exit(state.position, current, prior)
    _force_end_close(state, minutes, cfg)
    return build_low_tf_replay_report(
        initial_equity=cfg.initial_equity,
        final_equity=state.equity,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        trades=state.trades,
        rejections=state.rejections,
    )


def _validated_minutes(bars: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_MINUTE_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError(f"low-timeframe minute bars missing columns: {missing}")
    times = pd.DatetimeIndex(bars["timestamp"])
    if bars.empty or times.tz is None or times.has_duplicates:
        raise ValueError("minute bars require non-empty unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("minute bars must be ordered")
    prices = bars[["open", "high", "low", "close"]].to_numpy(float)
    funding = bars["funding_rate"].to_numpy(float)
    if not np.isfinite(prices).all() or (prices <= 0.0).any():
        raise ValueError("minute prices must be positive and finite")
    if not np.isfinite(funding).all():
        raise ValueError("minute funding must be finite")
    return bars.set_index("timestamp").copy()


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_FEATURE_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"replay features missing columns: {missing}")
    times = pd.DatetimeIndex(features["bar_open_at"])
    if features.empty or times.tz is None or times.has_duplicates:
        raise ValueError("replay features require unique aware timestamps")
    if not times.is_monotonic_increasing:
        raise ValueError("replay features must be ordered")
    numeric = features[list(_FEATURE_COLUMNS - {"bar_open_at"})].to_numpy(float)
    if np.isinf(numeric).any():
        raise ValueError("replay features cannot contain infinity")
    return features.copy().reset_index(drop=True)


def _scheduled_candidates(
    minutes: pd.DataFrame, signals: pd.DataFrame
) -> tuple[dict[pd.Timestamp, tuple[_Candidate, ...]], list[LowTfReplayRejection]]:
    missing = sorted(_SIGNAL_COLUMNS.difference(signals.columns))
    if missing:
        raise ValueError(f"replay signals missing columns: {missing}")
    identity = signals[["symbol", "family", "side", "exit_variant"]].drop_duplicates()
    if signals.empty or len(identity) != 1:
        raise ValueError("low-timeframe replay requires exactly one strategy cell")
    scheduled: dict[pd.Timestamp, list[_Candidate]] = {}
    rejected: list[LowTfReplayRejection] = []
    for _, row in signals.iterrows():
        candidate = _candidate(row)
        reason = _candidate_reason(candidate, minutes)
        if reason is None:
            scheduled.setdefault(candidate.entry_time, []).append(candidate)
        else:
            rejected.append(_rejection(candidate, reason))
    frozen = {time: tuple(values) for time, values in scheduled.items()}
    return frozen, rejected


def _candidate(row: pd.Series) -> _Candidate:
    signal_time = pd.Timestamp(row["decision_time_utc"])
    if signal_time.tz is None:
        raise ValueError("signal decision time must be timezone-aware")
    side = str(row["side"])
    if side not in {"long", "short"}:
        raise ValueError("signal side must be long or short")
    if str(row["execution_authority"]) != "none":
        raise ValueError("research replay signals must have no execution authority")
    target_value = float(row["target_anchor_price"])
    target = target_value if math.isfinite(target_value) else None
    maximum_hold = int(row["max_hold_bars"])
    return _Candidate(
        signal_time,
        signal_time,
        str(row["symbol"]),
        str(row["family"]),
        side,
        str(row["exit_variant"]),
        float(row["stop_anchor_price"]),
        target,
        str(row["invalidation_mode"]),
        maximum_hold,
    )


def _candidate_reason(candidate: _Candidate, minutes: pd.DataFrame) -> str | None:
    if candidate.entry_time not in minutes.index:
        return "next_five_minute_open_unavailable"
    if not math.isfinite(candidate.stop_anchor) or candidate.stop_anchor <= 0.0:
        return "invalid_stop_anchor"
    if candidate.maximum_hold_bars <= 0:
        return "invalid_maximum_hold"
    if candidate.invalidation_mode not in {"intrabar_stop", "completed_bar_close"}:
        return "invalid_invalidation_mode"
    return None


def _fill_candidates(
    state: _State,
    candidates: tuple[_Candidate, ...],
    bar: pd.Series,
    config: LowTfReplayConfig,
) -> None:
    for candidate in candidates:
        if state.position is not None:
            state.rejections.append(_rejection(candidate, "symbol_position_open"))
            continue
        if (
            state.next_entry_eligible_at is not None
            and candidate.entry_time < state.next_entry_eligible_at
        ):
            state.rejections.append(_rejection(candidate, "reentry_cooldown"))
            continue
        opened, reason = _open_candidate(state, candidate, float(bar["open"]), config)
        if reason is not None:
            state.rejections.append(_rejection(candidate, reason))
            continue
        state.position = opened


def _open_candidate(
    state: _State,
    candidate: _Candidate,
    raw_open: float,
    config: LowTfReplayConfig,
) -> tuple[_OpenPosition | None, str | None]:
    entry = adverse_low_tf_price(
        raw_open, candidate.direction, config.slippage_bps_per_side, entering=True
    )
    stop = candidate.stop_anchor
    if not low_tf_stop_is_adverse(candidate.direction, stop, entry):
        return None, "stop_anchor_crossed_at_entry"
    if candidate.target_anchor is not None and not low_tf_target_is_favorable(
        candidate.direction, candidate.target_anchor, entry
    ):
        return None, "target_anchor_crossed_at_entry"
    desired_risk = state.equity * config.risk_fraction
    stop_distance = abs(entry - stop)
    desired_quantity = desired_risk / stop_distance
    maximum_quantity = (
        state.equity * config.maximum_margin_fraction * config.leverage / entry
    )
    quantity = min(desired_quantity, maximum_quantity)
    risk = quantity * stop_distance
    margin = quantity * entry / config.leverage
    fee = quantity * entry * config.fee_rate_per_side
    opened = _OpenPosition(
        candidate,
        candidate.entry_time,
        entry,
        stop,
        candidate.target_anchor,
        quantity,
        risk,
        margin,
        fee,
        state.equity,
        0.0,
    )
    opened.initial_liquidation_price = _liquidation_price(opened, config)
    state.equity -= fee
    _update_drawdown(state, state.equity)
    return opened, None


def _execute_open_exit(
    state: _State,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    config: LowTfReplayConfig,
) -> None:
    opened = state.position
    if opened is None or opened.pending_exit is None:
        return
    reason = opened.pending_exit
    price = adverse_low_tf_price(
        float(bar["open"]),
        opened.candidate.direction,
        config.slippage_bps_per_side,
        entering=False,
    )
    _close(state, timestamp, price, reason, False, config)


def _execute_maximum_hold(
    state: _State,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    config: LowTfReplayConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    deadline = opened.entry_time + pd.Timedelta(
        minutes=5 * opened.candidate.maximum_hold_bars
    )
    if timestamp < deadline:
        return
    price = adverse_low_tf_price(
        float(bar["open"]),
        opened.candidate.direction,
        config.slippage_bps_per_side,
        entering=False,
    )
    _close(state, timestamp, price, "max_hold", False, config)


def _settle_funding(state: _State, bar: pd.Series) -> None:
    opened = state.position
    rate = float(bar["funding_rate"])
    if opened is None or rate == 0.0:
        return
    sign = 1.0 if opened.candidate.direction == "long" else -1.0
    cashflow = -sign * opened.quantity * float(bar["open"]) * rate
    opened.funding_cashflow += cashflow
    state.equity += cashflow
    _update_drawdown(state, state.equity)


def _process_minute_bar(
    state: _State,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    config: LowTfReplayConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    liquidation = _liquidation_price(opened, config)
    hits = _barrier_hits(opened, bar, liquidation)
    reasons: tuple[LowTfExitReason, ...] = ("liquidation", "stop", "target")
    reason = next((value for value in reasons if hits[value]), None)
    if reason is None:
        return
    raw_price = _barrier_price(opened, bar, liquidation, reason)
    price = adverse_low_tf_price(
        raw_price,
        opened.candidate.direction,
        config.slippage_bps_per_side,
        entering=False,
    )
    _close(state, timestamp, price, reason, sum(hits.values()) > 1, config)


def _barrier_hits(
    opened: _OpenPosition, bar: pd.Series, liquidation: float
) -> dict[LowTfExitReason, bool]:
    low, high = float(bar["low"]), float(bar["high"])
    long = opened.candidate.direction == "long"
    hard_stop = opened.candidate.invalidation_mode == "intrabar_stop"
    return {
        "liquidation": low <= liquidation if long else high >= liquidation,
        "stop": hard_stop
        and (low <= opened.stop_price if long else high >= opened.stop_price),
        "target": opened.target_price is not None
        and (high >= opened.target_price if long else low <= opened.target_price),
    }


def _barrier_price(
    opened: _OpenPosition,
    bar: pd.Series,
    liquidation: float,
    reason: LowTfExitReason,
) -> float:
    barrier = liquidation if reason == "liquidation" else opened.stop_price
    if reason == "target" and opened.target_price is not None:
        return opened.target_price
    bar_open = float(bar["open"])
    if opened.candidate.direction == "long":
        return min(barrier, bar_open)
    return max(barrier, bar_open)


def _feature_completions(
    features: pd.DataFrame,
) -> dict[pd.Timestamp, tuple[pd.Series, pd.Series | None]]:
    completions: dict[pd.Timestamp, tuple[pd.Series, pd.Series | None]] = {}
    prior: pd.Series | None = None
    for _, row in features.iterrows():
        time = pd.Timestamp(row["bar_open_at"]) + pd.Timedelta(minutes=5)
        completions[time] = row, prior
        prior = row
    return completions


def _schedule_dynamic_exit(
    opened: _OpenPosition, row: pd.Series, prior: pd.Series | None
) -> None:
    opened.pending_exit = dynamic_low_tf_exit(
        variant=opened.candidate.exit_variant,
        direction=opened.candidate.direction,
        stop_price=opened.stop_price,
        row=row,
        prior=prior,
    )


def _liquidation_price(opened: _OpenPosition, config: LowTfReplayConfig) -> float:
    return low_tf_liquidation_price(
        symbol=opened.candidate.symbol,
        direction=opened.candidate.direction,
        quantity=opened.quantity,
        entry_price=opened.entry_price,
        isolated_margin=opened.isolated_margin,
        entry_fee=opened.entry_fee,
        funding_cashflow=opened.funding_cashflow,
        venue_max_leverage=config.venue_max_leverage,
    )


def _close(
    state: _State,
    timestamp: pd.Timestamp,
    exit_price: float,
    reason: LowTfExitReason,
    ambiguous: bool,
    config: LowTfReplayConfig,
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("cannot close a missing low-timeframe position")
    sign = 1.0 if opened.candidate.direction == "long" else -1.0
    gross = sign * opened.quantity * (exit_price - opened.entry_price)
    exit_fee = opened.quantity * exit_price * config.fee_rate_per_side
    penalty = (
        opened.quantity * exit_price * config.liquidation_penalty_rate
        if reason == "liquidation"
        else 0.0
    )
    state.equity += gross - exit_fee - penalty
    state.trades.append(
        _trade(
            opened,
            timestamp,
            exit_price,
            gross,
            exit_fee,
            penalty,
            reason,
            ambiguous,
            state.equity,
        )
    )
    state.position = None
    state.next_entry_eligible_at = timestamp + pd.Timedelta(
        minutes=5 * config.reentry_cooldown_bars
    )
    _update_drawdown(state, state.equity)


def _trade(
    opened: _OpenPosition,
    timestamp: pd.Timestamp,
    exit_price: float,
    gross: float,
    exit_fee: float,
    penalty: float,
    reason: LowTfExitReason,
    ambiguous: bool,
    equity_after: float,
) -> LowTfReplayTrade:
    fees = opened.entry_fee + exit_fee
    net = gross - fees + opened.funding_cashflow - penalty
    return LowTfReplayTrade(
        opened.candidate.symbol,
        opened.candidate.family,
        opened.candidate.exit_variant,
        opened.candidate.direction,
        opened.candidate.signal_time.isoformat(),
        opened.entry_time.isoformat(),
        timestamp.isoformat(),
        opened.entry_price,
        exit_price,
        opened.stop_price,
        opened.target_price,
        opened.initial_liquidation_price,
        opened.quantity,
        opened.risk_budget,
        opened.isolated_margin,
        gross,
        opened.entry_fee,
        exit_fee,
        fees,
        opened.funding_cashflow,
        penalty,
        net,
        opened.equity_before,
        equity_after,
        reason,
        ambiguous,
    )


def _force_end_close(
    state: _State, minutes: pd.DataFrame, config: LowTfReplayConfig
) -> None:
    if state.position is None:
        return
    timestamp = pd.Timestamp(minutes.index[-1])
    raw = float(minutes.iloc[-1]["close"])
    price = adverse_low_tf_price(
        raw,
        state.position.candidate.direction,
        config.slippage_bps_per_side,
        entering=False,
    )
    _close(state, timestamp, price, "end_of_data", False, config)


def _update_marked_drawdown(state: _State, bar: pd.Series) -> None:
    marked = state.equity
    if state.position is not None:
        opened = state.position
        mark = float(
            bar["low"] if opened.candidate.direction == "long" else bar["high"]
        )
        sign = 1.0 if opened.candidate.direction == "long" else -1.0
        marked += sign * opened.quantity * (mark - opened.entry_price)
    _update_drawdown(state, marked)


def _update_drawdown(state: _State, marked_equity: float) -> None:
    state.peak_equity = max(state.peak_equity, marked_equity)
    if state.peak_equity <= 0.0:
        return
    drawdown = 100.0 * (state.peak_equity - marked_equity) / state.peak_equity
    state.maximum_drawdown_pct = max(state.maximum_drawdown_pct, drawdown)


def _rejection(candidate: _Candidate, reason: str) -> LowTfReplayRejection:
    return LowTfReplayRejection(
        candidate.signal_time.isoformat(),
        candidate.symbol,
        candidate.family,
        candidate.exit_variant,
        reason,
    )
