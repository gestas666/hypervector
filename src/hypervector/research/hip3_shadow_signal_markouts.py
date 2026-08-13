"""Report-only executable-BBO markouts for prospective HIP-3 onsets."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import math
from statistics import mean, median
from typing import cast

_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class Hip3ShadowMarkoutConfig:
    """Frozen route, friction, and causal quote boundaries."""

    symbol: str
    provider_id: str
    profile_id: str
    ledger_profile_id: str
    fee_bps_per_side: float
    residual_latency_bps_per_side: float
    friction_source: str
    horizons_minutes: tuple[int, ...]
    maximum_book_lateness_ms: int

    def __post_init__(self) -> None:
        """Reject aliased identities or unsupported numeric assumptions."""
        if not self.symbol.startswith("xyz:"):
            raise ValueError("HIP-3 markout symbol must use the xyz namespace")
        token = self.symbol.removeprefix("xyz:").lower()
        identities = (self.provider_id, self.profile_id, self.ledger_profile_id)
        if any(not value or token not in value.lower() for value in identities):
            raise ValueError("HIP-3 markout route identity is inconsistent")
        costs = (self.fee_bps_per_side, self.residual_latency_bps_per_side)
        if any(not math.isfinite(value) or value < 0.0 for value in costs):
            raise ValueError("HIP-3 markout friction must be finite and nonnegative")
        if not self.friction_source:
            raise ValueError("HIP-3 markout friction source is required")
        if not self.horizons_minutes or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in self.horizons_minutes
        ):
            raise ValueError("HIP-3 markout horizons must be positive integers")
        if len(set(self.horizons_minutes)) != len(self.horizons_minutes):
            raise ValueError("HIP-3 markout horizons must be unique")
        _positive_integer(self.maximum_book_lateness_ms, "maximum book lateness")


@dataclass(frozen=True)
class _Decision:
    event_id: str
    decision_time_ms: int
    observed_at_ms: int
    side: str


@dataclass(frozen=True)
class _Book:
    recv_ts_ms: int
    best_bid: float
    best_ask: float


@dataclass(frozen=True)
class _Outcome:
    decision_time_ms: int
    signal_available_time_ms: int
    entry_book_time_ms: int
    exit_book_time_ms: int
    horizon_minutes: int
    side: str
    entry_price: float
    exit_price: float
    gross_bbo_bps: float
    after_fee_bps: float
    after_modeled_friction_bps: float


def build_hip3_shadow_signal_markouts(
    *,
    decision_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    config: Hip3ShadowMarkoutConfig,
) -> dict[str, object]:
    """Measure causal post-publication BBO paths without claiming fills."""
    decisions = _decisions(decision_rows, config)
    books = _books(book_rows, config)
    horizons = {
        str(horizon): _horizon(decisions, books, horizon, config)
        for horizon in sorted(config.horizons_minutes)
    }
    return {
        "schema_version": "hip3_shadow_signal_markouts_v1",
        "symbol": config.symbol,
        "provider_id": config.provider_id,
        "profile_id": config.profile_id,
        "execution_authority": "none",
        "report_only": True,
        "contract": _contract(config),
        "source": {
            "decision_rows": len(decision_rows),
            "eligible_onset_decisions": len(decisions),
            "book_rows": len(book_rows),
        },
        "markouts": {"horizons": horizons},
        "limitations": _limitations(),
    }


def _decisions(
    rows: Sequence[Mapping[str, object]], config: Hip3ShadowMarkoutConfig
) -> tuple[_Decision, ...]:
    seen: set[str] = set()
    output: list[_Decision] = []
    for row in rows:
        event_id = _text(row.get("event_id"), "decision event id")
        if event_id in seen:
            raise ValueError("HIP-3 markout contains a duplicate decision")
        seen.add(event_id)
        decision = _decision(row, config, event_id)
        if decision is not None:
            output.append(decision)
    ordered = sorted(output, key=lambda value: value.observed_at_ms)
    return tuple(ordered)


def _decision(
    row: Mapping[str, object],
    config: Hip3ShadowMarkoutConfig,
    event_id: str,
) -> _Decision | None:
    token = config.symbol.removeprefix("xyz:").lower()
    if row.get("event_type") != f"{token}_hip3_breakout_shadow_decision":
        raise ValueError("HIP-3 markout decision event type is inconsistent")
    if not _report_only(row) or row.get("intents") != []:
        raise ValueError("HIP-3 markout decision authority is invalid")
    value = _mapping(row.get("decision"), "decision")
    _require_decision_identity(value, config)
    if value.get("eligible") is not True:
        return None
    if value.get("prospective") is not True or any(
        value.get(name) is not True
        for name in (
            "pressure_fresh",
            "pressure_scan_complete",
            "pressure_state_history_complete",
        )
    ):
        raise ValueError("eligible HIP-3 markout decision lacks causal evidence")
    side = _text(value.get("side"), "decision side")
    if side not in {"long", "short"}:
        raise ValueError("eligible HIP-3 markout side is invalid")
    decision_ms = _nonnegative_integer(value.get("decision_time_ms"), "decision time")
    observed_ms = _nonnegative_integer(value.get("observed_at_ms"), "observed time")
    if not 0 <= observed_ms - decision_ms <= 15_000:
        raise ValueError("eligible HIP-3 markout was published outside its boundary")
    return _Decision(event_id, decision_ms, observed_ms, side)


def _require_decision_identity(
    value: Mapping[str, object], config: Hip3ShadowMarkoutConfig
) -> None:
    expected = {
        "symbol": config.symbol,
        "provider_id": config.provider_id,
        "profile_id": config.profile_id,
        "execution_authority": "none",
    }
    if any(
        value.get(name) != expected_value for name, expected_value in expected.items()
    ):
        raise ValueError("HIP-3 markout decision identity is inconsistent")


def _books(
    rows: Sequence[Mapping[str, object]], config: Hip3ShadowMarkoutConfig
) -> tuple[_Book, ...]:
    output = tuple(_book(row, config) for row in rows)
    ordered = tuple(sorted(output, key=lambda value: value.recv_ts_ms))
    timestamps = [value.recv_ts_ms for value in ordered]
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("HIP-3 markout book receive timestamps must be unique")
    return ordered


def _book(row: Mapping[str, object], config: Hip3ShadowMarkoutConfig) -> _Book:
    if row.get("event_type") != "book_observation":
        raise ValueError("HIP-3 markout book event type is invalid")
    if row.get("profile_id") != config.ledger_profile_id:
        raise ValueError("HIP-3 markout book profile is inconsistent")
    if row.get("execution_authority") != "none":
        raise ValueError("HIP-3 markout book authority is invalid")
    payload = _mapping(row.get("payload"), "book payload")
    if payload.get("symbol") != config.symbol:
        raise ValueError("HIP-3 markout book symbol is inconsistent")
    if payload.get("source") != _BOOK_SOURCE:
        raise ValueError("HIP-3 markout book source is inconsistent")
    exchange_ms = _nonnegative_integer(payload.get("exchange_ts_ms"), "exchange time")
    recv_ms = _nonnegative_integer(payload.get("recv_ts_ms"), "receipt time")
    if recv_ms < exchange_ms:
        raise ValueError("HIP-3 markout book receipt precedes exchange time")
    bids = _levels(payload.get("bids"), "bids", descending=True)
    asks = _levels(payload.get("asks"), "asks", descending=False)
    if bids[0] >= asks[0]:
        raise ValueError("HIP-3 markout book is crossed")
    return _Book(recv_ms, bids[0], asks[0])


def _levels(value: object, label: str, *, descending: bool) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) < 10:
        raise ValueError(f"HIP-3 markout {label} require ten levels")
    prices: list[float] = []
    for raw in value[:10]:
        level = _mapping(raw, f"{label} level")
        price = _positive_number(level.get("price"), f"{label} price")
        _positive_number(level.get("size"), f"{label} size")
        prices.append(price)
    comparisons = zip(prices, prices[1:])
    ordered = (
        all(left > right for left, right in comparisons)
        if descending
        else all(left < right for left, right in comparisons)
    )
    if not ordered:
        raise ValueError(f"HIP-3 markout {label} are not strictly ordered")
    return tuple(prices)


def _horizon(
    decisions: Sequence[_Decision],
    books: Sequence[_Book],
    horizon: int,
    config: Hip3ShadowMarkoutConfig,
) -> dict[str, object]:
    coverage = _coverage(len(decisions))
    outcomes: list[_Outcome] = []
    timestamps = [value.recv_ts_ms for value in books]
    for decision in decisions:
        entry_status, entry = _at_or_after(
            books, timestamps, decision.observed_at_ms, config.maximum_book_lateness_ms
        )
        if entry is None:
            coverage[f"entry_{entry_status}"] += 1
            continue
        coverage["entry_matched"] += 1
        exit_status, exit_book = _at_or_after(
            books,
            timestamps,
            entry.recv_ts_ms + horizon * _MINUTE_MS,
            config.maximum_book_lateness_ms,
        )
        if exit_book is None:
            coverage[f"exit_{exit_status}"] += 1
            continue
        coverage["resolved"] += 1
        outcomes.append(_outcome(decision, entry, exit_book, horizon, config))
    independent = _independent(outcomes, horizon)
    return {
        "coverage": coverage,
        "resolved_paths": [asdict(value) for value in outcomes],
        "independent_paths": [asdict(value) for value in independent],
        "summary": _summary(independent),
    }


def _coverage(eligible: int) -> dict[str, int]:
    return {
        "eligible_signals": eligible,
        "entry_matched": 0,
        "entry_censored": 0,
        "entry_gap": 0,
        "resolved": 0,
        "exit_censored": 0,
        "exit_gap": 0,
    }


def _at_or_after(
    books: Sequence[_Book],
    timestamps: Sequence[int],
    target_ms: int,
    maximum_lateness_ms: int,
) -> tuple[str, _Book | None]:
    position = bisect_left(timestamps, target_ms)
    if position >= len(books):
        return "censored", None
    book = books[position]
    if book.recv_ts_ms - target_ms > maximum_lateness_ms:
        return "gap", None
    return "matched", book


def _outcome(
    decision: _Decision,
    entry: _Book,
    exit_book: _Book,
    horizon: int,
    config: Hip3ShadowMarkoutConfig,
) -> _Outcome:
    long = decision.side == "long"
    entry_price = entry.best_ask if long else entry.best_bid
    exit_price = exit_book.best_bid if long else exit_book.best_ask
    direction = 1.0 if long else -1.0
    gross = direction * (exit_price / entry_price - 1.0) * 10_000.0
    scale = 1.0 + exit_price / entry_price
    after_fee = gross - config.fee_bps_per_side * scale
    after_modeled = after_fee - config.residual_latency_bps_per_side * scale
    return _Outcome(
        decision.decision_time_ms,
        decision.observed_at_ms,
        entry.recv_ts_ms,
        exit_book.recv_ts_ms,
        horizon,
        decision.side,
        entry_price,
        exit_price,
        gross,
        after_fee,
        after_modeled,
    )


def _independent(outcomes: Sequence[_Outcome], horizon: int) -> tuple[_Outcome, ...]:
    selected: list[_Outcome] = []
    next_available = -1
    for outcome in sorted(outcomes, key=lambda value: value.entry_book_time_ms):
        if outcome.entry_book_time_ms < next_available:
            continue
        selected.append(outcome)
        next_available = outcome.entry_book_time_ms + horizon * _MINUTE_MS
    return tuple(selected)


def _summary(outcomes: Sequence[_Outcome]) -> dict[str, object]:
    values = [value.after_modeled_friction_bps for value in outcomes]
    return {
        "independent_paths": len(values),
        "mean_after_modeled_friction_bps": mean(values) if values else None,
        "median_after_modeled_friction_bps": median(values) if values else None,
        "positive_after_modeled_friction_count": sum(value > 0.0 for value in values),
        "positive_after_modeled_friction_rate": (
            sum(value > 0.0 for value in values) / len(values) if values else None
        ),
        "mean_excluding_largest_after_modeled_friction_bps": (
            (sum(values) - max(values)) / (len(values) - 1) if len(values) > 1 else None
        ),
    }


def _contract(config: Hip3ShadowMarkoutConfig) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
        "entry_anchor": "first_book_at_or_after_signal_publication",
        "exit_anchor": "first_book_at_or_after_entry_plus_horizon",
        "entry_liquidity": "taker_bbo_cross",
        "exit_liquidity": "taker_bbo_cross",
        "funding_included": False,
        "fee_bps_per_side": config.fee_bps_per_side,
        "residual_latency_bps_per_side": config.residual_latency_bps_per_side,
        "friction_source": config.friction_source,
        "maximum_book_lateness_ms": config.maximum_book_lateness_ms,
    }


def _limitations() -> list[str]:
    return [
        "fixed-horizon BBO markouts are not strategy stop or exit lifecycles",
        "funding and depth-constrained fill size are excluded",
        "small prospective samples do not establish profitability",
        "this report grants no execution, sizing, or promotion authority",
    ]


def _report_only(row: Mapping[str, object]) -> bool:
    return (
        row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 markout {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HIP-3 markout {label} must be non-empty text")
    return value


def _positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 markout {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"HIP-3 markout {label} must be finite and positive")
    return number


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HIP-3 markout {label} must be a nonnegative integer")
    return value


def _positive_integer(value: object, label: str) -> int:
    result = _nonnegative_integer(value, label)
    if result == 0:
        raise ValueError(f"HIP-3 markout {label} must be positive")
    return result
