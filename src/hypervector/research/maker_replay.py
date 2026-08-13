"""Causal post-only order-book replay for backend Hypervelocity decisions."""

from __future__ import annotations

import pandas as pd

from hypervector.research.maker_replay_context import (
    MakerReplayContext,
    apply_funding_event,
    apply_price_event,
    mark_for_book,
    remember_book,
)
from hypervector.research.maker_replay_contract import (
    MakerReplayPositionContract,
    maker_replay_contract,
)
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayReport,
    PendingEntry as _PendingEntry,
    ReplayState as _ReplayState,
)
from hypervector.research.maker_replay_lifecycle import (
    mark_open as _mark_open,
    resolve_pending as _resolve_pending,
)
from hypervector.research.maker_replay_orders import (
    entry_filled as _entry_filled,
    entry_limit_price as _entry_limit_price,
    exit_filled as _exit_filled,
    open_position as _open_position,
)
from hypervector.research.maker_replay_risk import (
    apply_book_entry_close_reverse,
    apply_book_liquidation,
    apply_book_regime_exit,
    apply_book_stop,
    apply_book_time_exit,
    complete_target,
    update_drawdown,
)
from hypervector.research.maker_replay_signals import (
    DecisionProjection,
    consume_liquidation_cooldown_signal,
    decision_projection,
    projected_market_at,
)
from hypervector.research.maker_replay_trades import replay_trade


def _submit_entry(
    state: _ReplayState,
    direction: Direction,
    signal_time: pd.Timestamp,
    timestamp: pd.Timestamp,
    limit_price: float,
    maximum_hold_seconds: float | None,
    stop_price: float | None,
    stop_margin_pct: float | None,
    allocation_multiplier: float,
) -> None:
    lifecycle_id = len(state.lifecycles)
    state.lifecycles.append(
        MakerReplayLifecycle(
            lifecycle_id,
            direction,
            signal_time.isoformat(),
            timestamp.isoformat(),
            None,
            None,
            "pending",
            None,
            None,
            None,
            None,
            None,
        )
    )
    state.pending = _PendingEntry(
        lifecycle_id,
        direction,
        signal_time,
        timestamp,
        limit_price,
        allocation_multiplier=allocation_multiplier,
        stop_price=stop_price,
        stop_margin_pct=stop_margin_pct,
        maximum_hold_seconds=maximum_hold_seconds,
    )
    state.last_signal = signal_time
    state.submitted += 1
    state.submissions.append(timestamp.isoformat())


def _rearm_consumed(
    state: _ReplayState,
    structural: Direction | None,
    timestamp: pd.Timestamp,
) -> None:
    if structural != state.structural_episode_direction:
        state.structural_episode_direction = structural
        state.structural_episode_started_at = timestamp
        state.target_completions_in_episode = 0
    if state.expired_direction is not None and structural != state.expired_direction:
        state.expired_direction = None
    if (
        state.completed_direction is not None
        and structural != state.completed_direction
    ):
        state.completed_direction = None
        state.completed_status = None
        state.completed_reference_price = None


def _cooldown_complete(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    config: MakerReplayConfig,
) -> bool:
    if state.last_exit_time is None:
        return True
    elapsed = (timestamp - state.last_exit_time).total_seconds()
    return elapsed >= config.reentry_cooldown_seconds


def _completed_direction_available(
    state: _ReplayState,
    desired: Direction,
    limit_price: float,
    timestamp: pd.Timestamp,
    signal_time: pd.Timestamp | None,
    reentry_event: Direction | None,
    config: MakerReplayConfig,
) -> bool:
    if desired != state.completed_direction:
        return True
    if config.same_direction_reentry_policy == "cooldown_only":
        return True
    if (
        config.same_direction_reentry_policy
        not in ("target_continuation", "target_pullback_transition")
        or state.completed_status != "target_completed"
    ):
        return False
    limit = config.target_continuation_limit_per_episode
    if limit is not None and state.target_completions_in_episode >= limit:
        return False
    started_at = state.structural_episode_started_at
    minimum = config.target_continuation_minimum_episode_seconds
    if started_at is None or (timestamp - started_at).total_seconds() < minimum:
        return False
    if config.same_direction_reentry_policy == "target_pullback_transition":
        if signal_time is None or state.last_exit_time is None:
            return False
        event_age = (signal_time - state.last_exit_time).total_seconds()
        return (
            reentry_event == desired
            and signal_time > state.last_exit_time
            and event_age >= config.reentry_cooldown_seconds
        )
    reference = state.completed_reference_price
    if reference is None:
        return False
    clearance = config.same_direction_reentry_clearance_bps / 10_000.0
    if desired == "long":
        return limit_price >= reference * (1.0 + clearance)
    return limit_price <= reference * (1.0 - clearance)


def _update_pending_from_book(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    structural: Direction | None,
    mark: float | None,
    config: MakerReplayConfig,
    contract: MakerReplayPositionContract,
) -> bool:
    pending = state.pending
    if pending is None:
        return False
    age = (timestamp - pending.submitted_time).total_seconds()
    if structural != pending.direction:
        _resolve_pending(state, pending, timestamp, "canceled")
        state.pending, state.canceled = None, state.canceled + 1
    elif age > config.entry_ttl_seconds:
        _resolve_pending(state, pending, timestamp, "expired")
        state.pending, state.expired = None, state.expired + 1
        state.expired_direction = pending.direction
    elif _entry_filled(pending, bid, ask, config):
        state.position = _open_position(
            pending, timestamp, state.equity, contract, config
        )
        state.equity -= state.position.entry_fee
        _mark_open(state, state.position)
        state.pending, state.entry_fills = None, state.entry_fills + 1
        if mark is not None:
            update_drawdown(state, mark)
        return True
    return False


def _submit_from_book(
    state: _ReplayState,
    desired: Direction | None,
    signal_time: pd.Timestamp | None,
    reentry_event: Direction | None,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    maximum_hold_seconds: float | None,
    stop_price: float | None,
    stop_margin_pct: float | None,
    allocation_multiplier: float,
    config: MakerReplayConfig,
    *,
    atomic_reverse: bool = False,
) -> None:
    if desired is None:
        return
    if consume_liquidation_cooldown_signal(
        state,
        desired,
        signal_time,
        timestamp,
        config,
    ):
        return
    limit_price = _entry_limit_price(desired, bid, ask, config)
    can_submit = (
        state.pending is None
        and state.position is None
        and (atomic_reverse or desired != state.expired_direction)
        and (
            atomic_reverse
            or _completed_direction_available(
                state,
                desired,
                limit_price,
                timestamp,
                signal_time,
                reentry_event,
                config,
            )
        )
        and (atomic_reverse or _cooldown_complete(state, timestamp, config))
    )
    if can_submit and signal_time is not None and signal_time != state.last_signal:
        cap = config.maximum_entry_spread_bps
        midpoint = (bid + ask) / 2.0
        spread_bps = 10_000.0 * (ask - bid) / midpoint
        if cap is not None and spread_bps > cap:
            state.last_signal = signal_time
            state.spread_rejected_entries += 1
            return
        _submit_entry(
            state,
            desired,
            signal_time,
            timestamp,
            limit_price,
            maximum_hold_seconds,
            stop_price,
            stop_margin_pct,
            allocation_multiplier,
        )


def _replay_snapshot(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    desired: Direction | None,
    structural: Direction | None,
    signal_time: pd.Timestamp | None,
    reentry_event: Direction | None,
    maximum_hold_seconds: float | None,
    stop_price: float | None,
    stop_margin_pct: float | None,
    allocation_multiplier: float,
    config: MakerReplayConfig,
    contract: MakerReplayPositionContract,
) -> None:
    remember_book(state, timestamp, bid, ask)
    mark = mark_for_book(state, timestamp, bid, ask, config)
    if _update_pending_from_book(
        state, timestamp, bid, ask, structural, mark, config, contract
    ):
        return
    if mark is not None and apply_book_liquidation(
        state, timestamp, bid, ask, config, trigger_mark=mark
    ):
        return
    if apply_book_entry_close_reverse(
        state, timestamp, bid, ask, desired, structural, signal_time, config
    ):
        _submit_from_book(
            state,
            desired,
            signal_time,
            reentry_event,
            timestamp,
            bid,
            ask,
            maximum_hold_seconds,
            stop_price,
            stop_margin_pct,
            allocation_multiplier,
            config,
            atomic_reverse=True,
        )
        return
    if apply_book_regime_exit(state, timestamp, bid, ask, structural, config):
        return
    if apply_book_time_exit(state, timestamp, bid, ask, config):
        return
    if apply_book_stop(state, timestamp, bid, ask, config):
        return
    if state.position is not None and _exit_filled(state.position, bid, ask, config):
        complete_target(state, timestamp, config.maker_fee_rate, (bid + ask) / 2.0)
        return
    _submit_from_book(
        state,
        desired,
        signal_time,
        reentry_event,
        timestamp,
        bid,
        ask,
        maximum_hold_seconds,
        stop_price,
        stop_margin_pct,
        allocation_multiplier,
        config,
    )
    if mark is not None:
        update_drawdown(state, mark)


def _apply_context_event(
    state: _ReplayState,
    row: object,
    timestamp: pd.Timestamp,
    event_kind: object,
    config: MakerReplayConfig,
) -> bool:
    if event_kind == "price":
        apply_price_event(
            state, timestamp, float(row.mark_price), float(row.oracle_price), config
        )
        return True
    if event_kind == "funding":
        apply_funding_event(state, timestamp, float(row.funding_rate), config)
        return True
    return False


def _occupied_structural_direction(
    state: _ReplayState,
    structural: Direction | None,
    signal_time: pd.Timestamp | None,
    config: MakerReplayConfig,
) -> Direction | None:
    """Consume but otherwise ignore new signals while portfolio state is occupied."""
    pending = state.pending
    position = state.position
    if config.occupied_signal_policy != "ignore" or (
        pending is None and position is None
    ):
        return structural
    if signal_time is not None and signal_time != state.last_signal:
        state.last_signal = signal_time
    return pending.direction if pending is not None else position.direction


def _execute_tape_event(
    state: _ReplayState,
    row: object,
    timestamp: pd.Timestamp,
    position: int,
    projection: DecisionProjection,
    config: MakerReplayConfig,
    contract: MakerReplayPositionContract,
) -> None:
    (
        desired,
        structural,
        signal_time,
        reentry_event,
        maximum_hold_seconds,
        stop_price,
        stop_margin_pct,
        allocation_multiplier,
    ) = projected_market_at(position, projection)
    structural = _occupied_structural_direction(
        state,
        structural,
        signal_time,
        config,
    )
    event_kind = getattr(row, "event_kind", "book")
    if _apply_context_event(state, row, timestamp, event_kind, config):
        return
    _rearm_consumed(state, structural, timestamp)
    if event_kind == "trade":
        replay_trade(
            state,
            timestamp,
            str(row.aggressor_side),
            float(row.price),
            float(row.size),
            structural,
            config,
            contract,
        )
    else:
        _replay_snapshot(
            state,
            timestamp,
            float(row.best_bid),
            float(row.best_ask),
            desired,
            structural,
            signal_time,
            reentry_event,
            maximum_hold_seconds,
            stop_price,
            stop_margin_pct,
            allocation_multiplier,
            config,
            contract,
        )


def _execute_tape(
    tape: pd.DataFrame,
    directions: pd.Series,
    structural_directions: pd.Series,
    reentry_events: pd.Series,
    maximum_holds: pd.Series,
    entry_stops: pd.Series,
    entry_stop_margin_pcts: pd.Series,
    allocation_multipliers: pd.Series,
    config: MakerReplayConfig,
    state: _ReplayState | None = None,
) -> _ReplayState:
    active = state or _ReplayState(equity=config.initial_equity)
    active.peak_equity = max(active.peak_equity, config.initial_equity)
    contract = maker_replay_contract(config)
    timestamps = pd.to_datetime(tape["ts_ms"], unit="ms", utc=True)
    positions = directions.index.searchsorted(timestamps, side="right") - 1
    projection = decision_projection(
        directions,
        structural_directions,
        reentry_events,
        maximum_holds,
        entry_stops,
        entry_stop_margin_pcts,
        allocation_multipliers,
    )
    for row, timestamp, position in zip(
        tape.itertuples(index=False), timestamps, positions, strict=True
    ):
        _execute_tape_event(
            active, row, timestamp, int(position), projection, config, contract
        )
    return active


def replay_maker_orders(
    book: pd.DataFrame,
    decisions: pd.DataFrame,
    config: MakerReplayConfig | None = None,
    *,
    trades: pd.DataFrame | None = None,
    context: MakerReplayContext | None = None,
) -> MakerReplayReport:
    """Replay post-only entries and fixed targets from causal market evidence."""
    from hypervector.research.maker_replay_stream import (
        MakerReplayEvidenceChunk,
        replay_maker_order_chunks,
    )

    return replay_maker_order_chunks(
        (MakerReplayEvidenceChunk(book, trades),),
        decisions,
        config,
        context=context,
    )
