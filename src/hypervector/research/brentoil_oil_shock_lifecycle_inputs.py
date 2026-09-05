"""Causal source validation for BRENTOIL shadow lifecycles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

from hypervector.data.hl_events import AssetContextEvent
from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
    BRENTOIL_OIL_SHOCK_SYMBOL,
)
from hypervector.live.brentoil_oil_shock_shadow_storage import (
    validate_candle_row,
)
from hypervector.research.brentoil_oil_shock_lifecycle_models import (
    Mark,
    positive_integer,
    positive_number,
)
from hypervector.research.hip3_shadow_signal_markouts import Hip3ShadowDecision

_MARK_SOURCE = "hyperliquid_ws_activeAssetCtx"


def validated_decisions(
    rows: Sequence[Mapping[str, object]], observed_at_ms: int
) -> tuple[Hip3ShadowDecision, ...]:
    """Return unique eligible decisions with exact report-only identity."""
    seen: set[str] = set()
    eligible: list[Hip3ShadowDecision] = []
    for row in rows:
        event_id = text(row.get("event_id"), "decision event id")
        if event_id in seen:
            raise ValueError("BRENTOIL lifecycle contains a duplicate decision")
        seen.add(event_id)
        decision = _validated_decision_row(row, observed_at_ms)
        if decision is not None:
            eligible.append(decision)
    return tuple(sorted(eligible, key=lambda value: value.observed_at_ms))


def _validated_decision_row(
    row: Mapping[str, object], observed_at_ms: int
) -> Hip3ShadowDecision | None:
    if row.get("event_type") != "brentoil_oil_shock_shadow_decision":
        raise ValueError("BRENTOIL lifecycle decision event type is invalid")
    decision = mapping(row.get("decision"), "decision")
    _require_decision_identity(row, decision)
    decision_ms = positive_integer(decision.get("decision_time_ms"), "decision time")
    publication = positive_integer(decision.get("observed_at_ms"), "observed time")
    delay_ms = publication - decision_ms
    if delay_ms < 0 or publication > observed_at_ms:
        raise ValueError("BRENTOIL lifecycle decision publication is not causal")
    eligible = decision.get("eligible")
    if not isinstance(eligible, bool):
        raise ValueError("BRENTOIL lifecycle decision eligibility is invalid")
    if not eligible:
        return None
    side = text(decision.get("side"), "decision side")
    if (
        side not in {"long", "short"}
        or decision.get("prospective") is not True
        or delay_ms > 15_000
        or decision.get("non_action_reason") is not None
    ):
        raise ValueError("BRENTOIL lifecycle eligible decision is inconsistent")
    event_id = text(row.get("event_id"), "decision event id")
    return Hip3ShadowDecision(event_id, decision_ms, publication, side)


def _require_decision_identity(
    row: Mapping[str, object], decision: Mapping[str, object]
) -> None:
    safe = (
        row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("runtime_strategy_changed") is False
        and row.get("intents") == []
    )
    expected = (
        BRENTOIL_OIL_SHOCK_SYMBOL,
        BRENTOIL_OIL_SHOCK_PROVIDER_ID,
        BRENTOIL_OIL_SHOCK_PROFILE_ID,
        "none",
    )
    actual = tuple(
        decision.get(name)
        for name in ("symbol", "provider_id", "profile_id", "execution_authority")
    )
    if (
        not safe
        or actual != expected
        or not isinstance(decision.get("prospective"), bool)
    ):
        raise ValueError("BRENTOIL lifecycle decision identity is invalid")


def reconcile_candles(
    decision_rows: Sequence[Mapping[str, object]],
    candle_rows: Sequence[Mapping[str, object]],
    observed_at_ms: int,
) -> set[int]:
    """Reconcile every decision to its exact persistent source candle."""
    by_close = _candles_by_close(candle_rows, observed_at_ms)
    prospective: set[int] = set()
    for raw in decision_rows:
        decision = mapping(raw.get("decision"), "decision")
        decision_ms = positive_integer(
            decision.get("decision_time_ms"), "decision time"
        )
        candle = by_close.get(decision_ms)
        if candle is None or not _same_candle(decision, candle):
            raise ValueError("BRENTOIL lifecycle decision candle is inconsistent")
        if candle.get("prospective") is True:
            prospective.add(decision_ms)
    return prospective


def unresolved_prospective_boundaries(
    candle_rows: Sequence[Mapping[str, object]], observed_at_ms: int
) -> set[int]:
    """Return late non-warmup candle closes that could hide an exit signal."""
    by_close = _candles_by_close(candle_rows, observed_at_ms)
    return {
        close
        for close, row in by_close.items()
        if row.get("historical_warmup") is False and row.get("prospective") is False
    }


def _candles_by_close(
    rows: Sequence[Mapping[str, object]], observed_at_ms: int
) -> dict[int, Mapping[str, object]]:
    output: dict[int, Mapping[str, object]] = {}
    for row in rows:
        close = _validated_candle(row, observed_at_ms)
        if close in output:
            raise ValueError("BRENTOIL lifecycle candle identity is duplicated")
        output[close] = row
    return output


def _validated_candle(row: Mapping[str, object], observed_at_ms: int) -> int:
    validate_candle_row(dict(row))
    close = positive_integer(row.get("bar_close_ms"), "candle close")
    captured = positive_integer(row.get("observed_at_ms"), "candle observation")
    if captured > observed_at_ms:
        raise ValueError("BRENTOIL lifecycle candle source is invalid")
    return close


def _same_candle(decision: Mapping[str, object], candle: Mapping[str, object]) -> bool:
    price_pairs = (
        ("candle_open", "open"),
        ("candle_high", "high"),
        ("candle_low", "low"),
        ("candle_close", "close"),
    )
    prices_match = all(
        math.isclose(
            positive_number(decision.get(left), left),
            positive_number(candle.get(right), right),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for left, right in price_pairs
    )
    volumes_match = math.isclose(
        _nonnegative_number(decision.get("candle_volume"), "candle_volume"),
        _nonnegative_number(candle.get("volume"), "volume"),
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    return prices_match and volumes_match


def _nonnegative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BRENTOIL lifecycle {label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be nonnegative")
    return number


def validated_marks(
    rows: Sequence[AssetContextEvent], observed_at_ms: int
) -> tuple[Mark, ...]:
    """Return unique exact receipt-time BRENTOIL mark observations."""
    output: dict[int, Mark] = {}
    for row in rows:
        receipt_ms = (row.received_ts_ns + 999_999) // 1_000_000
        if not _valid_mark_source(row, receipt_ms, observed_at_ms):
            raise ValueError("BRENTOIL lifecycle mark source is invalid")
        mark = Mark(receipt_ms, positive_number(row.mark_price, "mark price"))
        prior = output.get(row.received_ts_ns)
        if prior is not None and prior != mark:
            raise ValueError("BRENTOIL lifecycle marks contain a conflict")
        output[row.received_ts_ns] = mark
    return tuple(sorted(output.values(), key=lambda value: value.timestamp_ms))


def _valid_mark_source(
    row: AssetContextEvent, receipt_ms: int, observed_at_ms: int
) -> bool:
    return (
        row.symbol == BRENTOIL_OIL_SHOCK_SYMBOL
        and row.source == _MARK_SOURCE
        and receipt_ms <= observed_at_ms
    )


def mapping(value: object, label: str) -> Mapping[str, object]:
    """Return a mapping or fail closed with source context."""
    if not isinstance(value, Mapping):
        raise ValueError(f"BRENTOIL lifecycle {label} must be an object")
    return value


def text(value: object, label: str) -> str:
    """Return non-empty text or fail closed with source context."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"BRENTOIL lifecycle {label} must be non-empty text")
    return value
