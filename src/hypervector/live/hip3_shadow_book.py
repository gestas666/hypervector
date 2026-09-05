"""Causal, provenance-preserving book rows for HIP-3 research observers."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.paper.book import BookSnapshot


@dataclass(frozen=True)
class Hip3ShadowBookSpec:
    """Exact identity and bounded cross-clock contract for one HIP-3 ledger."""

    symbol: str
    source: str
    profile_id: str
    label: str
    maximum_negative_clock_skew_ms: int = 5_000
    depth: int = 10

    def __post_init__(self) -> None:
        """Reject incomplete identity or invalid timing/depth limits."""
        for value, name in (
            (self.symbol, "symbol"),
            (self.source, "source"),
            (self.profile_id, "profile id"),
            (self.label, "label"),
        ):
            if not value:
                raise ValueError(f"HIP-3 shadow book {name} must be non-empty")
        if self.maximum_negative_clock_skew_ms < 0 or self.depth <= 0:
            raise ValueError("HIP-3 shadow book limits must be nonnegative")


def hip3_shadow_book_row(
    snapshot: BookSnapshot, spec: Hip3ShadowBookSpec
) -> tuple[dict[str, object], int]:
    """Normalize bounded venue-clock lead while retaining local receipt time."""
    if snapshot.symbol != spec.symbol:
        raise ValueError(
            f"{spec.label} shadow public book must have exact {spec.symbol} identity"
        )
    if snapshot.source != "hl_rest_l2":
        raise ValueError(f"{spec.label} shadow book must use Hyperliquid Info REST")
    exchange = _exact_integer(snapshot.ts_exchange_ms, spec.label, "exchange timestamp")
    local_receipt = _ceiling_integer(
        snapshot.ts_recv_ms, spec.label, "receipt timestamp"
    )
    negative_skew = max(0, exchange - local_receipt)
    if negative_skew > spec.maximum_negative_clock_skew_ms:
        raise ValueError(
            f"{spec.label} shadow book clock skew exceeds "
            f"{spec.maximum_negative_clock_skew_ms}ms"
        )
    available = max(exchange, local_receipt)
    payload: dict[str, object] = {
        "symbol": spec.symbol,
        "source": spec.source,
        "exchange_ts_ms": exchange,
        "recv_ts_ms": available,
        "local_recv_ts_ms": local_receipt,
        "negative_clock_skew_ms": negative_skew,
        "bids": _levels(snapshot, "bids", spec),
        "asks": _levels(snapshot, "asks", spec),
    }
    return _envelope(payload, spec), available


def _envelope(
    payload: dict[str, object], spec: Hip3ShadowBookSpec
) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": spec.profile_id,
        "execution_authority": "none",
        "payload": payload,
    }


def _levels(
    snapshot: BookSnapshot, side: str, spec: Hip3ShadowBookSpec
) -> list[dict[str, float]]:
    values = snapshot.bids if side == "bids" else snapshot.asks
    if len(values) < spec.depth:
        raise ValueError(f"{spec.label} shadow {side} require {spec.depth} levels")
    return [
        {"price": float(level.price), "size": float(level.size)}
        for level in values[: spec.depth]
    ]


def _exact_integer(value: object, label: str, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} shadow {field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"{label} shadow {field} must be an exact integer")
    return int(numeric)


def _ceiling_integer(value: object, label: str, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} shadow {field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"{label} shadow {field} must be finite and nonnegative")
    return math.ceil(numeric)
