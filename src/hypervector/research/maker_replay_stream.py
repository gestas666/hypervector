"""Bounded-memory chunk adapter for causal Hypervelocity maker replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.maker_replay import (
    MakerReplayConfig,
    MakerReplayReport,
    _ReplayState,
    _execute_tape,
)
from hypervector.research.maker_replay_context import (
    MakerReplayContext,
    build_event_tape,
    enable_authentic_context,
)
from hypervector.research.maker_replay_signals import (
    available_directions,
    available_entry_allocation_multipliers,
    available_entry_stop_margin_pcts,
    available_entry_stops,
    available_maximum_holds,
    available_reentry_events,
    available_structural_directions,
)
from hypervector.research.maker_replay_validation import (
    validate_book,
    validate_trades,
)

_DecisionStreams = tuple[
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
    pd.Series,
]


@dataclass(frozen=True)
class MakerReplayEvidenceChunk:
    """One chronological evidence chunk for bounded-memory replay."""

    book: pd.DataFrame | None
    trades: pd.DataFrame | None = None
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None


def archive_evidence_chunks(
    bundles: Iterable[OxaArchiveBundle],
    *,
    include_trades: bool,
) -> Iterable[MakerReplayEvidenceChunk]:
    """Load one verified archive bundle at a time for bounded replay."""
    from hypervector.data.book_align import load_l2_jsonl
    from hypervector.data.oxa_trades import load_trade_jsonl

    for bundle in bundles:
        book = load_l2_jsonl(bundle.book_path) if bundle.book_path else None
        trades = None
        if include_trades and bundle.trade_path is not None:
            trades = load_trade_jsonl(bundle.trade_path)
        yield MakerReplayEvidenceChunk(
            book,
            trades,
            pd.Timestamp(bundle.start),
            pd.Timestamp(bundle.end),
        )


def _empty_book() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_ms", "best_bid", "best_ask"])


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["ts_ms", "trade_id", "aggressor_side", "price", "size"]
    )


def _book_chunk(
    book: pd.DataFrame | None,
    previous: tuple[float, float, float] | None,
) -> tuple[pd.DataFrame, tuple[float, float, float] | None]:
    frame = _empty_book() if book is None or book.empty else validate_book(book)
    if frame.empty:
        return frame, previous
    first = tuple(float(frame.iloc[0][name]) for name in frame.columns)
    if previous is not None and first[0] < previous[0]:
        raise ValueError("book chunk timestamp regression")
    if previous is not None and first[0] == previous[0]:
        if first != previous:
            raise ValueError("conflicting book chunk boundary")
        frame = frame.iloc[1:].reset_index(drop=True)
    if frame.empty:
        return frame, previous
    last = tuple(float(frame.iloc[-1][name]) for name in frame.columns)
    return frame, last


def _trade_chunk(
    trades: pd.DataFrame | None,
    previous: dict[object, tuple[object, ...]],
    previous_max_ts: float | None,
) -> tuple[pd.DataFrame, dict[object, tuple[object, ...]], float | None]:
    frame = (
        _empty_trades() if trades is None or trades.empty else validate_trades(trades)
    )
    if frame.empty:
        return frame, previous, previous_max_ts
    fields = tuple(frame.columns)
    trade_id_index = fields.index("trade_id")
    drop: list[int] = []
    for index, current in enumerate(frame.itertuples(index=False, name=None)):
        trade_id = current[trade_id_index]
        if trade_id in previous:
            if current != previous[trade_id]:
                raise ValueError("conflicting trade chunk boundary")
            drop.append(index)
    frame = frame.drop(index=drop).reset_index(drop=True)
    if frame.empty:
        return frame, previous, previous_max_ts
    if previous_max_ts is not None and float(frame.iloc[0]["ts_ms"]) < previous_max_ts:
        raise ValueError("trade chunk timestamp regression")
    identities = {
        row[trade_id_index]: row for row in frame.itertuples(index=False, name=None)
    }
    return frame, identities, float(frame.iloc[-1]["ts_ms"])


def _report_limitations(
    state: _ReplayState, config: MakerReplayConfig
) -> tuple[str, ...]:
    limitation = (
        "trade-through requires cumulative volume beyond limits but cannot observe queue rank"
        if config.fill_rule == "trade-through"
        else "book-only fill rules do not observe executed trade prints"
    )
    context_limitations = (
        (
            "liquidation uses causal Hyperliquid mark with last observed BBO execution",
            "official hourly funding uses backward-known oracle notional",
        )
        if state.authentic_context_enabled
        else (
            "liquidation uses midpoint as mark proxy and BBO execution without depth",
            "historical funding is not applied",
        )
    )
    gap_limitations: list[str] = []
    if state.empty_book_evidence_windows:
        gap_limitations.append(
            "empty L2 evidence windows make execution economics inconclusive"
        )
    if state.missing_mark_events or state.stale_mark_events:
        gap_limitations.append(
            "missing or stale mark observations while positions were open make "
            "liquidation and drawdown inconclusive"
        )
    if state.missing_oracle_settlements or state.stale_oracle_settlements:
        gap_limitations.append(
            "missing or stale oracle observations make funding cashflow inconclusive"
        )
    peak_limitations = (
        ("peak protection observes archived mark cadence rather than live 5s polling",)
        if config.peak_protection_activation_margin_pct is not None
        else ()
    )
    return (
        limitation,
        "queue position, cancellations, and partial maker fills are unknown",
        "touch and book-through remain assumption challengers, not guarantees",
        *context_limitations,
        *tuple(gap_limitations),
        *peak_limitations,
    )


def _build_report(
    state: _ReplayState,
    config: MakerReplayConfig,
    snapshots: int,
    trade_prints: int,
) -> MakerReplayReport:
    final_equity = (
        state.equity if state.last_marked_equity is None else state.last_marked_equity
    )
    return MakerReplayReport(
        config.fill_rule,
        snapshots,
        trade_prints,
        state.submitted,
        state.entry_fills,
        state.expired,
        state.canceled,
        int(state.pending is not None),
        len(state.trades),
        int(state.position is not None),
        config.initial_equity,
        final_equity,
        tuple(state.submissions),
        tuple(state.trades),
        tuple(state.lifecycles),
        _report_limitations(state, config),
        liquidations=state.liquidations,
        partial_liquidations=state.partial_liquidations,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        realized_equity=state.equity,
        liquidation_model=(
            "hyperliquid_mark_bbo_execution_v1"
            if state.authentic_context_enabled
            else "bbo_mark_proxy_partial_liquidation_v1"
        ),
        stops=state.stops,
        time_exits=state.time_exits,
        regime_exits=state.regime_exits,
        close_reversals=state.close_reversals,
        authentic_price_updates=state.authentic_price_updates,
        missing_mark_events=state.missing_mark_events,
        stale_mark_events=state.stale_mark_events,
        funding_settlements=state.funding_settlements,
        funding_cashflow=state.funding_cashflow,
        funding_paid=state.funding_paid,
        funding_received=state.funding_received,
        missing_oracle_settlements=state.missing_oracle_settlements,
        stale_oracle_settlements=state.stale_oracle_settlements,
        empty_book_evidence_windows=state.empty_book_evidence_windows,
        active_book_gap_windows=state.active_book_gap_windows,
        execution_economics_conclusive=state.execution_economics_conclusive,
        first_book_gap_start_utc=state.first_book_gap_start_utc,
        spread_rejected_entries=state.spread_rejected_entries,
        peak_protection_arms=state.peak_protection_arms,
        peak_protection_updates=state.peak_protection_updates,
        peak_protection_exits=state.peak_protection_exits,
    )


def _record_empty_book_evidence(
    states: Mapping[str, _ReplayState], chunk: MakerReplayEvidenceChunk
) -> None:
    if chunk.book is not None and not chunk.book.empty:
        return
    gap_start = None if chunk.start is None else pd.Timestamp(chunk.start).isoformat()
    for state in states.values():
        state.empty_book_evidence_windows += 1
        state.execution_economics_conclusive = False
        if state.first_book_gap_start_utc is None and gap_start is not None:
            state.first_book_gap_start_utc = gap_start
        if state.pending is not None or state.position is not None:
            state.active_book_gap_windows += 1


def replay_maker_order_chunks(
    chunks: Iterable[MakerReplayEvidenceChunk],
    decisions: pd.DataFrame,
    config: MakerReplayConfig | None = None,
    *,
    context: MakerReplayContext | None = None,
) -> MakerReplayReport:
    """Replay chronological evidence chunks without resetting portfolio state."""
    cfg = config or MakerReplayConfig()
    return replay_maker_order_grid_chunks(
        chunks,
        decisions,
        {"candidate": cfg},
        context=context,
    )["candidate"]


def _validated_grid_configs(
    configs: Mapping[str, MakerReplayConfig],
) -> tuple[dict[str, MakerReplayConfig], str]:
    if not configs:
        raise ValueError("maker replay grid requires at least one candidate")
    if any(not name.strip() for name in configs):
        raise ValueError("maker replay grid candidate names must be non-empty")
    result = dict(configs)
    fill_rules = {config.fill_rule for config in result.values()}
    if len(fill_rules) != 1:
        raise ValueError("maker replay grid candidates require one shared fill_rule")
    return result, next(iter(fill_rules))


def _initial_grid_states(
    configs: Mapping[str, MakerReplayConfig],
    context: MakerReplayContext | None,
) -> dict[str, _ReplayState]:
    states = {
        name: _ReplayState(equity=config.initial_equity)
        for name, config in configs.items()
    }
    if context is not None:
        for state in states.values():
            enable_authentic_context(state)
    return states


def replay_maker_order_grid_chunks(
    chunks: Iterable[MakerReplayEvidenceChunk],
    decisions: pd.DataFrame,
    configs: Mapping[str, MakerReplayConfig],
    *,
    context: MakerReplayContext | None = None,
) -> dict[str, MakerReplayReport]:
    """Replay named candidates over one validated chronological event tape."""
    decision_grid = {name: decisions for name in configs}
    return replay_maker_order_decision_grid_chunks(
        chunks,
        decision_grid,
        configs,
        context=context,
    )


def _validated_decision_grid(
    decision_grid: Mapping[str, pd.DataFrame],
    configs: Mapping[str, MakerReplayConfig],
) -> dict[str, _DecisionStreams]:
    if set(decision_grid) != set(configs):
        raise ValueError("decision and config candidate names must match")
    result: dict[str, _DecisionStreams] = {}
    for name, decisions in decision_grid.items():
        index = decisions.index
        valid = isinstance(index, pd.DatetimeIndex) and index.tz is not None
        valid &= index.is_unique and index.is_monotonic_increasing
        if not valid:
            raise ValueError(
                "candidate decisions require a unique, chronological, "
                "and timezone-aware DatetimeIndex"
            )
        result[name] = (
            available_directions(decisions),
            available_structural_directions(decisions),
            (
                available_reentry_events(decisions)
                if configs[name].same_direction_reentry_policy
                == "target_pullback_transition"
                else pd.Series(
                    None,
                    index=available_directions(decisions).index,
                    dtype=object,
                )
            ),
            available_maximum_holds(decisions),
            available_entry_stops(decisions),
            available_entry_stop_margin_pcts(decisions),
            available_entry_allocation_multipliers(decisions),
        )
    return result


def _execute_grid_tape(
    tape: pd.DataFrame,
    states: dict[str, _ReplayState],
    streams: Mapping[str, _DecisionStreams],
    configs: Mapping[str, MakerReplayConfig],
) -> None:
    for name, config in configs.items():
        (
            directions,
            structural,
            reentry_events,
            maximum_holds,
            entry_stops,
            entry_stop_margin_pcts,
            allocation_multipliers,
        ) = streams[name]
        states[name] = _execute_tape(
            tape,
            directions,
            structural,
            reentry_events,
            maximum_holds,
            entry_stops,
            entry_stop_margin_pcts,
            allocation_multipliers,
            config,
            states[name],
        )


def replay_maker_order_decision_grid_chunks(
    chunks: Iterable[MakerReplayEvidenceChunk],
    decision_grid: Mapping[str, pd.DataFrame],
    configs: Mapping[str, MakerReplayConfig],
    *,
    context: MakerReplayContext | None = None,
) -> dict[str, MakerReplayReport]:
    """Replay candidate-specific decisions over one chronological event tape."""
    candidates, fill_rule = _validated_grid_configs(configs)
    streams = _validated_decision_grid(decision_grid, candidates)
    states = _initial_grid_states(candidates, context)
    previous_book: tuple[float, float, float] | None = None
    previous_trades: dict[object, tuple[object, ...]] = {}
    previous_trade_ts: float | None = None
    snapshot_count = 0
    trade_count = 0
    for chunk in chunks:
        _record_empty_book_evidence(states, chunk)
        books, previous_book = _book_chunk(chunk.book, previous_book)
        trades = _empty_trades()
        if fill_rule == "trade-through":
            trades, previous_trades, previous_trade_ts = _trade_chunk(
                chunk.trades, previous_trades, previous_trade_ts
            )
        prices, funding = _context_window(context, chunk)
        tape = build_event_tape(books, trades, prices, funding)
        _execute_grid_tape(tape, states, streams, candidates)
        snapshot_count += len(books)
        trade_count += len(trades)
    has_decisions = any(not stream[0].empty for stream in streams.values())
    if fill_rule == "trade-through" and has_decisions and trade_count == 0:
        raise ValueError("trade-through replay requires public trade prints")
    return {
        name: _build_report(states[name], config, snapshot_count, trade_count)
        for name, config in candidates.items()
    }


def _context_window(
    context: MakerReplayContext | None,
    chunk: MakerReplayEvidenceChunk,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    if context is None:
        return None, None
    if chunk.start is None or chunk.end is None:
        return context.prices, context.funding
    return context.window(chunk.start, chunk.end)
