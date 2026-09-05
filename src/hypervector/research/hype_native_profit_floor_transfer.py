"""Report-only transfer test for the frozen HYPE mature-profit floor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from hypervector.cohort_profit_lock_policy import (
    ProfitLockPolicy,
    evaluate_profit_lock_path,
    policy_declaration,
)
from hypervector.research.cohort_exact_depth_books import (
    book_time,
    first_book,
    validated_books,
    visible_depth_fill,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_MAXIMUM_EXIT_DELAY_MS = 60_000
_FEE_BPS_PER_SIDE = 4.32
_SLIPPAGE_BPS_PER_SIDE = 2.0
_POLICY = ProfitLockPolicy("a100_floor25_only", 100.0, 25.0, 10_000.0)


@dataclass(frozen=True)
class FundingCashflow:
    """One exact official funding cashflow for the frozen quantity."""

    timestamp_ms: int
    cashflow_usd: float

    def __post_init__(self) -> None:
        """Reject invalid funding evidence."""
        if (
            isinstance(self.timestamp_ms, bool)
            or self.timestamp_ms < 0
            or not math.isfinite(self.cashflow_usd)
        ):
            raise ValueError("HYPE floor funding cashflow is invalid")


@dataclass(frozen=True)
class NativeLifecycle:
    """One frozen native-HYPE lifecycle and its natural-exit economics."""

    lifecycle_id: str
    entry_time_ms: int
    natural_exit_time_ms: int | None
    as_of_ms: int
    entry_price: float
    quantity: float
    actual_net_after_funding_usd: float | None
    actual_exit_reason: str | None
    funding_cashflows: tuple[FundingCashflow, ...]
    funding_complete_through_ms: int | None

    def __post_init__(self) -> None:
        """Reject internally inconsistent lifecycle evidence."""
        _validate_lifecycle(self)


@dataclass(frozen=True)
class ProfitFloorBar:
    """One source-native completed one-minute candle."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float


def build_hype_native_profit_floor_transfer(
    lifecycles: Sequence[NativeLifecycle],
    bars_by_lifecycle: Mapping[str, Sequence[ProfitFloorBar]],
    books_by_lifecycle: Mapping[str, Sequence[Record]],
) -> dict[str, object]:
    """Score one frozen floor without changing entries or live authority."""
    _validate_collection(lifecycles, bars_by_lifecycle, books_by_lifecycle)
    outcomes = [
        _lifecycle_outcome(
            lifecycle,
            tuple(bars_by_lifecycle[lifecycle.lifecycle_id]),
            tuple(books_by_lifecycle[lifecycle.lifecycle_id]),
        )
        for lifecycle in lifecycles
    ]
    comparison = _comparison(outcomes)
    return {
        "schema_version": 1,
        "mode": "hype_native_mature_profit_floor_transfer_v1",
        "contract": _contract(),
        "policy": policy_declaration(_POLICY),
        "lifecycles": outcomes,
        "comparison": comparison,
        "limitations": _limitations(str(comparison["status"])),
    }


def _lifecycle_outcome(
    lifecycle: NativeLifecycle,
    bars: tuple[ProfitFloorBar, ...],
    raw_books: tuple[Record, ...],
) -> dict[str, object]:
    path = _continuous_completed_path(lifecycle, bars)
    state = evaluate_profit_lock_path(_POLICY, "long", path, lifecycle.entry_price)
    base = _base_outcome(lifecycle, state)
    if state.trigger is None:
        return _untriggered_outcome(lifecycle, base)
    decision_time = state.trigger.trigger_timestamp_ms + _MINUTE_MS
    books = _validated_book_rows(raw_books)
    exit_book = first_book(books, decision_time, _MAXIMUM_EXIT_DELAY_MS)
    if exit_book is None:
        return {**base, "status": "withheld_exit_book_delay"}
    fill = visible_depth_fill(
        exit_book, position_side="long", notional=0.0, quantity=lifecycle.quantity
    )
    if fill.get("complete") is not True:
        return {**base, "status": "withheld_exit_depth"}
    return _triggered_outcome(lifecycle, base, exit_book, fill)


def _triggered_outcome(
    lifecycle: NativeLifecycle,
    base: dict[str, object],
    exit_book: Record,
    fill: Record,
) -> dict[str, object]:
    exit_time = book_time(exit_book)
    exit_price = _number(fill.get("price"), "exit price")
    exit_quote = _number(fill.get("quote_usd"), "exit quote")
    entry_quote = lifecycle.entry_price * lifecycle.quantity
    gross = (exit_price - lifecycle.entry_price) * lifecycle.quantity
    turnover = entry_quote + exit_quote
    fees = turnover * _FEE_BPS_PER_SIDE / 10_000.0
    slippage = turnover * _SLIPPAGE_BPS_PER_SIDE / 10_000.0
    before_funding = gross - fees - slippage
    funding = _funding_through(lifecycle, exit_time)
    after_funding = None if funding is None else before_funding + funding
    status = _triggered_status(lifecycle, after_funding)
    return {
        **base,
        "status": status,
        "exit_book_time_ms": exit_time,
        "exit_price": exit_price,
        "exit_levels_consumed": fill.get("levels_consumed"),
        "estimated_fees_usd": fees,
        "estimated_residual_slippage_usd": slippage,
        "estimated_net_before_funding_usd": before_funding,
        "estimated_funding_cashflow_usd": funding,
        "estimated_net_after_funding_usd": after_funding,
    }


def _untriggered_outcome(
    lifecycle: NativeLifecycle, base: dict[str, object]
) -> dict[str, object]:
    actual = lifecycle.actual_net_after_funding_usd
    return {
        **base,
        "status": "resolved_not_triggered"
        if actual is not None
        else "open_not_triggered",
        "estimated_net_before_funding_usd": None,
        "estimated_funding_cashflow_usd": None,
        "estimated_net_after_funding_usd": actual,
    }


def _base_outcome(lifecycle: NativeLifecycle, state: object) -> dict[str, object]:
    trigger = getattr(state, "trigger")
    return {
        "lifecycle_id": lifecycle.lifecycle_id,
        "entry_time_ms": lifecycle.entry_time_ms,
        "natural_exit_time_ms": lifecycle.natural_exit_time_ms,
        "actual_exit_reason": lifecycle.actual_exit_reason,
        "actual_net_after_funding_usd": lifecycle.actual_net_after_funding_usd,
        "activation_bar_ms": getattr(state, "activation_timestamp_ms"),
        "trigger_bar_ms": getattr(trigger, "trigger_timestamp_ms", None),
        "decision_time_ms": (
            None
            if trigger is None
            else getattr(trigger, "trigger_timestamp_ms") + _MINUTE_MS
        ),
        "exit_book_time_ms": None,
        "exit_price": None,
        "exit_levels_consumed": None,
        "estimated_net_before_funding_usd": None,
        "estimated_funding_cashflow_usd": None,
        "estimated_net_after_funding_usd": None,
    }


def _continuous_completed_path(
    lifecycle: NativeLifecycle, bars: tuple[ProfitFloorBar, ...]
) -> tuple[ProfitFloorBar, ...]:
    boundary = lifecycle.natural_exit_time_ms or lifecycle.as_of_ms
    first = lifecycle.entry_time_ms // _MINUTE_MS * _MINUTE_MS + _MINUTE_MS
    last = (boundary - _MINUTE_MS) // _MINUTE_MS * _MINUTE_MS
    expected = tuple(range(first, last + _MINUTE_MS, _MINUTE_MS))
    actual = tuple(bar.timestamp_ms for bar in bars)
    if actual != expected:
        raise ValueError("HYPE floor requires a continuous completed one-minute path")
    return bars


def _validated_book_rows(rows: tuple[Record, ...]) -> tuple[Record, ...]:
    if not rows:
        return ()
    run_ids = tuple(dict.fromkeys(str(row.get("run_id")) for row in rows))
    return validated_books(rows, symbol="HYPE", run_ids=run_ids)


def _funding_through(lifecycle: NativeLifecycle, exit_time_ms: int) -> float | None:
    if (
        lifecycle.funding_complete_through_ms is None
        or lifecycle.funding_complete_through_ms < exit_time_ms
    ):
        return None
    return sum(
        row.cashflow_usd
        for row in lifecycle.funding_cashflows
        if lifecycle.entry_time_ms < row.timestamp_ms <= exit_time_ms
    )


def _triggered_status(
    lifecycle: NativeLifecycle, estimated_after_funding: float | None
) -> str:
    if lifecycle.actual_net_after_funding_usd is None:
        return "provisional_trigger_funding_pending"
    if estimated_after_funding is None:
        return "withheld_funding_incomplete"
    return "resolved_triggered"


def _comparison(outcomes: Sequence[Record]) -> dict[str, object]:
    statuses = {str(row.get("status")) for row in outcomes}
    unresolved = any(status.startswith("withheld_") for status in statuses)
    provisional = any(
        status.startswith("open_") or status.startswith("provisional_")
        for status in statuses
    )
    complete = not unresolved and not provisional
    actual = _complete_values(outcomes, "actual_net_after_funding_usd")
    floor = _complete_values(outcomes, "estimated_net_after_funding_usd")
    return {
        "status": "technically_unresolved"
        if unresolved
        else ("provisional_open_lifecycle" if provisional else "complete"),
        "trades": len(outcomes),
        "triggered": sum(row.get("trigger_bar_ms") is not None for row in outcomes),
        "native_net_after_funding_usd": sum(actual) if complete else None,
        "floor_net_after_funding_usd": sum(floor) if complete else None,
        "floor_minus_native_net_usd": (sum(floor) - sum(actual) if complete else None),
        "floor_net_excluding_largest_winner_usd": (
            _excluding_largest(floor) if complete else None
        ),
        "floor_profit_factor": _profit_factor(floor) if complete else None,
    }


def _complete_values(rows: Sequence[Record], field: str) -> list[float]:
    values = [row.get(field) for row in rows]
    return [_number(value, field) for value in values if value is not None]


def _excluding_largest(values: Sequence[float]) -> float:
    return sum(values) - max((value for value in values if value > 0.0), default=0.0)


def _profit_factor(values: Sequence[float]) -> float | None:
    gain = sum(value for value in values if value > 0.0)
    loss = -sum(value for value in values if value < 0.0)
    return None if loss == 0.0 else gain / loss


def _validate_collection(
    lifecycles: Sequence[NativeLifecycle],
    bars: Mapping[str, Sequence[ProfitFloorBar]],
    books: Mapping[str, Sequence[Record]],
) -> None:
    identities = tuple(row.lifecycle_id for row in lifecycles)
    if not identities or len(identities) != len(set(identities)):
        raise ValueError("HYPE floor lifecycles must be unique and non-empty")
    if set(identities) != set(bars) or set(identities) != set(books):
        raise ValueError("HYPE floor evidence identities differ")


def _validate_lifecycle(value: NativeLifecycle) -> None:
    valid_exit = value.natural_exit_time_ms is None or (
        value.entry_time_ms < value.natural_exit_time_ms <= value.as_of_ms
    )
    valid = (
        bool(value.lifecycle_id)
        and not isinstance(value.entry_time_ms, bool)
        and 0 <= value.entry_time_ms < value.as_of_ms
        and valid_exit
        and math.isfinite(value.entry_price)
        and math.isfinite(value.quantity)
        and min(value.entry_price, value.quantity) > 0.0
        and (
            value.actual_net_after_funding_usd is None
            or math.isfinite(value.actual_net_after_funding_usd)
        )
    )
    if not valid:
        raise ValueError("HYPE floor lifecycle is invalid")


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HYPE floor {label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"HYPE floor {label} must be finite")
    return result


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "entry_strategy_changed": False,
        "selection_performed": False,
        "fee_bps_per_side": _FEE_BPS_PER_SIDE,
        "residual_slippage_bps_per_side": _SLIPPAGE_BPS_PER_SIDE,
        "maximum_exit_delay_ms": _MAXIMUM_EXIT_DELAY_MS,
    }


def _limitations(status: str) -> list[str]:
    limitations = [
        "the floor was developed on compression entries and is transferred to native entries",
        "recorded books are finite-depth counterfactuals rather than private venue fills",
        "this report cannot route, resize, configure, close, or submit a live trade",
    ]
    if status == "provisional_open_lifecycle":
        limitations.append(
            "the current lifecycle remains provisional until its natural exit and funding resolve"
        )
    return limitations
