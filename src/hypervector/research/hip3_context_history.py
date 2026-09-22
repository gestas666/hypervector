"""Append-only public asset-context research snapshots without account data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
import fcntl
import json
import math
import os
from pathlib import Path

from hypervector.data.hip3_mark_snapshot_recorder import select_hip3_asset_contexts
from hypervector.data.oxa_api import validate_hip3_symbol

_NUMERIC_FIELDS = {
    "premium": "premium",
    "oraclePx": "oracle_price",
    "markPx": "mark_price",
    "midPx": "mid_price",
    "funding": "funding_rate_hourly",
    "openInterest": "open_interest",
    "dayNtlVlm": "day_notional_volume",
}
_PRICES = {"oraclePx", "markPx", "midPx"}


def context_record(
    response: object,
    *,
    dex: str,
    observed_at: datetime,
    required_symbols: Sequence[str] = (),
) -> dict[str, object]:
    """Normalize the complete namespace using the same positional identity checks.

    ``required_symbols`` are the roster markets whose values the live supervisor
    reads: a parse failure on one of those is still fatal. Every other market in
    the dex is archived best-effort, because one unparseable market nobody trades
    must not blank the whole checkpoint.
    """
    if (
        not isinstance(response, list)
        or len(response) != 2
        or not isinstance(response[0], dict)
    ):
        raise ValueError("context history requires aligned metadata and context arrays")
    universe = response[0].get("universe")
    if not isinstance(universe, list) or not universe:
        raise ValueError("context history requires a nonempty universe")
    symbols = tuple(_symbol(row, dex) for row in universe)
    contexts = select_hip3_asset_contexts(response, symbols=symbols)
    required = frozenset(required_symbols)
    markets = []
    unparsed = 0
    for symbol, row in zip(symbols, universe, strict=True):
        try:
            markets.append(_market(symbol, contexts[symbol], row))
        except (ValueError, TypeError, KeyError) as exc:
            if symbol in required:
                raise
            unparsed += 1
            markets.append({"symbol": symbol, "parse_error": type(exc).__name__})
    return {
        **_header(observed_at),
        "status": "available",
        "dex": dex,
        "source": "hyperliquid_info_metaAndAssetCtxs",
        "unparsed_market_count": unparsed,
        "markets": markets,
    }


def unavailable_context_record(
    observed_at: datetime, error_type: str
) -> dict[str, object]:
    """Record a failed polling opportunity without copying potentially private errors."""
    return {
        **_header(observed_at),
        "status": "unavailable",
        "error_type": error_type,
        "markets": None,
    }


def append_context_record(directory: Path, record: dict[str, object]) -> Path:
    """Synchronously append one complete record under an exclusive writer lock."""
    timestamp = record.get("observed_at_utc")
    if not isinstance(timestamp, str):
        raise ValueError("context history requires an observed_at_utc timestamp")
    stamp = datetime.fromisoformat(timestamp)
    if stamp.tzinfo is None:
        raise ValueError("context history timestamp must be timezone-aware")
    encoded = (json.dumps(record, allow_nan=False, sort_keys=True) + "\n").encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (stamp.astimezone(UTC).date().isoformat() + ".jsonl")
    with path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    raise ValueError(
                        f"context history has incomplete JSONL tail; back up and repair {path}"
                    )
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    return path


def prune_context_history(
    directory: Path, *, retention_days: int, now: datetime | None = None
) -> list[Path]:
    """Drop whole day files outside the retention window. Report what was removed.

    The capture appends a full dex snapshot every poll; without a window it adds
    gigabytes a year to the same volume the live ledgers grow on.
    """
    if retention_days <= 0:
        raise ValueError("context history retention_days must be positive")
    if not directory.is_dir():
        return []
    oldest = (now or datetime.now(UTC)).astimezone(UTC).date() - timedelta(
        days=retention_days
    )
    removed: list[Path] = []
    for path in sorted(directory.glob("*.jsonl")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < oldest:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


def _header(observed_at: datetime) -> dict[str, object]:
    if observed_at.tzinfo is None:
        raise ValueError("context observation timestamp must be timezone-aware")
    return {
        "schema_version": 1,
        "observed_at_utc": observed_at.astimezone(UTC).isoformat(),
        "timestamp_source": "local_receipt",
        "event_type": "hip3_asset_context_snapshot",
        "execution_authority": "none",
        "report_only": True,
    }


def _symbol(row: object, dex: str) -> str:
    symbol = row.get("name") if isinstance(row, dict) else None
    if not isinstance(symbol, str) or validate_hip3_symbol(symbol)[0] != dex:
        raise ValueError("context market name must belong to the requested dex")
    return symbol


def _market(
    symbol: str, context: Mapping[str, object], metadata: Mapping[str, object]
) -> dict[str, object]:
    fields = {
        name: _optional_decimal(context.get(raw), symbol, raw)
        for raw, name in _NUMERIC_FIELDS.items()
    }
    return {
        "symbol": symbol,
        **fields,
        "missing_fields": [name for name, value in fields.items() if value is None],
        "growth_mode": metadata.get("growthMode"),
        "max_leverage": metadata.get("maxLeverage"),
        "is_delisted": metadata.get("isDelisted"),
    }


def _optional_decimal(value: object, symbol: str, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{symbol} {field} must be a decimal string or null")
    number = float(value)
    if not math.isfinite(number) or (field in _PRICES and number <= 0):
        raise ValueError(f"{symbol} {field} must be finite and prices must be positive")
    return number
