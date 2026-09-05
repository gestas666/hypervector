"""Causal visible-depth paths for reconstructed HYPE-native onsets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import math

from hypervector.research.cohort_exact_depth_books import (
    book_time,
    directional_return_bps,
    first_book,
    first_stop_book,
    latest_book_time,
    post_entry_books,
    protective_stop_price,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]
_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"


@dataclass(frozen=True)
class HypeNativePathSpec:
    """Frozen identity, execution, risk, and friction for one onset path."""

    run_id: str
    profile_id: str
    profile_fingerprint: str
    source_strategy_id: str
    candidate_strategy_id: str
    symbol: str
    side: str
    decision_time_ms: int
    notional_usd: float
    stop_bps: float
    maximum_entry_delay_ms: int
    maximum_exit_delay_ms: int
    soft_hold_seconds: int
    hard_hold_seconds: int
    fee_bps_per_side: float
    residual_slippage_bps_per_side: float
    maximum_clock_skew_ms: int
    horizons_minutes: tuple[int, ...]

    def __post_init__(self) -> None:
        """Reject identity drift, invalid sizing, or ambiguous exit geometry."""
        _validate_identity(self)
        _validate_execution(self)


def build_hype_native_counterfactual_path(
    cohort_records: Sequence[Record],
    asset_records: Sequence[Record],
    spec: HypeNativePathSpec,
) -> dict[str, object]:
    """Build one report-only finite-depth path without claiming venue fills."""
    _cohort_identity(cohort_records, spec)
    candidates, excluded, conflicts = evaluation_candidates(cohort_records)
    source = _source_candidate(candidates, spec)
    native = replace(
        source,
        strategy_id=spec.candidate_strategy_id,
        eligible=True,
        blockers=(),
    )
    books, asset_identity, clock_evidence = _asset_books(asset_records, spec)
    execution = _execution_path(native, candidates, books, spec)
    return {
        "schema_version": 1,
        "mode": "hype_native_counterfactual_exact_depth_v1",
        "contract": _contract(),
        "identity": _identity(spec, asset_identity),
        "market_clock_evidence": clock_evidence,
        "source_signal": _source_payload(source, excluded, conflicts),
        "execution_path": execution,
        "status": _status(execution),
        "limitations": _limitations(),
    }


def _source_candidate(
    candidates: Sequence[SignalCandidate], spec: HypeNativePathSpec
) -> SignalCandidate:
    matches = [
        item
        for item in candidates
        if item.source_run_id == spec.run_id
        and item.strategy_id == spec.source_strategy_id
        and item.symbol == spec.symbol
        and item.decision_time_ms == spec.decision_time_ms
    ]
    if len(matches) != 1:
        raise ValueError("HYPE-native source onset must resolve exactly once")
    source = matches[0]
    if source.side != spec.side:
        raise ValueError("HYPE-native source onset side differs from frozen spec")
    if source.eligible:
        raise ValueError("HYPE-native counterfactual source was already executable")
    if source.metrics.get("canonical_breakout_onset_fresh") is not True:
        raise ValueError("HYPE-native source is not a fresh canonical breakout onset")
    return source


def _cohort_identity(records: Sequence[Record], spec: HypeNativePathSpec) -> None:
    identities = [
        row
        for row in records
        if row.get("event_type") == "configuration_identity"
        and row.get("run_id") == spec.run_id
    ]
    if len(identities) != 1:
        raise ValueError("HYPE cohort ledger requires one exact run identity")
    identity = identities[0]
    if identity.get("profile_id") != spec.profile_id:
        raise ValueError("HYPE cohort profile differs from frozen path")
    if identity.get("profile_fingerprint") != spec.profile_fingerprint:
        raise ValueError("HYPE cohort profile fingerprint differs from frozen path")


def _asset_books(
    records: Sequence[Record], spec: HypeNativePathSpec
) -> tuple[tuple[Record, ...], Record, dict[str, int]]:
    identities = [
        row
        for row in records
        if row.get("event_type") == "configuration_identity"
        and row.get("run_id") == spec.run_id
    ]
    if len(identities) != 1:
        raise ValueError("HYPE asset ledger requires one exact run identity")
    identity = identities[0]
    payload = _mapping(identity.get("payload"), "asset identity payload")
    if payload.get("symbol") != spec.symbol:
        raise ValueError("HYPE asset ledger symbol differs from frozen spec")
    rows = [_normalized_book(row, identity, spec) for row in records if _is_book(row)]
    books = validated_books(
        rows,
        symbol=spec.symbol,
        run_ids=(spec.run_id,),
        maximum_exchange_ahead_ms=spec.maximum_clock_skew_ms,
    )
    return books, identity, _clock_evidence(books, spec.maximum_clock_skew_ms)


def _clock_evidence(books: Sequence[Record], allowed_ms: int) -> dict[str, int]:
    skews = [
        int(_mapping(row["payload"], "book payload")["exchange_ts_ms"]) - book_time(row)
        for row in books
    ]
    ahead = [value for value in skews if value > 0]
    return {
        "maximum_allowed_exchange_ahead_ms": allowed_ms,
        "exchange_ahead_row_count": len(ahead),
        "maximum_exchange_ahead_ms": max(ahead, default=0),
    }


def _normalized_book(row: Record, identity: Record, spec: HypeNativePathSpec) -> Record:
    if row.get("run_id") != spec.run_id:
        raise ValueError("HYPE book run differs from frozen path")
    for field in ("profile_id", "profile_fingerprint"):
        if row.get(field) != identity.get(field):
            raise ValueError(f"HYPE book {field} differs from asset identity")
    payload = dict(_mapping(row.get("payload"), "book payload"))
    if payload.get("source") != _BOOK_SOURCE:
        raise ValueError("HYPE book source differs from mainnet L2 REST")
    payload["symbol"] = spec.symbol
    return dict(row) | {"payload": payload}


def _execution_path(
    candidate: SignalCandidate,
    all_candidates: Sequence[SignalCandidate],
    books: Sequence[Record],
    spec: HypeNativePathSpec,
) -> dict[str, object]:
    entry = first_book(books, candidate.available_time_ms, spec.maximum_entry_delay_ms)
    if entry is None:
        return {"status": "entry_book_unavailable", "exit_reason": None}
    entry_fill = visible_depth_fill(
        entry, position_side=spec.side, notional=spec.notional_usd, quantity=None
    )
    if entry_fill.get("complete") is not True:
        return {"status": "entry_depth_insufficient", "exit_reason": None}
    deadline = book_time(entry) + spec.hard_hold_seconds * 1_000
    path = post_entry_books(books, book_time(entry), deadline)
    stop_price = protective_stop_price(
        spec.side, float(entry_fill["price"]), spec.stop_bps
    )
    stop = first_stop_book(path, side=spec.side, stop_price=stop_price)
    opposite = _opposite_exit_book(all_candidates, books, candidate, spec)
    exit_reason, exit_book = _first_exit(stop, opposite)
    return _path_payload(entry, entry_fill, exit_book, exit_reason, books, spec)


def _opposite_exit_book(
    candidates: Sequence[SignalCandidate],
    books: Sequence[Record],
    entry: SignalCandidate,
    spec: HypeNativePathSpec,
) -> Record | None:
    exits = [
        item
        for item in candidates
        if item.source_run_id == spec.run_id
        and item.strategy_id == spec.source_strategy_id
        and item.symbol == spec.symbol
        and item.decision_time_ms > entry.decision_time_ms
        and item.metrics.get("canonical_breakout_onset_fresh") is True
        and item.side not in {None, spec.side}
    ]
    if not exits:
        return None
    first = min(exits, key=lambda item: item.available_time_ms)
    return first_book(books, first.available_time_ms, spec.maximum_exit_delay_ms)


def _first_exit(
    stop: Record | None, opposite: Record | None
) -> tuple[str | None, Record | None]:
    candidates = [
        ("protective_stop_bbo_proxy", stop),
        ("opposite_native_onset", opposite),
    ]
    available = [(reason, book) for reason, book in candidates if book is not None]
    return (
        min(available, key=lambda item: book_time(item[1]))
        if available
        else (None, None)
    )


def _path_payload(
    entry: Record,
    entry_fill: Record,
    exit_book: Record | None,
    exit_reason: str | None,
    books: Sequence[Record],
    spec: HypeNativePathSpec,
) -> dict[str, object]:
    current = exit_book or books[-1]
    current_outcome = _outcome(entry_fill, current, spec)
    return {
        "status": "resolved"
        if exit_book is not None
        else _open_status(entry, books, spec),
        "entry_book_time_ms": book_time(entry),
        "entry_price": entry_fill["price"],
        "entry_quantity": entry_fill["quantity"],
        "entry_levels_consumed": entry_fill["levels_consumed"],
        "stop_price": protective_stop_price(
            spec.side, float(entry_fill["price"]), spec.stop_bps
        ),
        "exit_reason": exit_reason,
        "exit_book_time_ms": book_time(exit_book) if exit_book is not None else None,
        **(
            {"net_pnl_usd_before_funding": current_outcome["net_pnl_usd"]}
            if exit_book
            else {}
        ),
        "current_book_time_ms": book_time(current),
        "current_net_pnl_usd_before_funding": current_outcome["net_pnl_usd"],
        "current_outcome": current_outcome,
        "horizons": _horizons(entry, entry_fill, books, spec),
    }


def _horizons(
    entry: Record, entry_fill: Record, books: Sequence[Record], spec: HypeNativePathSpec
) -> dict[str, object]:
    result: dict[str, object] = {}
    for minutes in spec.horizons_minutes:
        target = book_time(entry) + minutes * 60_000
        book = first_book(books, target, spec.maximum_exit_delay_ms)
        if book is not None:
            selected_time = book_time(book)
            result[str(minutes)] = {
                "status": "resolved_bbo_proxy",
                "target_time_ms": target,
                "book_time_ms": selected_time,
                "book_delay_ms": selected_time - target,
            } | _outcome(entry_fill, book, spec)
        else:
            status = "censored" if latest_book_time(books) < target else "book_gap"
            result[str(minutes)] = {"status": status, "target_time_ms": target}
    return result


def _outcome(
    entry_fill: Record, exit_book: Record, spec: HypeNativePathSpec
) -> dict[str, object]:
    quantity = float(entry_fill["quantity"])
    exit_fill = visible_depth_fill(
        exit_book, position_side=spec.side, notional=0.0, quantity=quantity
    )
    if exit_fill.get("complete") is not True:
        raise ValueError("HYPE counterfactual exit exceeds recorded depth")
    entry_price, exit_price = float(entry_fill["price"]), float(exit_fill["price"])
    direction = 1.0 if spec.side == "long" else -1.0
    gross_usd = direction * quantity * (exit_price - entry_price)
    turnover = float(entry_fill["quote_usd"]) + float(exit_fill["quote_usd"])
    fee_usd = turnover * spec.fee_bps_per_side / 10_000
    residual_usd = turnover * spec.residual_slippage_bps_per_side / 10_000
    net_usd = gross_usd - fee_usd - residual_usd
    return {
        "exit_price": exit_price,
        "exit_levels_consumed": exit_fill["levels_consumed"],
        "gross_return_bps": directional_return_bps(spec.side, entry_price, exit_price),
        "fee_usd": fee_usd,
        "residual_slippage_usd": residual_usd,
        "net_pnl_usd": net_usd,
        "net_return_on_entry_notional_bps": net_usd
        / float(entry_fill["quote_usd"])
        * 10_000,
    }


def _open_status(
    entry: Record, books: Sequence[Record], spec: HypeNativePathSpec
) -> str:
    age = latest_book_time(books) - book_time(entry)
    if age >= spec.hard_hold_seconds * 1_000:
        return "hard_exit_book_not_evaluated"
    if age >= spec.soft_hold_seconds * 1_000:
        return "soft_deadline_requires_regime_policy_replay"
    return "open_counterfactual_path"


def _source_payload(
    source: SignalCandidate, excluded: int, conflicts: int
) -> dict[str, object]:
    return {
        "source_strategy_id": source.strategy_id,
        "source_eligible": source.eligible,
        "decision_time_ms": source.decision_time_ms,
        "available_time_ms": source.available_time_ms,
        "reference_price": source.reference_price,
        "side": source.side,
        "excluded_pre_activation": excluded,
        "direction_conflicts": conflicts,
        "canonical_breakout_onset_fresh": True,
    }


def _identity(spec: HypeNativePathSpec, asset: Record) -> dict[str, object]:
    return {
        "run_id": spec.run_id,
        "profile_id": spec.profile_id,
        "profile_fingerprint": spec.profile_fingerprint,
        "source_strategy_id": spec.source_strategy_id,
        "candidate_strategy_id": spec.candidate_strategy_id,
        "asset_profile_id": asset.get("profile_id"),
        "asset_profile_fingerprint": asset.get("profile_fingerprint"),
        "symbol": spec.symbol,
        "side": spec.side,
        "decision_time_ms": spec.decision_time_ms,
        "notional_usd": spec.notional_usd,
        "stop_bps": spec.stop_bps,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_or_fills_assumed": False,
        "realized_pnl_claimed": False,
        "entry_anchor": "first_recorded_book_at_or_after_signal_publication",
        "entry_liquidity": "finite_depth_taker_vwap",
        "stop_trigger_proxy": "first_recorded_executable_bbo_cross",
        "funding_included": False,
    }


def _status(execution: Record) -> str:
    if execution.get("status") != "resolved":
        return str(execution.get("status"))
    if execution.get("exit_reason") == "protective_stop_bbo_proxy":
        return "resolved_bbo_stop_proxy_mark_trigger_unverified"
    return "resolved_opposite_signal_proxy"


def _limitations() -> list[str]:
    return [
        "recorded BBO does not prove a venue mark-price stop trigger",
        "recorded books are sampled and do not prove private fills or latency",
        "funding is excluded until official hourly evidence is attached",
        "residual slippage is modeled rather than realized",
        "soft-hold extension requires a separate exact production-policy replay",
    ]


def _validate_identity(spec: HypeNativePathSpec) -> None:
    for value, label in (
        (spec.run_id, "run id"),
        (spec.profile_id, "profile id"),
        (spec.profile_fingerprint, "profile fingerprint"),
        (spec.source_strategy_id, "source strategy id"),
        (spec.candidate_strategy_id, "candidate strategy id"),
    ):
        _text(value, label)
    if spec.symbol != "HYPE" or spec.side not in {"long", "short"}:
        raise ValueError("HYPE-native path requires exact HYPE and long or short")
    if spec.source_strategy_id == spec.candidate_strategy_id:
        raise ValueError("HYPE-native candidate identity must be distinct")


def _validate_execution(spec: HypeNativePathSpec) -> None:
    _nonnegative_integer(spec.decision_time_ms, "decision time")
    for value, label in (
        (spec.notional_usd, "notional"),
        (spec.stop_bps, "stop bps"),
    ):
        _positive(value, label)
    for value, label in (
        (spec.maximum_entry_delay_ms, "entry delay"),
        (spec.maximum_exit_delay_ms, "exit delay"),
        (spec.soft_hold_seconds, "soft hold"),
        (spec.hard_hold_seconds, "hard hold"),
    ):
        _positive_integer(value, label)
    if spec.hard_hold_seconds <= spec.soft_hold_seconds:
        raise ValueError("HYPE-native hard hold must exceed soft hold")
    _nonnegative(spec.fee_bps_per_side, "fee bps")
    _nonnegative(spec.residual_slippage_bps_per_side, "slippage bps")
    _nonnegative_integer(spec.maximum_clock_skew_ms, "maximum clock skew")
    if not spec.horizons_minutes or len(set(spec.horizons_minutes)) != len(
        spec.horizons_minutes
    ):
        raise ValueError("HYPE-native horizons must be unique and non-empty")
    for value in spec.horizons_minutes:
        _positive_integer(value, "horizon minutes")


def _is_book(row: Record) -> bool:
    return row.get("event_type") == "book_observation"


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output


def _positive(value: object, label: str) -> float:
    output = _number(value, label)
    if output <= 0.0:
        raise ValueError(f"{label} must be positive")
    return output


def _nonnegative(value: object, label: str) -> float:
    output = _number(value, label)
    if output < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return output


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
