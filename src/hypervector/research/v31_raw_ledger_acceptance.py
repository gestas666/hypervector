"""Raw-ledger v31 acceptance for causal pressure books and funding cursors."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.live.cohort_funding_window import (
    CohortFundingWindow,
    funding_window_from_payload,
)
from hypervector.research.cohort_live_audit_values import (
    mapping,
    nonnegative_int,
    number,
    text,
)
from hypervector.research.candidate_raw_acceptance_report import (
    build_raw_acceptance_report,
)
from hypervector.research.v31_poststart_acceptance import PRESSURE_ROUTES
from hypervector.research.v31_raw_identity import (
    V31_SYMBOLS,
    is_asset_event,
    is_run_event,
    ledger_sequence,
    ledger_timestamp_ms,
    raw_acceptance_identity,
)

Record = Mapping[str, object]
AssetRecords = Mapping[str, Sequence[Record]]

_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"
_BOUNDARY_SEMANTICS = "contiguous_cursor_with_inclusive_venue_deduplication"
_IMBALANCE_TOLERANCE = 1e-12
_CUTOFF_TOLERANCE_MS = 0


def build_v31_raw_ledger_acceptance(
    checkpoint: Record,
    aggregate_acceptance: Record,
    cohort_records: Sequence[Record],
    asset_records: AssetRecords,
    *,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Build execution-incapable raw-book and funding-cursor acceptance."""
    return build_candidate_raw_ledger_acceptance(
        checkpoint,
        aggregate_acceptance,
        cohort_records,
        asset_records,
        expected_profile_id=("multi_asset_bidirectional_swing_pruned_candidate_v31"),
        symbols=V31_SYMBOLS,
        schema_version="v31_raw_ledger_acceptance_v1",
        maximum_pressure_age_seconds=maximum_pressure_age_seconds,
    )


def build_candidate_raw_ledger_acceptance(
    checkpoint: Record,
    aggregate_acceptance: Record,
    cohort_records: Sequence[Record],
    asset_records: AssetRecords,
    *,
    expected_profile_id: str,
    symbols: Sequence[str],
    schema_version: str,
    maximum_pressure_age_seconds: float = 30.0,
) -> dict[str, object]:
    """Build raw-ledger acceptance for one exact candidate identity."""
    maximum_age = _candidate_parameters(
        expected_profile_id, symbols, schema_version, maximum_pressure_age_seconds
    )
    identity, identity_reasons = raw_acceptance_identity(
        checkpoint,
        aggregate_acceptance,
        expected_profile_id=expected_profile_id,
    )
    routing, evaluations = _first_pressure_group(cohort_records, identity)
    books, book_reasons = _causal_books(
        evaluations,
        routing,
        asset_records,
        identity,
        maximum_age,
    )
    cutoff = books.get("common_provider_cutoff_time_ms")
    funding, funding_reasons = _funding_cursor(
        cohort_records,
        identity,
        routing,
        cutoff if isinstance(cutoff, int) else None,
    )
    payments, payment_reasons = _funding_payments(
        asset_records, identity, funding, symbols
    )
    reasons = identity_reasons + book_reasons + funding_reasons + payment_reasons
    return build_raw_acceptance_report(
        checkpoint,
        aggregate_acceptance,
        identity,
        routing,
        books,
        funding,
        payments,
        reasons,
        schema_version=schema_version,
    )


def _candidate_parameters(
    profile_id: str, symbols: Sequence[str], schema: str, maximum_age: float
) -> float:
    if not profile_id.strip() or not schema.strip():
        raise ValueError("candidate profile and schema must be nonempty")
    if not symbols or any(not symbol.strip() for symbol in symbols):
        raise ValueError("candidate symbols must be nonempty strings")
    value = number(maximum_age, "maximum pressure age")
    if value <= 0.0:
        raise ValueError("maximum pressure age must be positive")
    return value


def _first_pressure_group(
    records: Sequence[Record], identity: Record
) -> tuple[Record, dict[str, Record]]:
    for row in records:
        if not is_run_event(row, identity, "intent_routing"):
            continue
        payload = mapping(row.get("payload"), "routing payload")
        raw = payload.get("evaluations")
        if not isinstance(raw, list):
            raise ValueError("routing evaluations must be a list")
        evaluations = _pressure_evaluations(raw)
        if evaluations:
            if set(evaluations) != set(PRESSURE_ROUTES):
                raise ValueError("first HIP-3 pressure group is incomplete")
            return row, evaluations
    raise ValueError("exact v31 run has no HIP-3 pressure evaluation group")


def _pressure_evaluations(raw: Sequence[object]) -> dict[str, Record]:
    evaluations: dict[str, Record] = {}
    for item in raw:
        value = mapping(item, "provider evaluation")
        strategy = value.get("strategy_id")
        symbol = value.get("symbol")
        if not isinstance(strategy, str) or not isinstance(symbol, str):
            continue
        route = f"{strategy}|{symbol}"
        if route in PRESSURE_ROUTES:
            if route in evaluations:
                raise ValueError(f"duplicate HIP-3 pressure evaluation: {route}")
            evaluations[route] = value
    return evaluations


def _causal_books(
    evaluations: Mapping[str, Record],
    routing: Record,
    assets: AssetRecords,
    identity: Record,
    maximum_age: float,
) -> tuple[dict[str, object], list[str]]:
    routing_ms = ledger_timestamp_ms(routing)
    candidates: dict[str, list[dict[str, object]]] = {}
    reasons: list[str] = []
    for route in PRESSURE_ROUTES:
        symbol = route.split("|", maxsplit=1)[1]
        rows = assets.get(symbol)
        if rows is None:
            reasons.append(f"asset_ledger_missing:{symbol}")
            candidates[route] = []
            continue
        candidates[route] = _book_candidates(
            route,
            evaluations[route],
            rows,
            identity,
            routing_ms,
            maximum_age,
        )
        if not candidates[route]:
            reasons.append(f"causal_book_missing:{route}")
    cutoff, selected = _common_cutoff(candidates)
    if cutoff is None:
        reasons.append("pressure_cutoff_mismatch")
    route_reports: dict[str, object] = {}
    if cutoff is not None:
        for route, candidate in selected.items():
            report, reason = _latest_book_check(
                route, candidate, cutoff, assets, identity
            )
            route_reports[route] = report
            if reason is not None:
                reasons.append(reason)
    return {
        "passed": not reasons,
        "common_provider_cutoff_time_ms": cutoff,
        "routes": route_reports,
    }, reasons


def _book_candidates(
    route: str,
    evaluation: Record,
    records: Sequence[Record],
    identity: Record,
    routing_ms: int,
    maximum_age: float,
) -> list[dict[str, object]]:
    readiness = mapping(evaluation.get("readiness"), f"{route} readiness")
    metrics = mapping(readiness.get("metrics"), f"{route} metrics")
    expected = number(metrics.get("imbalance_10"), f"{route} imbalance")
    age = number(metrics.get("pressure_age_seconds"), f"{route} pressure age")
    declared_maximum = number(
        metrics.get("maximum_pressure_age_seconds"), f"{route} maximum pressure age"
    )
    if (
        not math.isclose(
            declared_maximum, maximum_age, rel_tol=0.0, abs_tol=_IMBALANCE_TOLERANCE
        )
        or not 0.0 <= age <= maximum_age
    ):
        return []
    decision_ms = nonnegative_int(
        evaluation.get("decision_time_ms"), f"{route} decision time"
    )
    candidates = []
    for row in records:
        if not is_asset_event(row, identity, "book_observation"):
            continue
        book = _book_value(row)
        recv_ms = int(book["recv_ts_ms"])
        if not decision_ms <= recv_ms <= routing_ms:
            continue
        imbalance = float(book["imbalance_10"])
        if not math.isclose(
            imbalance, expected, rel_tol=0.0, abs_tol=_IMBALANCE_TOLERANCE
        ):
            continue
        cutoff = int(round(recv_ms + age * 1_000.0))
        if recv_ms <= cutoff <= routing_ms:
            candidates.append({**book, "derived_cutoff_time_ms": cutoff})
    return candidates


def _book_value(row: Record) -> dict[str, object]:
    payload = mapping(row.get("payload"), "book payload")
    if payload.get("source") != _BOOK_SOURCE:
        raise ValueError("HIP-3 book has an invalid source")
    recv_ms = nonnegative_int(payload.get("recv_ts_ms"), "book receive time")
    exchange_ms = nonnegative_int(payload.get("exchange_ts_ms"), "book exchange time")
    if exchange_ms > recv_ms:
        raise ValueError("HIP-3 book exchange time exceeds receive time")
    return {
        "sequence": nonnegative_int(row.get("sequence"), "book sequence"),
        "recv_ts_ms": recv_ms,
        "exchange_ts_ms": exchange_ms,
        "imbalance_10": _depth_imbalance(payload),
    }


def _depth_imbalance(payload: Record) -> float:
    bid = _depth_sum(payload.get("bids"), "bid")
    ask = _depth_sum(payload.get("asks"), "ask")
    total = bid + ask
    if total <= 0.0:
        raise ValueError("HIP-3 top-ten book depth must be positive")
    return (bid - ask) / total


def _depth_sum(raw: object, label: str) -> float:
    if not isinstance(raw, list) or len(raw) < 10:
        raise ValueError(f"HIP-3 {label} book requires ten levels")
    values = [
        number(mapping(level, f"{label} level").get("size"), f"{label} size")
        for level in raw[:10]
    ]
    if any(value <= 0.0 for value in values):
        raise ValueError(f"HIP-3 {label} sizes must be positive")
    return sum(values)


def _common_cutoff(
    candidates: Mapping[str, list[dict[str, object]]],
) -> tuple[int | None, dict[str, dict[str, object]]]:
    first = candidates.get(PRESSURE_ROUTES[0], [])
    for anchor in first:
        cutoff = int(anchor["derived_cutoff_time_ms"])
        selected = {PRESSURE_ROUTES[0]: anchor}
        for route in PRESSURE_ROUTES[1:]:
            match = next(
                (
                    value
                    for value in candidates.get(route, [])
                    if abs(int(value["derived_cutoff_time_ms"]) - cutoff)
                    <= _CUTOFF_TOLERANCE_MS
                ),
                None,
            )
            if match is None:
                break
            selected[route] = match
        if len(selected) == len(PRESSURE_ROUTES):
            return cutoff, selected
    return None, {}


def _latest_book_check(
    route: str,
    candidate: Record,
    cutoff_ms: int,
    assets: AssetRecords,
    identity: Record,
) -> tuple[dict[str, object], str | None]:
    symbol = route.split("|", maxsplit=1)[1]
    admissible = [
        _book_value(row)
        for row in assets[symbol]
        if is_asset_event(row, identity, "book_observation")
        and nonnegative_int(
            mapping(row.get("payload"), "book payload").get("recv_ts_ms"),
            "book receive time",
        )
        <= cutoff_ms
    ]
    latest = max(
        admissible, key=lambda value: (int(value["recv_ts_ms"]), int(value["sequence"]))
    )
    passed = latest["sequence"] == candidate["sequence"]
    return {
        "passed": passed,
        "symbol": symbol,
        "book_sequence": candidate["sequence"],
        "recv_ts_ms": candidate["recv_ts_ms"],
        "exchange_ts_ms": candidate["exchange_ts_ms"],
        "imbalance_10": candidate["imbalance_10"],
        "derived_cutoff_time_ms": candidate["derived_cutoff_time_ms"],
        "latest_admissible_sequence": latest["sequence"],
    }, None if passed else f"causal_book_not_latest:{route}"


def _funding_cursor(
    records: Sequence[Record],
    identity: Record,
    routing: Record,
    cutoff_ms: int | None,
) -> tuple[dict[str, object], list[str]]:
    rows = [
        row
        for row in records
        if is_run_event(row, identity, "funding_reconciliation_window")
    ]
    windows = [(_window(row), row) for row in rows]
    matches = [item for item in windows if item[0].provider_cutoff_time_ms == cutoff_ms]
    reasons: list[str] = []
    if len(matches) != 1:
        reasons.append("target_funding_window_missing")
        return _funding_report(False, windows, None), reasons
    target, target_row = matches[0]
    target_sequence = ledger_sequence(target_row, "funding")
    relevant = [
        item
        for item in windows
        if ledger_sequence(item[1], "funding") <= target_sequence
    ]
    relevant.sort(key=lambda item: ledger_sequence(item[1], "funding"))
    if not _cursor_contiguous([item[0] for item in relevant]):
        reasons.append("funding_cursor_gap_or_overlap")
    routing_sequence = nonnegative_int(routing.get("sequence"), "routing sequence")
    routings = [
        row
        for row in records
        if is_run_event(row, identity, "intent_routing")
        and ledger_sequence(row, "routing") <= routing_sequence
    ]
    routings.sort(key=lambda row: ledger_sequence(row, "routing"))
    if len(routings) != len(relevant):
        reasons.append("funding_window_count_mismatch")
    if not _window_order_valid(routings, relevant):
        reasons.append("funding_window_order_invalid")
    return _funding_report(not reasons, relevant, target), reasons


def _window(row: Record) -> CohortFundingWindow:
    return funding_window_from_payload(row.get("payload"))


def _cursor_contiguous(windows: Sequence[CohortFundingWindow]) -> bool:
    return all(
        previous.next_funding_start_time_ms == current.funding_start_time_ms
        for previous, current in zip(windows, windows[1:], strict=False)
    )


def _window_order_valid(
    routings: Sequence[Record],
    windows: Sequence[tuple[CohortFundingWindow, Record]],
) -> bool:
    if len(routings) != len(windows):
        return False
    for index, (routing, (_, window)) in enumerate(zip(routings, windows, strict=True)):
        routing_sequence = ledger_sequence(routing, "routing")
        window_sequence = ledger_sequence(window, "funding")
        next_routing = (
            ledger_sequence(routings[index + 1], "routing")
            if index + 1 < len(routings)
            else None
        )
        if window_sequence <= routing_sequence:
            return False
        if next_routing is not None and window_sequence >= next_routing:
            return False
    return True


def _funding_report(
    passed: bool,
    windows: Sequence[tuple[CohortFundingWindow, Record]],
    target: CohortFundingWindow | None,
) -> dict[str, object]:
    return {
        "passed": passed,
        "windows": len(windows),
        "first_funding_start_time_ms": (
            windows[0][0].funding_start_time_ms if windows else None
        ),
        "target_committed_funding_end_time_ms": (
            target.committed_funding_end_time_ms if target is not None else None
        ),
        "target_provider_cutoff_time_ms": (
            target.provider_cutoff_time_ms if target is not None else None
        ),
        "boundary_semantics": _BOUNDARY_SEMANTICS,
    }


def _funding_payments(
    assets: AssetRecords,
    identity: Record,
    funding: Record,
    symbols: Sequence[str],
) -> tuple[dict[str, object], list[str]]:
    lower = funding.get("first_funding_start_time_ms")
    upper = funding.get("target_committed_funding_end_time_ms")
    counts: dict[str, int] = {}
    reasons: list[str] = []
    for symbol in symbols:
        keys: set[tuple[str, int]] = set()
        rows = assets.get(symbol)
        if rows is None:
            reasons.append(f"asset_ledger_missing:{symbol}")
            counts[symbol] = 0
            continue
        for row in rows:
            if not is_asset_event(row, identity, "funding"):
                continue
            payload = mapping(row.get("payload"), f"{symbol} funding")
            key = (
                text(payload.get("transaction_hash"), "funding transaction hash"),
                nonnegative_int(payload.get("venue_timestamp_ms"), "funding time"),
            )
            if key in keys:
                reasons.append(f"duplicate_funding_payment:{symbol}")
            keys.add(key)
            if isinstance(lower, int) and isinstance(upper, int):
                if not lower <= key[1] <= upper:
                    reasons.append(f"funding_payment_outside_committed_window:{symbol}")
        counts[symbol] = len(keys)
    return {"passed": not reasons, "unique_payments_by_symbol": counts}, reasons
