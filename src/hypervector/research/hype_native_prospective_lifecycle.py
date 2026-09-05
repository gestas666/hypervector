"""Exact-contract prospective lifecycle evidence for HYPE-native v54."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    object_list,
    payload,
    text,
    text_list,
    timestamp,
)
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    first_book,
    first_stop_book,
    latest_book_time,
    post_entry_books,
    protective_stop_price,
    validated_books,
    visible_depth_fill,
)
from hypervector.research.cohort_observer_exact_books import (
    extract_observer_asset_books,
    select_report_only_observer_run,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)
from hypervector.research.hype_native_prospective_metrics import (
    attempt_payload,
    lifecycle_payload,
    proxy_summary,
    report_status,
)
from hypervector.research.hype_native_baseline_comparison import (
    build_hype_native_baseline_comparisons,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class HypeNativeProspectiveSpec:
    """Frozen identity, execution, and evidence bounds for v54 observation."""

    run_id: str
    profile_id: str
    profile_fingerprint: str
    run_fingerprint: str
    strategy_id: str
    symbol: str
    notional_usd: float
    stop_bps: float
    maximum_hold_seconds: int
    maximum_entry_delay_ms: int
    maximum_exit_delay_ms: int
    fee_bps_per_side: float
    residual_slippage_bps_per_side: float
    maximum_book_gap_ms: int

    def __post_init__(self) -> None:
        """Reject incomplete identities or invalid economic assumptions."""
        _validate_spec(self)


@dataclass(frozen=True)
class _ExitOnset:
    decision_time_ms: int
    available_time_ms: int


def build_hype_native_prospective_report(
    records: Sequence[Record],
    spec: HypeNativeProspectiveSpec,
) -> dict[str, object]:
    """Measure eligible v54 long signals without constructing execution authority."""
    selected, identity = select_report_only_observer_run(records, spec.run_id)
    _require_runtime_identity(identity, spec)
    _require_provider_contract(identity, spec)
    extracted = extract_observer_asset_books(selected, (spec.symbol,))
    books = validated_books(
        extracted[spec.symbol],
        symbol=spec.symbol,
        run_ids=(spec.run_id,),
    )
    candidates, excluded, conflicts = evaluation_candidates(selected)
    entries = [
        row
        for row in candidates
        if row.strategy_id == spec.strategy_id
        and row.symbol == spec.symbol
        and row.eligible
    ]
    exits = _exit_only_rows(selected, spec)
    attempts, lifecycles = _replay(entries, exits, books, spec)
    comparisons = build_hype_native_baseline_comparisons(selected, entries)
    status = report_status(entries, lifecycles)
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_prospective_lifecycle_report_only",
        "status": status,
        "contract": _contract(spec),
        "identity": _identity(spec),
        "signal_counts": {
            "eligible_long_entries": len(entries),
            "exit_only_short_onsets": len(exits),
        },
        "candidate_parser_evidence": {
            "excluded_pre_activation": excluded,
            "direction_conflicts": conflicts,
        },
        "attempts": attempts,
        "lifecycles": lifecycles,
        "baseline_comparisons": comparisons,
        "resolved_proxy_summary": proxy_summary(lifecycles),
    }


def _exit_only_rows(
    records: Sequence[Record], spec: HypeNativeProspectiveSpec
) -> tuple[_ExitOnset, ...]:
    result: dict[int, _ExitOnset] = {}
    for row in event_rows(records, "intent_routing"):
        for evaluation in object_list(payload(row), "evaluations", required=False):
            if (
                evaluation.get("strategy_id") == spec.strategy_id
                and evaluation.get("symbol") == spec.symbol
                and evaluation.get("reason") == "opposite_native_onset_exit_only"
            ):
                onset = _exit_onset(row, evaluation)
                prior = result.get(onset.decision_time_ms)
                if prior is not None and prior != onset:
                    raise ValueError("conflicting duplicate HYPE exit-only onset")
                result[onset.decision_time_ms] = onset
    return tuple(sorted(result.values(), key=lambda row: row.available_time_ms))


def _exit_onset(row: Record, evaluation: Record) -> _ExitOnset:
    if (
        evaluation.get("eligible") is not False
        or evaluation.get("side") != "short"
        or evaluation.get("decision_action") != "close_long"
        or evaluation.get("exit_reason") != "opposite_native_onset"
        or text_list(evaluation.get("exit_sides"), "HYPE exit sides") != ["long"]
    ):
        raise ValueError("HYPE exit-only onset contract is invalid")
    decision = nonnegative_int(
        evaluation.get("decision_time_ms"), "HYPE exit decision time"
    )
    available = int(timestamp(row).timestamp() * 1_000)
    if available < decision:
        raise ValueError("HYPE exit-only onset predates its decision")
    return _ExitOnset(decision, available)


def _replay(
    entries: Sequence[SignalCandidate],
    exits: Sequence[_ExitOnset],
    books: Sequence[Record],
    spec: HypeNativeProspectiveSpec,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    attempts: list[dict[str, object]] = []
    lifecycles: list[dict[str, object]] = []
    occupied_until = -1
    for entry in sorted(entries, key=lambda row: row.available_time_ms):
        if entry.available_time_ms < occupied_until:
            attempts.append(attempt_payload(entry, "occupied_by_prior_lifecycle"))
            continue
        attempt, lifecycle, occupied_until = _evaluate_entry(entry, exits, books, spec)
        attempts.append(attempt)
        if lifecycle is not None:
            lifecycles.append(lifecycle)
    return attempts, lifecycles


def _evaluate_entry(
    candidate: SignalCandidate,
    exits: Sequence[_ExitOnset],
    books: Sequence[Record],
    spec: HypeNativeProspectiveSpec,
) -> tuple[dict[str, object], dict[str, object] | None, int]:
    if candidate.side != "long":
        raise ValueError("prospective HYPE candidate attempted a non-long entry")
    entry = first_book(books, candidate.available_time_ms, spec.maximum_entry_delay_ms)
    if entry is None:
        return attempt_payload(candidate, "entry_book_unavailable"), None, -1
    entry_fill = visible_depth_fill(
        entry, position_side="long", notional=spec.notional_usd, quantity=None
    )
    if entry_fill.get("complete") is not True:
        return attempt_payload(candidate, "entry_depth_insufficient"), None, -1
    lifecycle = _entered_lifecycle(candidate, entry, entry_fill, exits, books, spec)
    occupied_until = int(lifecycle["occupancy_end_time_ms"])
    return (
        attempt_payload(candidate, str(lifecycle["status"])),
        lifecycle,
        occupied_until,
    )


def _entered_lifecycle(
    candidate: SignalCandidate,
    entry: Record,
    entry_fill: Record,
    exits: Sequence[_ExitOnset],
    books: Sequence[Record],
    spec: HypeNativeProspectiveSpec,
) -> dict[str, object]:
    deadline = book_time(entry) + spec.maximum_hold_seconds * 1_000
    path = post_entry_books(books, book_time(entry), deadline)
    stop_price = protective_stop_price(
        "long", float(entry_fill["price"]), spec.stop_bps
    )
    stop = first_stop_book(path, side="long", stop_price=stop_price)
    opposite = _opposite_exit(exits, books, book_time(entry), deadline, spec)
    maximum_hold = (
        first_book(books, deadline, spec.maximum_exit_delay_ms)
        if latest_book_time(books) >= deadline
        else None
    )
    reason, exit_book = _first_exit(stop, opposite, maximum_hold)
    current = exit_book or books[-1]
    return lifecycle_payload(
        candidate,
        entry,
        entry_fill,
        current,
        exit_book,
        reason,
        stop_price,
        books,
        spec,
    )


def _opposite_exit(
    exits: Sequence[_ExitOnset],
    books: Sequence[Record],
    entry_time_ms: int,
    deadline_ms: int,
    spec: HypeNativeProspectiveSpec,
) -> Record | None:
    onset = next(
        (row for row in exits if entry_time_ms < row.available_time_ms <= deadline_ms),
        None,
    )
    return (
        first_book(books, onset.available_time_ms, spec.maximum_exit_delay_ms)
        if onset is not None
        else None
    )


def _first_exit(
    stop: Record | None,
    opposite: Record | None,
    maximum_hold: Record | None,
) -> tuple[str | None, Record | None]:
    options = [
        ("protective_stop_bbo_proxy", stop, 0),
        ("opposite_native_onset", opposite, 1),
        ("maximum_hold", maximum_hold, 2),
    ]
    available = [row for row in options if row[1] is not None]
    if not available:
        return None, None
    reason, book, _ = min(available, key=lambda row: (book_time(row[1]), row[2]))
    return reason, book


def _require_runtime_identity(
    identity: Record, spec: HypeNativeProspectiveSpec
) -> None:
    for field, expected in (
        ("profile_id", spec.profile_id),
        ("profile_fingerprint", spec.profile_fingerprint),
        ("run_fingerprint", spec.run_fingerprint),
    ):
        if identity.get(field) != expected:
            raise ValueError(f"prospective HYPE observer {field} differs")


def _require_provider_contract(
    identity: Record, spec: HypeNativeProspectiveSpec
) -> None:
    values = payload(identity)
    providers = [
        row
        for row in object_list(values, "providers")
        if row.get("strategy_id") == spec.strategy_id
        and spec.symbol in text_list(row.get("symbols"), "provider symbols")
    ]
    if len(providers) != 1:
        raise ValueError("prospective HYPE provider contract must resolve once")
    provider = providers[0]
    overrides = mapping(
        provider.get("execution_side_overrides"),
        "provider execution side overrides",
    )
    if text_list(overrides.get(spec.symbol), "HYPE execution sides") != ["long"]:
        raise ValueError("prospective HYPE provider must execute long entries only")
    execution = mapping(provider.get("execution"), "provider execution")
    _require_execution(execution, spec)


def _require_execution(execution: Record, spec: HypeNativeProspectiveSpec) -> None:
    expected = {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "target_policy": "none",
        "maximum_hold_policy": "fixed",
        "provider_recipe_exit_policy": "honor",
        "maximum_hold_seconds": spec.maximum_hold_seconds,
        "stop_bps": spec.stop_bps,
    }
    if any(execution.get(field) != value for field, value in expected.items()):
        raise ValueError("prospective HYPE execution contract differs from v54")


def _contract(spec: HypeNativeProspectiveSpec) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "realized_pnl_claimed": False,
        "orders_or_fills_assumed": False,
        "funding_included": False,
        "mark_stop_truth_included": False,
        "entry_sides": ["long"],
        "native_short_onset_exit": True,
        "execution": asdict(spec),
    }


def _identity(spec: HypeNativeProspectiveSpec) -> dict[str, str]:
    return {
        "run_id": spec.run_id,
        "profile_id": spec.profile_id,
        "profile_fingerprint": spec.profile_fingerprint,
        "run_fingerprint": spec.run_fingerprint,
        "strategy_id": spec.strategy_id,
        "symbol": spec.symbol,
    }


def _validate_spec(spec: HypeNativeProspectiveSpec) -> None:
    for value, label in (
        (spec.run_id, "run id"),
        (spec.profile_id, "profile id"),
        (spec.profile_fingerprint, "profile fingerprint"),
        (spec.run_fingerprint, "run fingerprint"),
        (spec.strategy_id, "strategy id"),
    ):
        text(value, label)
    if spec.symbol != "HYPE":
        raise ValueError("prospective HYPE lifecycle requires exact HYPE")
    for value, label in (
        (spec.notional_usd, "notional"),
        (spec.stop_bps, "stop bps"),
    ):
        _positive(value, label)
    for value, label in (
        (spec.maximum_hold_seconds, "maximum hold"),
        (spec.maximum_entry_delay_ms, "entry delay"),
        (spec.maximum_exit_delay_ms, "exit delay"),
        (spec.maximum_book_gap_ms, "maximum book gap"),
    ):
        _positive_integer(value, label)
    _nonnegative(spec.fee_bps_per_side, "fee bps")
    _nonnegative(spec.residual_slippage_bps_per_side, "slippage bps")


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


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    return output


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
