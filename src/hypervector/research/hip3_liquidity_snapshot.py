"""Build an execution-incapable HIP-3 liquidity ranking."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import math

Record = Mapping[str, object]


def build_hip3_liquidity_snapshot(
    *,
    dex: str,
    metadata: Record,
    contexts: object,
    observed_at_utc: datetime,
) -> dict[str, object]:
    """Return a strictly aligned active-market ranking by reported day volume."""
    universe, aligned = _aligned_rows(metadata, contexts)
    active: list[dict[str, object]] = []
    delisted: list[str] = []
    seen: set[str] = set()
    for market, context in zip(universe, aligned, strict=True):
        symbol = _symbol(market, dex)
        if symbol in seen:
            raise ValueError(f"duplicate HIP-3 market symbol: {symbol}")
        seen.add(symbol)
        if market.get("isDelisted") is True:
            delisted.append(symbol)
            continue
        active.append(_market_row(market, context, symbol))
    active.sort(
        key=lambda row: (-float(row["day_notional_volume_usd"]), str(row["symbol"]))
    )
    for rank, row in enumerate(active, start=1):
        row["volume_rank"] = rank
    return _report(dex, active, delisted, len(universe), observed_at_utc)


def _aligned_rows(
    metadata: Record, contexts: object
) -> tuple[tuple[Record, ...], tuple[Record, ...]]:
    universe = _records(metadata.get("universe"), "market universe")
    aligned = _records(contexts, "market contexts")
    if len(universe) != len(aligned):
        raise ValueError("HIP-3 metadata and context lengths differ")
    return universe, aligned


def _market_row(market: Record, context: Record, symbol: str) -> dict[str, object]:
    mark = _positive_number(context.get("markPx"), f"{symbol} markPx")
    open_interest = _nonnegative_number(
        context.get("openInterest"), f"{symbol} openInterest"
    )
    return {
        "symbol": symbol,
        "day_notional_volume_usd": _nonnegative_number(
            context.get("dayNtlVlm"), f"{symbol} dayNtlVlm"
        ),
        "mark_price": mark,
        "open_interest_base": open_interest,
        "open_interest_notional_usd": mark * open_interest,
        "max_leverage": _positive_integer(
            market.get("maxLeverage"), f"{symbol} maxLeverage"
        ),
    }


def _report(
    dex: str,
    markets: list[dict[str, object]],
    delisted: list[str],
    total: int,
    observed_at: datetime,
) -> dict[str, object]:
    return {
        "schema_version": "hip3_liquidity_snapshot_v1",
        "mode": "hip3_public_liquidity_snapshot",
        "status": "observed",
        "observed_at_utc": _aware(observed_at).isoformat(),
        "dex": dex,
        "market_count": total,
        "active_market_count": len(markets),
        "markets": markets,
        "excluded_delisted_symbols": sorted(delisted),
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "credentials_loaded": False,
            "execution_client_constructed": False,
            "automatic_live_change": False,
        },
    }


def _symbol(market: Record, dex: str) -> str:
    symbol = market.get("name")
    if not isinstance(symbol, str) or not symbol.startswith(f"{dex}:"):
        raise ValueError("HIP-3 market symbol does not match the requested dex")
    return symbol


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    rows: list[Record] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} rows must be mappings")
        rows.append(row)
    return tuple(rows)


def _nonnegative_number(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if number < 0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _positive_number(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation timestamp must be timezone-aware")
    return value.astimezone(UTC)
