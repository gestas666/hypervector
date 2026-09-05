"""Unsigned public mark evidence for the V58 BTC sweep watcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import cast

from hypervector.data.oxa_api import validate_market_symbol

BTC_MARK_SOURCE = "hyperliquid_info_metaAndAssetCtxs_rest"


def parse_btc_mark_snapshot(
    response: object,
    *,
    run_id: str,
    received_ts_ns: int,
) -> dict[str, object]:
    """Parse one receipt-causal BTC mark from public core venue contexts."""
    validate_market_symbol("BTC", "core")
    run = _text(run_id, "BTC mark run id")
    receipt = _positive_integer(received_ts_ns, "BTC mark receipt")
    pair = _sequence(response, "metaAndAssetCtxs response")
    if len(pair) != 2:
        raise ValueError("metaAndAssetCtxs must contain metadata and contexts")
    metadata = _mapping(pair[0], "core metadata")
    universe = _sequence(metadata.get("universe"), "core universe")
    contexts = _sequence(pair[1], "core contexts")
    if len(universe) != len(contexts):
        raise ValueError("core universe and contexts must be position-aligned")
    matches = [
        index
        for index, raw in enumerate(universe)
        if _mapping(raw, "core market").get("name") == "BTC"
    ]
    if len(matches) != 1:
        raise ValueError("core mark symbol BTC must resolve exactly once")
    context = _mapping(contexts[matches[0]], "BTC context")
    return {
        "schema_version": 1,
        "symbol": "BTC",
        "source": BTC_MARK_SOURCE,
        "run_id": run,
        "received_ts_ms": receipt // 1_000_000,
        "received_ts_ns": receipt,
        "mark_price": _decimal(context.get("markPx"), "BTC mark", positive=True),
        "oracle_price": _decimal(context.get("oraclePx"), "BTC oracle", positive=True),
        "funding_rate_hourly": _decimal(context.get("funding"), "BTC funding"),
        "open_interest": _decimal(
            context.get("openInterest"), "BTC open interest", nonnegative=True
        ),
    }


def validated_btc_marks(
    rows: Sequence[Mapping[str, object]], *, run_id: str
) -> tuple[dict[str, object], ...]:
    """Validate, deduplicate, and order exact-run BTC mark observations."""
    run = _text(run_id, "BTC mark run id")
    selected: dict[int, dict[str, object]] = {}
    for raw in rows:
        row = dict(raw)
        _validate_row(row, run)
        received = cast(int, row["received_ts_ms"])
        prior = selected.get(received)
        if prior is not None and prior != row:
            raise ValueError("BTC mark ledger contains a conflicting receipt")
        selected[received] = row
    return tuple(selected[key] for key in sorted(selected))


def _validate_row(row: Mapping[str, object], run_id: str) -> None:
    if row.get("schema_version") != 1:
        raise ValueError("BTC mark schema is invalid")
    expected = {"symbol": "BTC", "source": BTC_MARK_SOURCE, "run_id": run_id}
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("BTC mark identity differs from the observer run")
    received = _positive_integer(row.get("received_ts_ms"), "BTC mark time")
    received_ns = _positive_integer(row.get("received_ts_ns"), "BTC mark time ns")
    if received_ns // 1_000_000 != received:
        raise ValueError("BTC mark millisecond and nanosecond receipts disagree")
    _number(row.get("mark_price"), "BTC mark price", positive=True)
    _number(row.get("oracle_price"), "BTC oracle price", positive=True)
    _number(row.get("funding_rate_hourly"), "BTC funding")
    _number(row.get("open_interest"), "BTC open interest", nonnegative=True)


def _decimal(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string")
    try:
        output = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    return _validated_number(output, label, positive, nonnegative)


def _number(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return _validated_number(float(value), label, positive, nonnegative)


def _validated_number(
    value: float, label: str, positive: bool, nonnegative: bool
) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    if positive and value <= 0.0:
        raise ValueError(f"{label} must be positive")
    if nonnegative and value < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be an array")
    return value


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
