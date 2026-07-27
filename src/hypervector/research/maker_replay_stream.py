"""Bounded-memory chunk adapter for causal Hypervelocity maker replay."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.maker_replay import (
    MakerReplayConfig,
    MakerReplayReport,
    _ReplayState,
    _available_directions,
    _event_tape,
    _execute_tape,
)
from hypervector.research.maker_replay_validation import (
    validate_book,
    validate_trades,
)


@dataclass(frozen=True)
class MakerReplayEvidenceChunk:
    """One chronological evidence chunk for bounded-memory replay."""

    book: pd.DataFrame | None
    trades: pd.DataFrame | None = None


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
        yield MakerReplayEvidenceChunk(book, trades)


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


def _build_report(
    state: _ReplayState,
    config: MakerReplayConfig,
    snapshots: int,
    trade_prints: int,
) -> MakerReplayReport:
    limitation = (
        "trade-through requires cumulative volume beyond limits but cannot observe queue rank"
        if config.fill_rule == "trade-through"
        else "book-only fill rules do not observe executed trade prints"
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
        state.equity,
        tuple(state.submissions),
        tuple(state.trades),
        tuple(state.lifecycles),
        (
            limitation,
            "queue position, cancellations, and partial maker fills are unknown",
            "touch and book-through remain assumption challengers, not guarantees",
        ),
    )


def replay_maker_order_chunks(
    chunks: Iterable[MakerReplayEvidenceChunk],
    decisions: pd.DataFrame,
    config: MakerReplayConfig | None = None,
) -> MakerReplayReport:
    """Replay chronological evidence chunks without resetting portfolio state."""
    cfg = config or MakerReplayConfig()
    directions = _available_directions(decisions)
    state = _ReplayState(equity=cfg.initial_equity)
    previous_book: tuple[float, float, float] | None = None
    previous_trades: dict[object, tuple[object, ...]] = {}
    previous_trade_ts: float | None = None
    snapshot_count = 0
    trade_count = 0
    for chunk in chunks:
        books, previous_book = _book_chunk(chunk.book, previous_book)
        trades = _empty_trades()
        if cfg.fill_rule == "trade-through":
            trades, previous_trades, previous_trade_ts = _trade_chunk(
                chunk.trades, previous_trades, previous_trade_ts
            )
        tape = _event_tape(books, trades) if cfg.fill_rule == "trade-through" else books
        state = _execute_tape(tape, directions, cfg, state)
        snapshot_count += len(books)
        trade_count += len(trades)
    if cfg.fill_rule == "trade-through" and trade_count == 0:
        raise ValueError("trade-through replay requires public trade prints")
    return _build_report(state, cfg, snapshot_count, trade_count)
