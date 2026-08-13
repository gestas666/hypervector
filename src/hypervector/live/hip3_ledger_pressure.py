"""Causal depth-ten HIP-3 order pressure from authoritative ledgers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Protocol

_TAIL_BYTES = 512 * 1_024
_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"


@dataclass(frozen=True)
class Hip3PressureObservation:
    """One causally received depth-ten order-pressure measurement."""

    recv_ts_ms: int
    imbalance_10: float

    def __post_init__(self) -> None:
        """Reject impossible timestamps and normalized imbalance values."""
        if (
            isinstance(self.recv_ts_ms, bool)
            or not isinstance(self.recv_ts_ms, int)
            or self.recv_ts_ms < 0
        ):
            raise ValueError("HIP-3 pressure timestamp must be nonnegative")
        if not math.isfinite(self.imbalance_10) or not -1.0 <= self.imbalance_10 <= 1.0:
            raise ValueError("HIP-3 depth-ten imbalance must be within [-1, 1]")


class Hip3PressureSourceProtocol(Protocol):
    """Read the latest causally recorded pressure for one exact symbol."""

    def latest_at_or_before(
        self,
        symbol: str,
        not_after_ms: int,
    ) -> Hip3PressureObservation | None:
        """Return the newest observation at or before the causal cutoff."""
        ...


class Hip3LedgerPressureSource:
    """Read live asset books or observer books without making network calls."""

    def __init__(
        self,
        *,
        asset_ledgers: Mapping[str, Path],
        cohort_ledger: Path,
    ) -> None:
        """Bind exact symbol paths and the shared observer fallback ledger."""
        if not asset_ledgers:
            raise ValueError("HIP-3 pressure source requires asset ledgers")
        self._asset_ledgers = dict(asset_ledgers)
        self._cohort_ledger = cohort_ledger

    def latest_at_or_before(
        self,
        symbol: str,
        not_after_ms: int,
    ) -> Hip3PressureObservation | None:
        """Return the newest exact measurement not newer than the cutoff."""
        if symbol not in self._asset_ledgers:
            raise ValueError(f"HIP-3 pressure symbol is not configured: {symbol}")
        if (
            isinstance(not_after_ms, bool)
            or not isinstance(not_after_ms, int)
            or not_after_ms < 0
        ):
            raise ValueError("HIP-3 pressure cutoff must be a nonnegative integer")
        candidates = tuple(
            value
            for value in (
                _latest_asset_book(self._asset_ledgers[symbol], not_after_ms),
                _latest_cohort_book(self._cohort_ledger, symbol, not_after_ms),
            )
            if value is not None
        )
        return max(candidates, key=lambda value: value.recv_ts_ms, default=None)

    def latest(self, symbol: str) -> Hip3PressureObservation | None:
        """Return the newest observation without applying a historical cutoff."""
        return self.latest_at_or_before(symbol, 2**63 - 1)


def _latest_asset_book(
    path: Path,
    not_after_ms: int,
) -> Hip3PressureObservation | None:
    for row in _reverse_rows(path):
        if row.get("event_type") != "book_observation":
            continue
        pressure = _pressure(_mapping(row.get("payload"), "asset book payload"))
        if pressure.recv_ts_ms <= not_after_ms:
            return pressure
    return None


def _latest_cohort_book(
    path: Path,
    symbol: str,
    not_after_ms: int,
) -> Hip3PressureObservation | None:
    for row in _reverse_rows(path):
        if row.get("event_type") != "market_books":
            continue
        payload = _mapping(row.get("payload"), "cohort book payload")
        books = _mapping(payload.get("books"), "cohort books")
        raw = books.get(symbol)
        if raw is not None:
            pressure = _pressure(_mapping(raw, f"cohort book {symbol}"))
            if pressure.recv_ts_ms <= not_after_ms:
                return pressure
    return None


def _pressure(payload: Mapping[str, object]) -> Hip3PressureObservation:
    if payload.get("source") != _BOOK_SOURCE:
        raise ValueError("HIP-3 pressure must come from Hyperliquid mainnet L2")
    recv_ts_ms = payload.get("recv_ts_ms")
    if isinstance(recv_ts_ms, bool) or not isinstance(recv_ts_ms, int):
        raise ValueError("HIP-3 book recv_ts_ms must be an integer")
    bid_depth = _depth(payload.get("bids"), "bids")
    ask_depth = _depth(payload.get("asks"), "asks")
    total = bid_depth + ask_depth
    if total <= 0.0:
        raise ValueError("HIP-3 depth-ten book has no visible size")
    return Hip3PressureObservation(
        recv_ts_ms=recv_ts_ms,
        imbalance_10=(bid_depth - ask_depth) / total,
    )


def _depth(value: object, side: str) -> float:
    if not isinstance(value, list) or not value:
        raise ValueError(f"HIP-3 book {side} must be a non-empty list")
    depth = 0.0
    for raw in value[:10]:
        level = _mapping(raw, f"HIP-3 {side} level")
        size = level.get("size")
        if isinstance(size, bool) or not isinstance(size, (int, float)):
            raise ValueError(f"HIP-3 {side} size must be numeric")
        numeric = float(size)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"HIP-3 {side} size must be positive and finite")
        depth += numeric
    return depth


def _reverse_rows(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - _TAIL_BYTES)
        handle.seek(start)
        data = handle.read()
    if not data:
        return ()
    if not data.endswith(b"\n"):
        data = data.rsplit(b"\n", 1)[0] + b"\n" if b"\n" in data else b""
    lines = data.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    return tuple(_json_object(line) for line in reversed(lines))


def _json_object(line: bytes) -> dict[str, object]:
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("HIP-3 pressure ledger contains malformed JSONL") from exc
    if not isinstance(value, dict):
        raise ValueError("HIP-3 pressure ledger row must be an object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
