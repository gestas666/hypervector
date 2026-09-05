"""Evidence-map assembly for one external research candidate."""

from __future__ import annotations

from collections.abc import Mapping
import math

Record = Mapping[str, object]


def external_candidate_status(
    record: Record,
    symbol: str,
    market_source: tuple[int, Record],
    observer: dict[str, object],
    epoch: dict[str, object] | None,
    lifecycle: dict[str, object] | None,
    validation: dict[str, object] | None,
    historical: dict[str, object] | None,
) -> dict[str, object]:
    """Project one validated candidate without inferring missing evidence."""
    rank, market = market_source
    market_record = _mapping(market.get("market"), "external market")
    book_record = _mapping(market.get("book"), "external book")
    return {
        "symbol": symbol,
        "stage": _text(record.get("stage"), "external candidate stage"),
        "liquidity_rank": rank,
        "day_notional_volume_usd": _number(
            market_record.get("day_notional_volume_usd"), "external day volume"
        ),
        "spread_bps": _number(book_record.get("spread_bps"), "external spread"),
        "maximum_venue_leverage": _integer(
            market.get("max_leverage"), "external maximum leverage"
        ),
        "observer": observer,
        "comparable_decision_epoch": epoch,
        "prospective_lifecycle": lifecycle,
        "technical_validation": validation,
        "historical_live": historical,
        "live_authorized": False,
        "strategy_edge_established": False,
    }


def external_candidate_source_evidence(
    observer: dict[str, object],
    immutable: list[dict[str, object]],
    historical: dict[str, object] | None,
    validation: dict[str, object] | None,
    lifecycle: dict[str, object] | None,
    epoch: dict[str, object] | None,
) -> dict[str, object]:
    """Return exact source evidence without success-shaped missing sections."""
    source: dict[str, object] = {"observer": observer, "immutable": immutable}
    optional = {
        "historical_live": historical,
        "technical_validation": validation,
        "prospective_lifecycle": lifecycle,
        "comparable_decision_epoch": epoch,
    }
    source.update(
        (name, value) for name, value in optional.items() if value is not None
    )
    return source


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
