"""Causal visible-book replay for BTC liquidation treatment episodes."""

from __future__ import annotations

from decimal import Decimal
from hypervector.research.btc_liquidation_covariate_models import (
    AggressorSide,
    BookSnapshot,
    BookTimingCoverage,
    BurstArm,
    CandidateBranch,
    DepthExecution,
    EntryAssessment,
    EntryStatus,
    FundingCashflow,
    FundingAdjustedHorizon,
    FundingSettlement,
    HorizonReplay,
    OverlapPurge,
    PublicTrade,
    PurgeCandidate,
    ReplayEpisode,
    VisibleLevel,
    _nonnegative_integer,
    _positive_decimal,
)

_BASIS_POINTS = Decimal("10000")
_MAXIMUM_ENTRY_BOOK_DELAY_MS = 5_000
_MAXIMUM_EXIT_BOOK_DELAY_MS = 30_000


def assess_book_timing(
    episode: ReplayEpisode,
    *,
    books: tuple[BookSnapshot, ...],
    horizons_ms: tuple[int, ...],
    decision_delay_ms: int = 10_000,
) -> BookTimingCoverage:
    """Measure timestamp coverage without calculating price outcomes."""
    _positive_integer(decision_delay_ms, "decision delay")
    _validate_horizons(horizons_ms)
    _validate_books(books)
    decision_ms = episode.end_ms + decision_delay_ms
    entry_book = _first_complete_book(books, decision_ms)
    if entry_book is None:
        return BookTimingCoverage(
            episode.episode_id,
            decision_ms,
            None,
            None,
            tuple((horizon, None) for horizon in horizons_ms),
            False,
        )
    times = tuple(
        (
            horizon,
            _book_time(
                _first_complete_book(books, entry_book.ts_exchange_ms + horizon)
            ),
        )
        for horizon in horizons_ms
    )
    return BookTimingCoverage(
        episode.episode_id,
        decision_ms,
        entry_book.ts_exchange_ms,
        entry_book.ts_exchange_ms - decision_ms,
        times,
        all(timestamp is not None for _, timestamp in times),
    )


def _book_time(book: BookSnapshot | None) -> int | None:
    return None if book is None else book.ts_exchange_ms


def flow_imbalance(
    trades: tuple[PublicTrade, ...],
    *,
    decision_ms: int,
    window_ms: int,
) -> Decimal | None:
    """Compute exact public-flow imbalance in an open-left interval."""
    _nonnegative_integer(decision_ms, "decision timestamp")
    _positive_integer(window_ms, "flow window")
    _require_chronological(tuple(row.ts_exchange_ms for row in trades), "public trades")
    trade_ids = tuple(row.trade_id for row in trades)
    if len(trade_ids) != len(set(trade_ids)):
        raise ValueError("public trades contain duplicate trade identities")
    start_ms = decision_ms - window_ms
    selected = tuple(
        row for row in trades if start_ms < row.ts_exchange_ms <= decision_ms
    )
    buy = sum(
        (row.notional for row in selected if row.aggressor_side == "buy"),
        Decimal(),
    )
    sell = sum(
        (row.notional for row in selected if row.aggressor_side == "sell"),
        Decimal(),
    )
    total = buy + sell
    return None if total == 0 else (buy - sell) / total


def evaluate_entry(
    episode: ReplayEpisode,
    *,
    trades: tuple[PublicTrade, ...],
    books: tuple[BookSnapshot, ...],
    decision_delay_ms: int = 10_000,
    flow_window_ms: int = 5_000,
    entry_notional_usd: Decimal = Decimal("5000"),
    maximum_entry_book_delay_ms: int = _MAXIMUM_ENTRY_BOOK_DELAY_MS,
) -> EntryAssessment:
    """Apply the frozen causal branch gate and visible-depth entry model."""
    _positive_integer(decision_delay_ms, "decision delay")
    _positive_integer(flow_window_ms, "flow window")
    _positive_decimal(entry_notional_usd, "entry notional")
    _positive_integer(maximum_entry_book_delay_ms, "maximum entry-book delay")
    _validate_books(books)
    decision_ms = episode.end_ms + decision_delay_ms
    flow = flow_imbalance(trades, decision_ms=decision_ms, window_ms=flow_window_ms)
    decision_book = _first_complete_book(books, decision_ms)
    if decision_book is None:
        return _entry_result(
            episode,
            "technical_excluded",
            ("decision_book_unavailable",),
            decision_ms,
            flow,
            None,
            None,
        )
    if decision_book.ts_exchange_ms - decision_ms > maximum_entry_book_delay_ms:
        return _entry_result(
            episode,
            "technical_excluded",
            ("decision_book_delay_exceeded",),
            decision_ms,
            flow,
            decision_book,
            None,
        )
    blockers = _entry_blockers(episode, books, decision_book, decision_ms, flow)
    if blockers:
        return _entry_result(
            episode,
            "signal_blocked",
            blockers,
            decision_ms,
            flow,
            decision_book,
            None,
        )
    quantity = entry_notional_usd / decision_book.asks[0].price
    fill = _walk_depth(decision_book.asks, quantity=quantity, side="buy")
    if not fill.complete:
        return _entry_result(
            episode,
            "technical_excluded",
            ("entry_visible_depth_insufficient",),
            decision_ms,
            flow,
            decision_book,
            fill,
        )
    return _entry_result(
        episode, "eligible", (), decision_ms, flow, decision_book, fill
    )


def replay_outcomes(
    entry: EntryAssessment,
    *,
    books: tuple[BookSnapshot, ...],
    horizons_ms: tuple[int, ...],
    taker_fee_rate: Decimal = Decimal("0.00045"),
    maximum_exit_book_delay_ms: int = _MAXIMUM_EXIT_BOOK_DELAY_MS,
) -> tuple[HorizonReplay, ...]:
    """Replay fixed-quantity exits from the actual entry-book timestamp."""
    if entry.status != "eligible" or entry.entry_fill is None:
        raise ValueError("outcome replay requires an eligible complete entry")
    if entry.decision_book_time_ms is None:
        raise ValueError("eligible entry is missing its book timestamp")
    _nonnegative_decimal(taker_fee_rate, "taker fee rate")
    _positive_integer(maximum_exit_book_delay_ms, "maximum exit-book delay")
    _validate_horizons(horizons_ms)
    _validate_books(books)
    return tuple(
        _replay_horizon(
            entry.entry_fill,
            entry.decision_book_time_ms,
            books,
            horizon_ms,
            taker_fee_rate,
            maximum_exit_book_delay_ms,
        )
        for horizon_ms in horizons_ms
    )


def long_funding_cashflow(
    settlements: tuple[FundingSettlement, ...],
    *,
    entry_time_ms: int,
    exit_time_ms: int,
    entry_notional_usd: Decimal = Decimal("5000"),
) -> FundingCashflow:
    """Calculate exact long funding from settlements in ``(entry, exit]``."""
    _nonnegative_integer(entry_time_ms, "funding entry timestamp")
    _nonnegative_integer(exit_time_ms, "funding exit timestamp")
    if exit_time_ms < entry_time_ms:
        raise ValueError("funding exit timestamp cannot predate entry")
    _positive_decimal(entry_notional_usd, "funding entry notional")
    times = tuple(row.event_time_ms for row in settlements)
    if any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("funding settlements must be ordered and unique")
    selected = tuple(
        row for row in settlements if entry_time_ms < row.event_time_ms <= exit_time_ms
    )
    rate = sum((row.funding_rate for row in selected), Decimal())
    return FundingCashflow(
        entry_time_ms,
        exit_time_ms,
        entry_notional_usd,
        len(selected),
        rate,
        -entry_notional_usd * rate,
    )


def apply_long_funding(
    replay: HorizonReplay,
    *,
    entry_time_ms: int,
    settlements: tuple[FundingSettlement, ...],
    entry_notional_usd: Decimal = Decimal("5000"),
) -> FundingAdjustedHorizon:
    """Apply official long funding to a resolved fixed-horizon replay."""
    if replay.status != "resolved":
        return FundingAdjustedHorizon(replay, None, None, None)
    if (
        replay.exit_book_time_ms is None
        or replay.nominal_net_pnl_before_funding_usd is None
        or replay.stressed_net_pnl_before_funding_usd is None
    ):
        raise ValueError("resolved outcome is missing execution economics")
    funding = long_funding_cashflow(
        settlements,
        entry_time_ms=entry_time_ms,
        exit_time_ms=replay.exit_book_time_ms,
        entry_notional_usd=entry_notional_usd,
    )
    return FundingAdjustedHorizon(
        replay,
        funding,
        replay.nominal_net_pnl_before_funding_usd + funding.cashflow_usd,
        replay.stressed_net_pnl_before_funding_usd + funding.cashflow_usd,
    )


def _replay_horizon(
    entry_fill: DepthExecution,
    entry_time_ms: int,
    books: tuple[BookSnapshot, ...],
    horizon_ms: int,
    fee_rate: Decimal,
    maximum_delay_ms: int,
) -> HorizonReplay:
    target_ms = entry_time_ms + horizon_ms
    book = _first_complete_book(books, target_ms)
    if book is None:
        return _excluded_outcome(horizon_ms, target_ms, "exit_book_unavailable")
    if book.ts_exchange_ms - target_ms > maximum_delay_ms:
        return _excluded_outcome(
            horizon_ms, target_ms, "exit_book_delay_exceeded", book
        )
    fill = _walk_depth(
        book.bids,
        quantity=entry_fill.requested_quantity,
        side="sell",
    )
    if not fill.complete:
        return _excluded_outcome(
            horizon_ms,
            target_ms,
            "exit_visible_depth_insufficient",
            book,
            fill,
        )
    return _resolved_outcome(entry_fill, fill, horizon_ms, target_ms, book, fee_rate)


def purge_overlapping_entries(
    candidates: tuple[PurgeCandidate, ...],
    *,
    overlap_horizon_ms: int,
) -> OverlapPurge:
    """Purge overlapping entries within exact partition, branch, and arm."""
    _positive_integer(overlap_horizon_ms, "overlap horizon")
    identities = [
        (row.partition, row.branch, row.arm, row.episode_id) for row in candidates
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate overlap-purge candidate identity")
    retained: list[PurgeCandidate] = []
    suppressed: list[PurgeCandidate] = []
    latest: dict[tuple[str, CandidateBranch, BurstArm], PurgeCandidate] = {}
    ordered = sorted(
        candidates,
        key=lambda row: (row.decision_time_ms, row.entry_time_ms, row.episode_id),
    )
    for row in ordered:
        key = (row.partition, row.branch, row.arm)
        prior = latest.get(key)
        if prior is not None and row.decision_time_ms <= (
            prior.entry_time_ms + overlap_horizon_ms
        ):
            suppressed.append(row)
            continue
        retained.append(row)
        latest[key] = row
    return OverlapPurge(tuple(retained), tuple(suppressed))


def _entry_blockers(
    episode: ReplayEpisode,
    books: tuple[BookSnapshot, ...],
    decision_book: BookSnapshot,
    decision_ms: int,
    flow: Decimal | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if flow is None or flow <= 0:
        blockers.append("flow_not_positive")
    if episode.branch == "exhaustion_reclaim_long" and not _crossed_below(
        books, episode, decision_ms
    ):
        blockers.append("predecision_midpoint_never_below_episode_vwap")
    if decision_book.midpoint < episode.volume_weighted_price:
        blockers.append("decision_midpoint_below_episode_vwap")
    return tuple(blockers)


def _crossed_below(
    books: tuple[BookSnapshot, ...],
    episode: ReplayEpisode,
    decision_ms: int,
) -> bool:
    return any(
        row.complete
        and episode.end_ms < row.ts_exchange_ms < decision_ms
        and row.midpoint < episode.volume_weighted_price
        for row in books
    )


def _entry_result(
    episode: ReplayEpisode,
    status: EntryStatus,
    blockers: tuple[str, ...],
    decision_ms: int,
    flow: Decimal | None,
    book: BookSnapshot | None,
    fill: DepthExecution | None,
) -> EntryAssessment:
    return EntryAssessment(
        episode=episode,
        status=status,
        blockers=blockers,
        decision_time_ms=decision_ms,
        flow_imbalance=flow,
        decision_book_time_ms=None if book is None else book.ts_exchange_ms,
        decision_midpoint=None if book is None else book.midpoint,
        entry_fill=fill,
    )


def _first_complete_book(
    books: tuple[BookSnapshot, ...],
    boundary_ms: int,
) -> BookSnapshot | None:
    return next(
        (row for row in books if row.complete and row.ts_exchange_ms >= boundary_ms),
        None,
    )


def _walk_depth(
    levels: tuple[VisibleLevel, ...],
    *,
    quantity: Decimal,
    side: AggressorSide,
) -> DepthExecution:
    remaining = quantity
    quote = Decimal()
    filled = Decimal()
    consumed = 0
    worst = levels[0].price
    for level in levels:
        take = min(remaining, level.size)
        quote += take * level.price
        filled += take
        remaining -= take
        consumed += 1
        worst = level.price
        if remaining <= 0:
            break
    vwap = quote / filled
    best = levels[0].price
    impact = _depth_impact_bps(side, best, vwap)
    return DepthExecution(
        quantity, filled, quote, vwap, best, worst, impact, consumed, remaining <= 0
    )


def _depth_impact_bps(
    side: AggressorSide,
    best: Decimal,
    vwap: Decimal,
) -> Decimal:
    if side == "buy":
        return (vwap / best - Decimal("1")) * _BASIS_POINTS
    return (Decimal("1") - vwap / best) * _BASIS_POINTS


def _excluded_outcome(
    horizon_ms: int,
    target_ms: int,
    reason: str,
    book: BookSnapshot | None = None,
    fill: DepthExecution | None = None,
) -> HorizonReplay:
    return HorizonReplay(
        horizon_ms,
        target_ms,
        "technical_excluded",
        reason,
        None if book is None else book.ts_exchange_ms,
        fill,
        None,
        None,
        None,
        None,
    )


def _resolved_outcome(
    entry: DepthExecution,
    exit_fill: DepthExecution,
    horizon_ms: int,
    target_ms: int,
    book: BookSnapshot,
    fee_rate: Decimal,
) -> HorizonReplay:
    gross = exit_fill.quote_notional - entry.quote_notional
    fee = fee_rate * (entry.quote_notional + exit_fill.quote_notional)
    stressed_entry = entry.best_price + Decimal("2") * (entry.vwap - entry.best_price)
    stressed_exit = exit_fill.best_price - Decimal("2") * (
        exit_fill.best_price - exit_fill.vwap
    )
    stressed_entry_quote = stressed_entry * entry.requested_quantity
    stressed_exit_quote = stressed_exit * entry.requested_quantity
    stressed_fee = fee_rate * (stressed_entry_quote + stressed_exit_quote)
    return HorizonReplay(
        horizon_ms=horizon_ms,
        target_time_ms=target_ms,
        status="resolved",
        reason=None,
        exit_book_time_ms=book.ts_exchange_ms,
        exit_fill=exit_fill,
        gross_pnl_usd=gross,
        fee_usd=fee,
        nominal_net_pnl_before_funding_usd=gross - fee,
        stressed_net_pnl_before_funding_usd=(
            stressed_exit_quote - stressed_entry_quote - stressed_fee
        ),
    )


def _validate_horizons(horizons_ms: tuple[int, ...]) -> None:
    if not horizons_ms or len(set(horizons_ms)) != len(horizons_ms):
        raise ValueError("outcome horizons must be nonempty and unique")
    for horizon_ms in horizons_ms:
        _positive_integer(horizon_ms, "outcome horizon")


def _validate_books(books: tuple[BookSnapshot, ...]) -> None:
    _require_chronological(tuple(row.ts_exchange_ms for row in books), "books")


def _require_chronological(values: tuple[int, ...], label: str) -> None:
    if any(left > right for left, right in zip(values, values[1:])):
        raise ValueError(f"{label} must be chronological")


def _nonnegative_decimal(value: Decimal, label: str) -> None:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
