"""Exact report-only lifecycle evidence for the V58 BTC sweep route."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.live.btc_liquidity_sweep_long_provider import (
    LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY,
)
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
    StrategyProviderConfig,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    covered_funding_bps,
)
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    directional_return_bps,
    first_book,
    latest_book_time,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_live_audit_values import mapping, payload
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_compatible_report_only_observer_runs,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.v58_btc_sweep_reporting import (
    build_v58_btc_sweep_pending,
    build_v58_btc_sweep_report,
)
from hypervector.research.v58_btc_sweep_marks import validated_btc_marks

Record = Mapping[str, object]
BTC_SWEEP_STRATEGY = LIQUIDITY_SWEEP_LONG_TARGET60_STRATEGY
_SYMBOL = "BTC"
_OPPOSITE_STRATEGIES = frozenset(
    {"hulk_expansion_short_robust_v3", "hulk_expansion_short_tuned_v2"}
)
_MAXIMUM_MARK_GAP_MS = 120_000
_MAXIMUM_EXIT_DELAY_MS = 60_000


@dataclass(frozen=True)
class _ExitEvent:
    time_ms: int
    priority: int
    reason: str
    book: Record | None = None
    opposite_strategy_id: str | None = None


def build_v58_btc_sweep_resolution(
    records: Sequence[Record],
    *,
    marks: Sequence[Record],
    config: MultiAssetLiveConfig,
    run_id: str,
    prospective_start_ms: int,
    funding_evidence: EligiblePolicyFundingEvidence | None,
    taker_fee_rate: float,
) -> dict[str, object]:
    """Replay prospective sweep entries through exact books and public marks."""
    start = _nonnegative_integer(prospective_start_ms, "BTC prospective start")
    fee = _positive_number(taker_fee_rate, "BTC taker fee rate")
    selected, identities = select_compatible_report_only_observer_runs(records, run_id)
    provider, asset = _route(config)
    execution = provider.execution_for(_SYMBOL)
    compatible = tuple(str(row["run_id"]) for row in identities)
    extracted = extract_observer_asset_books(selected, (_SYMBOL,))[_SYMBOL]
    books = validated_books(extracted, symbol=_SYMBOL, run_ids=compatible)
    mark_rows = validated_btc_marks(marks, run_id=run_id)
    entries, opposites = _candidates(selected, run_id, start)
    attempts, outcomes, overlapping = _evaluate_entries(
        entries,
        opposites,
        books,
        mark_rows,
        asset,
        funding_evidence,
        fee,
        provider.maximum_entry_delay_seconds * 1_000,
        execution.maximum_hold_seconds * 1_000,
    )
    contract = _contract(config, run_id, compatible, asset, provider)
    return build_v58_btc_sweep_report(contract, attempts, outcomes, overlapping, start)


def _route(
    config: MultiAssetLiveConfig,
) -> tuple[StrategyProviderConfig, AssetLiveConfig]:
    providers = [
        row
        for row in config.providers
        if row.strategy_id == BTC_SWEEP_STRATEGY and _SYMBOL in row.symbols
    ]
    assets = [row for row in config.assets if row.symbol == _SYMBOL]
    if len(providers) != 1 or len(assets) != 1:
        raise ValueError("V58 BTC sweep route must be unique")
    provider, asset = providers[0], assets[0]
    execution = provider.execution_for(_SYMBOL)
    valid = (
        provider.symbols == (_SYMBOL,)
        and provider.sides == frozenset({"long"})
        and provider.execution_symbols == (_SYMBOL,)
        and provider.position_policy == "enter_and_close"
        and provider.timeframe == "1h"
        and provider.maximum_entry_delay_seconds == 30
        and execution.entry_liquidity == "taker_ioc"
        and execution.stop_policy == "fixed_bps"
        and execution.stop_bps == 60.0
        and execution.target_policy == "fixed_bps"
        and execution.target_bps == 60.0
        and execution.maximum_hold_seconds == 86_400
        and execution.maximum_hold_policy == "fixed"
        and execution.provider_recipe_exit_policy == "ignore"
        and execution.profit_lock_policy == "none"
    )
    if not valid:
        raise ValueError("V58 BTC sweep execution contract is unsupported")
    return provider, asset


def _candidates(
    records: Sequence[Record], run_id: str, start_ms: int
) -> tuple[tuple[SignalCandidate, ...], tuple[SignalCandidate, ...]]:
    candidates, _, _ = evaluation_candidates(records)
    prospective = tuple(
        row
        for row in candidates
        if row.source_run_id == run_id
        and row.symbol == _SYMBOL
        and row.decision_time_ms >= start_ms
        and row.eligible
    )
    entries = tuple(row for row in prospective if row.strategy_id == BTC_SWEEP_STRATEGY)
    opposites = tuple(
        row
        for row in prospective
        if row.strategy_id in _OPPOSITE_STRATEGIES and row.side == "short"
    )
    return entries, opposites


def _evaluate_entries(
    entries: Sequence[SignalCandidate],
    opposites: Sequence[SignalCandidate],
    books: Sequence[Record],
    marks: Sequence[Record],
    asset: AssetLiveConfig,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    entry_delay_ms: int,
    hold_ms: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    attempts: list[dict[str, object]] = []
    outcomes: list[dict[str, object]] = []
    next_available_ms = -1
    overlapping = 0
    for candidate in entries:
        if candidate.available_time_ms < next_available_ms:
            overlapping += 1
            continue
        attempt, outcome, next_available_ms = _evaluate_entry(
            candidate,
            opposites,
            books,
            marks,
            asset.max_notional_usd,
            funding,
            fee_rate,
            entry_delay_ms,
            hold_ms,
        )
        attempts.append(attempt)
        if outcome is not None:
            outcomes.append(outcome)
    return attempts, outcomes, overlapping


def _evaluate_entry(
    candidate: SignalCandidate,
    opposites: Sequence[SignalCandidate],
    books: Sequence[Record],
    marks: Sequence[Record],
    notional: float,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    entry_delay_ms: int,
    hold_ms: int,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    base = _base(candidate)
    entry = first_book(books, candidate.available_time_ms, entry_delay_ms)
    deadline = candidate.available_time_ms + hold_ms
    if entry is None:
        return base | {"status": "entry_book_unavailable"}, None, deadline
    fill = visible_depth_fill(
        entry, position_side="long", notional=notional, quantity=None
    )
    if not fill["complete"]:
        return base | _capacity("entry", entry, fill), None, deadline
    entry_ms = book_time(entry)
    event = _first_exit(
        entry_ms, float(fill["price"]), deadline, books, marks, opposites
    )
    path_end = min(event.time_ms if event else latest_book_time(books), deadline)
    quality = _mark_quality(marks, entry_ms, path_end)
    entry_fields = _entry_fields(entry, fill)
    if quality["complete"] is not True:
        row = _mark_incomplete(base, entry_fields, quality)
        return row, None, deadline
    if event is None:
        row = _pending_row(base, entry_fields, books, fill, fee_rate, quality)
        return row, None, deadline
    exit_book = event.book or first_book(books, event.time_ms, _MAXIMUM_EXIT_DELAY_MS)
    if exit_book is None:
        row = (
            base
            | entry_fields
            | {
                "status": f"{event.reason}_exit_book_unavailable",
                "mark_path": quality,
            }
        )
        return row, None, deadline
    outcome = _resolved(
        base, entry, exit_book, fill, candidate, event, funding, fee_rate, quality
    )
    resolved = outcome if outcome.get("status") == "resolved" else None
    return outcome, resolved, book_time(exit_book) + 1


def _first_exit(
    entry_ms: int,
    entry_price: float,
    deadline: int,
    books: Sequence[Record],
    marks: Sequence[Record],
    opposites: Sequence[SignalCandidate],
) -> _ExitEvent | None:
    stop = entry_price * 0.994
    target = entry_price * 1.006
    path_books = [row for row in books if entry_ms < book_time(row) <= deadline]
    path_marks = [
        row for row in marks if entry_ms <= int(row["received_ts_ms"]) <= deadline
    ]
    events: list[_ExitEvent] = []
    stopped = next(
        (row for row in path_marks if float(row["mark_price"]) <= stop), None
    )
    if stopped is not None:
        events.append(
            _ExitEvent(int(stopped["received_ts_ms"]), 0, "protective_stop_mark")
        )
    targeted = next((row for row in path_books if _best_bid(row) >= target), None)
    if targeted is not None:
        events.append(_ExitEvent(book_time(targeted), 1, "fixed_target", targeted))
    opposite = next(
        (row for row in opposites if entry_ms < row.available_time_ms <= deadline), None
    )
    if opposite is not None:
        events.append(
            _ExitEvent(
                opposite.available_time_ms,
                2,
                "eligible_cross_provider_opposite_intent",
                opposite_strategy_id=opposite.strategy_id,
            )
        )
    if latest_book_time(books) >= deadline:
        events.append(_ExitEvent(deadline, 3, "maximum_hold"))
    return min(events, key=lambda row: (row.time_ms, row.priority), default=None)


def _mark_quality(
    marks: Sequence[Record], entry_ms: int, end_ms: int
) -> dict[str, object]:
    selected = [
        row for row in marks if entry_ms <= int(row["received_ts_ms"]) <= end_ms
    ]
    times = [entry_ms, *(int(row["received_ts_ms"]) for row in selected), end_ms]
    maximum_gap = max(
        (right - left for left, right in zip(times, times[1:])), default=0
    )
    complete = bool(selected) and maximum_gap <= _MAXIMUM_MARK_GAP_MS
    return {
        "complete": complete,
        "source": "receipt_causal_public_metaAndAssetCtxs_mark",
        "maximum_allowed_gap_ms": _MAXIMUM_MARK_GAP_MS,
        "maximum_gap_ms": maximum_gap,
        "observations": len(selected),
        "first_received_ts_ms": int(selected[0]["received_ts_ms"])
        if selected
        else None,
        "last_received_ts_ms": int(selected[-1]["received_ts_ms"])
        if selected
        else None,
    }


def _mark_incomplete(
    base: Record, entry_fields: Record, quality: Record
) -> dict[str, object]:
    return (
        dict(base)
        | dict(entry_fields)
        | {
            "status": "mark_path_incomplete",
            "mark_path": dict(quality),
        }
    )


def _pending_row(
    base: Record,
    entry_fields: Record,
    books: Sequence[Record],
    fill: Record,
    fee_rate: float,
    quality: Record,
) -> dict[str, object]:
    return (
        dict(base)
        | dict(entry_fields)
        | build_v58_btc_sweep_pending(books, fill, fee_rate, quality)
    )


def _resolved(
    base: dict[str, object],
    entry: Record,
    exit_book: Record,
    entry_fill: Record,
    candidate: SignalCandidate,
    event: _ExitEvent,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
    quality: Record,
) -> dict[str, object]:
    exit_fill = visible_depth_fill(
        exit_book,
        position_side="long",
        notional=0.0,
        quantity=float(entry_fill["quantity"]),
    )
    if not exit_fill["complete"]:
        return (
            base
            | _entry_fields(entry, entry_fill)
            | _capacity("exit", exit_book, exit_fill)
        )
    economics = _economics(
        entry, exit_book, entry_fill, exit_fill, candidate, funding, fee_rate
    )
    return (
        base
        | _entry_fields(entry, entry_fill)
        | economics
        | {
            "status": "resolved",
            "technical_complete": True,
            "exit_reason": event.reason,
            "opposite_strategy_id": event.opposite_strategy_id,
            "mark_path": dict(quality),
        }
    )


def _economics(
    entry: Record,
    exit_book: Record,
    entry_fill: Record,
    exit_fill: Record,
    candidate: SignalCandidate,
    funding: EligiblePolicyFundingEvidence | None,
    fee_rate: float,
) -> dict[str, object]:
    entry_price, exit_price = float(entry_fill["price"]), float(exit_fill["price"])
    gross = directional_return_bps("long", entry_price, exit_price)
    entry_notional = float(entry_fill["quote_usd"])
    fee_usd = fee_rate * (entry_notional + float(exit_fill["quote_usd"]))
    fee_bps = fee_usd / entry_notional * 10_000.0
    funding_bps = covered_funding_bps(
        funding,
        symbol=_SYMBOL,
        side=candidate.side or "",
        start_ms=book_time(entry),
        end_ms=book_time(exit_book),
    )
    net = gross - fee_bps + (funding_bps or 0.0)
    return {
        "exit_time_ms": book_time(exit_book),
        "exit_price": exit_price,
        "exit_levels_consumed": exit_fill["levels_consumed"],
        "gross_return_bps": gross,
        "fee_usd": fee_usd,
        "fee_bps": fee_bps,
        "funding_bps": funding_bps,
        "net_return_bps": net,
        "simulated_net_pnl_usd": entry_notional * net / 10_000.0,
    }


def _contract(
    config: MultiAssetLiveConfig,
    run_id: str,
    compatible: Sequence[str],
    asset: AssetLiveConfig,
    provider: StrategyProviderConfig,
) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "portfolio_pnl_claimed": False,
        "actual_orders_or_fills_claimed": False,
        "source_strategy_id": BTC_SWEEP_STRATEGY,
        "symbol": _SYMBOL,
        "source_run_id": run_id,
        "compatible_run_ids": list(compatible),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "sides": ["long"],
        "notional_usd": asset.max_notional_usd,
        "stop_bps": 60.0,
        "target_bps": 60.0,
        "maximum_hold_minutes": 1_440,
        "maximum_entry_delay_ms": provider.maximum_entry_delay_seconds * 1_000,
        "cross_provider_opposite_strategies": sorted(_OPPOSITE_STRATEGIES),
        "entry_exit_source": "recorded_visible_l2_depth_vwap",
        "stop_trigger_source": "receipt_causal_public_metaAndAssetCtxs_mark",
    }


def _base(candidate: SignalCandidate) -> dict[str, object]:
    return {
        "source_run_id": candidate.source_run_id,
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "reference_price": candidate.reference_price,
    }


def _entry_fields(entry: Record, fill: Record) -> dict[str, object]:
    return {
        "entry_time_ms": book_time(entry),
        "entry_price": fill["price"],
        "entry_notional_usd": fill["quote_usd"],
        "position_quantity": fill["quantity"],
        "entry_levels_consumed": fill["levels_consumed"],
    }


def _capacity(prefix: str, book: Record, fill: Record) -> dict[str, object]:
    return {
        "status": f"{prefix}_capacity_insufficient",
        f"{prefix}_time_ms": book_time(book),
        f"{prefix}_filled_quantity": fill["quantity"],
        f"{prefix}_unfilled_quantity": fill["unfilled_quantity"],
    }


def _best_bid(book: Record) -> float:
    rows = payload(book).get("bids")
    if not isinstance(rows, Sequence) or not rows:
        raise ValueError("BTC book bids must be a non-empty sequence")
    first = mapping(rows[0], "BTC best bid")
    return _positive_number(first.get("price"), "BTC best bid")


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not 0.0 < output < float("inf"):
        raise ValueError(f"{label} must be finite and positive")
    return output


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
