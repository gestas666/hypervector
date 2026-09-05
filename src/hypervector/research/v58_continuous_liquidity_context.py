"""Authenticated visible-liquidity context for the V58 observer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_candidate_notionals import (
    candidate_asset_notionals,
)
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

Record = Mapping[str, object]
Level = tuple[float, float]

_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_ACCOUNT_VALUE_USD = 5_000.0
_BOOK_SOURCE = "hyperliquid_mainnet_l2_rest"
_SYMBOLS = (
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:BRENTOIL",
)
_QUANTILES = (0.5, 0.9, 0.99)


@dataclass(frozen=True)
class LiquidityContext:
    """Execution-incapable visible-book capacity evidence."""

    payload: dict[str, object]
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_liquidity_context(
    config_path: Path,
    *,
    observer: SuccessorObserverEvidence,
) -> LiquidityContext:
    """Load synchronized V58 books from an authenticated observer prefix."""
    _require_observer(observer.status)
    config_evidence = file_evidence(config_path)
    config = load_multi_asset_live_config(config_path, mode="observe")
    if config.profile_id != _PROFILE_ID or tuple(config.symbols) != _SYMBOLS:
        raise ValueError("V58 liquidity config identity is invalid")
    notionals = candidate_asset_notionals(config, _ACCOUNT_VALUE_USD)
    ledger = _mapping(observer.evidence.get("observer_ledger"), "observer ledger")
    rows = _verified_rows(ledger)
    snapshots = _snapshot_metrics(rows, observer.status, notionals)
    payload = _liquidity_payload(snapshots, notionals)
    if file_evidence(config_path) != config_evidence:
        raise ValueError("V58 config changed during liquidity context evaluation")
    return LiquidityContext(
        payload,
        {
            "config": {"path": str(config_path.resolve()), **config_evidence},
            "observer_ledger": dict(ledger),
        },
    )


def liquidity_context_payload(context: LiquidityContext) -> dict[str, object]:
    """Serialize descriptive liquidity without fill or sizing authority."""
    return {
        **context.payload,
        "visible_book_fill_claim": False,
        "queue_position_modeled": False,
        "cancellation_risk_modeled": False,
        "submission_latency_modeled": False,
        "profitability_claim": False,
        "sizing_input": False,
        "execution_authority": context.execution_authority,
    }


def _verified_rows(ledger: Record) -> tuple[dict[str, object], ...]:
    path = Path(_text(ledger.get("path"), "observer ledger path"))
    return read_jsonl_verified_prefix(
        path,
        "V58 observer ledger",
        length=_positive_integer(ledger.get("stable_bytes"), "stable ledger bytes"),
        expected_sha256=_text(ledger.get("sha256"), "observer ledger sha256"),
    )


def _snapshot_metrics(
    rows: Sequence[Record],
    status: Record,
    notionals: Record,
) -> list[dict[str, dict[str, object]]]:
    output: list[dict[str, dict[str, object]]] = []
    sequences: list[int] = []
    for row in rows:
        if not _current_row(row, status) or row.get("event_type") != "market_books":
            continue
        _require_row_contract(row)
        sequence = _positive_integer(row.get("sequence"), "market-book sequence")
        if sequences and sequence <= sequences[-1]:
            raise ValueError("V58 market-book sequences are not strictly increasing")
        sequences.append(sequence)
        payload = _mapping(row.get("payload"), "market-book payload")
        books = _mapping(payload.get("books"), "market books")
        if len(books) != len(_SYMBOLS) or set(books) != set(_SYMBOLS):
            raise ValueError("V58 market-book symbol identity is invalid")
        output.append(
            {
                symbol: _book_metrics(books[symbol], symbol, float(notionals[symbol]))
                for symbol in _SYMBOLS
            }
        )
    if not output:
        raise ValueError("V58 liquidity context has no current-run market books")
    return output


def _book_metrics(value: object, symbol: str, notional: float) -> dict[str, object]:
    book = _mapping(value, f"{symbol} book")
    expected = {"symbol": symbol, "source": _BOOK_SOURCE}
    if any(book.get(field) != wanted for field, wanted in expected.items()):
        raise ValueError(f"{symbol} book identity is invalid")
    exchange = _positive_integer(book.get("exchange_ts_ms"), f"{symbol} exchange time")
    received = _positive_integer(book.get("recv_ts_ms"), f"{symbol} receive time")
    if received < exchange:
        raise ValueError(f"{symbol} book receive time precedes exchange time")
    mid = _positive_number(book.get("mid_px"), f"{symbol} midpoint")
    bids = _levels(book.get("bids"), symbol, "bid", descending=True)
    asks = _levels(book.get("asks"), symbol, "ask", descending=False)
    _require_bbo(symbol, mid, bids, asks, book.get("spread_bps"))
    bid_complete, bid_vwap = _visible_vwap(bids, notional)
    ask_complete, ask_vwap = _visible_vwap(asks, notional)
    return {
        "spread_bps": (asks[0][0] - bids[0][0]) / mid * 10_000.0,
        "exchange_to_receive_delay_ms": received - exchange,
        "bid_complete": bid_complete,
        "ask_complete": ask_complete,
        "bid_visible_cost_bps": _cost(mid, bid_vwap, sell=True),
        "ask_visible_cost_bps": _cost(mid, ask_vwap, sell=False),
    }


def _levels(
    value: object,
    symbol: str,
    side: str,
    *,
    descending: bool,
) -> list[Level]:
    if not isinstance(value, list) or not value or len(value) > 20:
        raise ValueError(f"{symbol} {side} levels must contain 1 to 20 rows")
    levels = [_level(row, symbol, side) for row in value]
    prices = [price for price, _ in levels]
    ordered = all(
        left > right if descending else left < right
        for left, right in zip(prices, prices[1:])
    )
    if not ordered and len(prices) > 1:
        raise ValueError(f"{symbol} {side} levels are not strictly ordered")
    return levels


def _level(value: object, symbol: str, side: str) -> Level:
    row = _mapping(value, f"{symbol} {side} level")
    price = _positive_number(row.get("price"), f"{symbol} {side} price")
    size = _positive_number(row.get("size"), f"{symbol} {side} size")
    orders = row.get("orders")
    if isinstance(orders, bool) or not isinstance(orders, int) or orders < 0:
        raise ValueError(f"{symbol} {side} orders must be a nonnegative integer")
    return price, size


def _require_bbo(
    symbol: str,
    mid: float,
    bids: Sequence[Level],
    asks: Sequence[Level],
    reported_spread: object,
) -> None:
    best_bid, best_ask = bids[0][0], asks[0][0]
    if best_bid >= best_ask or not best_bid <= mid <= best_ask:
        raise ValueError(f"{symbol} book is crossed or midpoint is outside the BBO")
    spread = (best_ask - best_bid) / mid * 10_000.0
    reported = _nonnegative_number(reported_spread, f"{symbol} spread")
    if not math.isclose(spread, reported, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(f"{symbol} reported spread does not match the BBO")


def _visible_vwap(
    levels: Sequence[Level], notional: float
) -> tuple[bool, float | None]:
    remaining = notional
    quantity = 0.0
    for price, size in levels:
        consumed = min(remaining, price * size)
        quantity += consumed / price
        remaining -= consumed
        if remaining <= 1e-9:
            return True, notional / quantity
    return False, None


def _cost(mid: float, vwap: float | None, *, sell: bool) -> float | None:
    if vwap is None:
        return None
    return (mid - vwap if sell else vwap - mid) / mid * 10_000.0


def _liquidity_payload(
    snapshots: Sequence[Mapping[str, Record]], notionals: Record
) -> dict[str, object]:
    assets = [
        _asset_summary(
            symbol,
            float(notionals[symbol]),
            [snapshot[symbol] for snapshot in snapshots],
        )
        for symbol in _SYMBOLS
    ]
    complete_rates = [float(row["both_complete_rate"]) for row in assets]
    maximum_cost, maximum_symbol = _maximum_asset_cost(assets)
    return {
        "account_value_usd": _ACCOUNT_VALUE_USD,
        "synchronized_snapshot_count": len(snapshots),
        "symbols": list(_SYMBOLS),
        "assets": assets,
        "minimum_both_complete_rate": min(complete_rates),
        "maximum_visible_cost_p99_bps": maximum_cost,
        "maximum_visible_cost_p99_symbol": maximum_symbol,
        "book_source": _BOOK_SOURCE,
        "scope": "visible_top20_capacity_at_configured_maximum_route_notional",
    }


def _asset_summary(
    symbol: str, notional: float, samples: Sequence[Record]
) -> dict[str, object]:
    bid_complete = sum(row["bid_complete"] is True for row in samples)
    ask_complete = sum(row["ask_complete"] is True for row in samples)
    both_complete = sum(
        row["bid_complete"] is True and row["ask_complete"] is True for row in samples
    )
    metrics = {
        "spread_bps": [float(row["spread_bps"]) for row in samples],
        "exchange_to_receive_delay_ms": [
            float(row["exchange_to_receive_delay_ms"]) for row in samples
        ],
        "bid_visible_cost_bps": _present(samples, "bid_visible_cost_bps"),
        "ask_visible_cost_bps": _present(samples, "ask_visible_cost_bps"),
    }
    quantiles = {
        f"{name}_{label}": _quantile(values, quantile)
        for name, values in metrics.items()
        for quantile, label in zip(_QUANTILES, ("p50", "p90", "p99"))
    }
    maximum = _optional_max(
        quantiles["bid_visible_cost_bps_p99"],
        quantiles["ask_visible_cost_bps_p99"],
    )
    return {
        "symbol": symbol,
        "configured_notional_usd": notional,
        "snapshot_count": len(samples),
        "bid_complete_count": bid_complete,
        "ask_complete_count": ask_complete,
        "both_complete_count": both_complete,
        "bid_complete_rate": bid_complete / len(samples),
        "ask_complete_rate": ask_complete / len(samples),
        "both_complete_rate": both_complete / len(samples),
        **quantiles,
        "maximum_visible_cost_p99_bps": maximum,
    }


def _present(samples: Sequence[Record], field: str) -> list[float]:
    return [float(row[field]) for row in samples if row.get(field) is not None]


def _optional_max(*values: object) -> float | None:
    present = [float(value) for value in values if value is not None]
    return max(present) if present else None


def _maximum_asset_cost(
    assets: Sequence[Record],
) -> tuple[float | None, str | None]:
    values = [
        (float(row["maximum_visible_cost_p99_bps"]), str(row["symbol"]))
        for row in assets
        if row["maximum_visible_cost_p99_bps"] is not None
    ]
    return max(values) if values else (None, None)


def _quantile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _current_row(row: Record, status: Record) -> bool:
    if row.get("run_id") != status.get("run_id"):
        return False
    if row.get("profile_fingerprint") != status.get("profile_fingerprint"):
        raise ValueError("V58 liquidity row profile fingerprint is invalid")
    return True


def _require_row_contract(row: Record) -> None:
    expected = {
        "schema_version": 1,
        "profile_id": _PROFILE_ID,
        "execution_authority": "none",
    }
    if any(row.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 market-book authority or profile is invalid")


def _require_observer(status: Record) -> None:
    expected = {
        "profile_id": _PROFILE_ID,
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 liquidity observer contract is invalid")
    require_reportable_v58_observer_status(status, "V58 liquidity observer")
    _text(status.get("profile_fingerprint"), "observer profile fingerprint")
    _text(status.get("run_id"), "observer run id")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _nonnegative_number(value: object, label: str) -> float:
    number = _number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return number


def _number(value: object, label: str) -> float:
    valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid or not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return float(value)
