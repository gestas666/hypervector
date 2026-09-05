"""Immutable source acquisition for Deribit BTC option trades."""

from __future__ import annotations

import json
import math
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Direction = Literal["buy", "sell"]
OptionType = Literal["call", "put"]
_INSTRUMENT = re.compile(r"^BTC-[0-9]{1,2}[A-Z]{3}[0-9]{2}-[0-9]+(?:\.[0-9]+)?-[CP]$")
DERIBIT_OPTION_TRADES_URL = (
    "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
)
DERIBIT_INSTRUMENTS_URL = "https://history.deribit.com/api/v2/public/get_instruments"
DAY_MS = 86_400_000
RequestParameters = Mapping[str, str | int | bool]
PageFetcher = Callable[[str, RequestParameters], bytes]


@dataclass(frozen=True)
class TradeWindow:
    """One half-open millisecond range requested from Deribit."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_ms, bool)
            or not isinstance(self.start_ms, int)
            or isinstance(self.end_ms, bool)
            or not isinstance(self.end_ms, int)
        ):
            raise ValueError("Deribit trade-window bounds must be integers")
        if self.start_ms < 0 or self.end_ms <= self.start_ms:
            raise ValueError("Deribit trade window must be positive and increasing")


@dataclass(frozen=True)
class OptionTrade:
    """Required event-time fields for one public BTC option trade."""

    trade_id: str
    trade_seq: int
    instrument_name: str
    timestamp_ms: int
    direction: Direction
    amount: float
    price: float
    index_price: float
    mark_price: float
    iv: float
    tick_direction: int
    block_trade_id: str | None
    block_rfq_id: int | None
    combo_id: str | None
    combo_trade_id: str | None


@dataclass(frozen=True)
class OptionInstrument:
    """Feature-defining metadata for one BTC option instrument."""

    instrument_name: str
    creation_timestamp_ms: int
    expiration_timestamp_ms: int
    strike: float
    option_type: OptionType
    contract_size: float


@dataclass(frozen=True)
class TradePage:
    """One validated raw Deribit response for an exact time window."""

    content: bytes
    window: TradeWindow
    trades: tuple[OptionTrade, ...]
    has_more: bool


@dataclass(frozen=True)
class TradeHistory:
    """All raw requests and complete normalized trades for one root window."""

    pages: tuple[TradePage, ...]
    terminal_windows: tuple[TradeWindow, ...]
    trades: tuple[OptionTrade, ...]
    truncated_pages: int
    duplicate_trades_removed: int


def acquire_deribit_option_bundle(
    output: Path,
    fetch_bytes: PageFetcher,
    *,
    window: TradeWindow,
    max_requests_per_day: int,
    context: dict[str, object],
) -> Path:
    """Publish immutable source-only option evidence with bounded memory."""
    from hypervector.research.deribit_option_trade_storage import (
        acquire_deribit_option_bundle as acquire,
    )

    return acquire(
        output,
        fetch_bytes,
        window=window,
        max_requests_per_day=max_requests_per_day,
        context=context,
    )


def parse_trade_page(content: bytes, window: TradeWindow) -> TradePage:
    """Parse and validate one official Deribit option-trade response."""
    payload = _decoded_object(content)
    if "error" in payload:
        raise ValueError("Deribit option-trade page returned JSON-RPC error")
    if payload.get("jsonrpc") != "2.0":
        raise ValueError("Deribit option-trade JSON-RPC version drifted")
    result = _object(payload.get("result"), "result")
    raw_trades = result.get("trades")
    if not isinstance(raw_trades, list):
        raise ValueError("Deribit option-trade result trades is not an array")
    has_more = result.get("has_more")
    if not isinstance(has_more, bool):
        raise ValueError("Deribit option-trade result has_more is not boolean")
    trades = tuple(
        _option_trade(value, window, index)
        for index, value in enumerate(raw_trades, start=1)
    )
    return TradePage(content, window, trades, has_more)


def fetch_trade_history(
    fetch_bytes: PageFetcher,
    window: TradeWindow,
    *,
    max_requests: int,
) -> TradeHistory:
    """Fetch one bounded window, bisecting every truncated response."""
    return _fetch_trade_windows(fetch_bytes, [window], max_requests=max_requests)


def fetch_daily_trade_history(
    fetch_bytes: PageFetcher,
    window: TradeWindow,
    *,
    max_requests: int,
) -> TradeHistory:
    """Fetch an exact UTC-day-aligned range using one day as each root."""
    if window.start_ms % DAY_MS or window.end_ms % DAY_MS:
        raise ValueError("Deribit option-trade daily bounds must be UTC-day aligned")
    roots = [
        TradeWindow(start, start + DAY_MS)
        for start in range(window.start_ms, window.end_ms, DAY_MS)
    ]
    return _fetch_trade_windows(fetch_bytes, roots, max_requests=max_requests)


def _fetch_trade_windows(
    fetch_bytes: PageFetcher,
    roots: list[TradeWindow],
    *,
    max_requests: int,
) -> TradeHistory:
    if max_requests < 1:
        raise ValueError("Deribit option-trade max_requests must be positive")
    pending = deque(roots)
    pages: list[TradePage] = []
    terminal: list[TradePage] = []
    while pending:
        if len(pages) >= max_requests:
            raise ValueError("Deribit option-trade max_requests exhausted")
        current = pending.popleft()
        content = fetch_bytes(DERIBIT_OPTION_TRADES_URL, _trade_parameters(current))
        page = parse_trade_page(content, current)
        pages.append(page)
        if not page.has_more:
            terminal.append(page)
            continue
        left, right = _bisected(current)
        pending.appendleft(right)
        pending.appendleft(left)
    trades, duplicate_count = _unique_trades(terminal)
    return TradeHistory(
        pages=tuple(pages),
        terminal_windows=tuple(page.window for page in terminal),
        trades=trades,
        truncated_pages=sum(page.has_more for page in pages),
        duplicate_trades_removed=duplicate_count,
    )


def parse_instruments(content: bytes) -> tuple[OptionInstrument, ...]:
    """Parse and validate one official Deribit instrument response."""
    payload = _decoded_object(content)
    if "error" in payload:
        raise ValueError("Deribit instrument page returned JSON-RPC error")
    if payload.get("jsonrpc") != "2.0":
        raise ValueError("Deribit instrument JSON-RPC version drifted")
    result = payload.get("result")
    if not isinstance(result, list):
        raise ValueError("Deribit instrument result is not an array")
    instruments = tuple(
        _option_instrument(value, index) for index, value in enumerate(result, start=1)
    )
    names = [instrument.instrument_name for instrument in instruments]
    if len(names) != len(set(names)):
        raise ValueError("Deribit instruments contain duplicate names")
    return instruments


def parse_exact_instrument(content: bytes, expected_name: str) -> OptionInstrument:
    """Parse one official exact-name instrument response and bind its identity."""
    payload = _decoded_object(content)
    if "error" in payload:
        raise ValueError("Deribit exact-instrument page returned JSON-RPC error")
    if payload.get("jsonrpc") != "2.0":
        raise ValueError("Deribit exact-instrument JSON-RPC version drifted")
    instrument = _option_instrument(payload.get("result"), 1)
    if instrument.instrument_name != expected_name:
        raise ValueError("Deribit exact-instrument identity mismatch")
    return instrument


def _trade_parameters(window: TradeWindow) -> dict[str, str | int | bool]:
    return {
        "currency": "BTC",
        "kind": "option",
        "start_timestamp": window.start_ms,
        "end_timestamp": window.end_ms - 1,
        "count": 10_000,
        "include_old": True,
        "sorting": "asc",
    }


def _bisected(window: TradeWindow) -> tuple[TradeWindow, TradeWindow]:
    if window.end_ms - window.start_ms <= 1:
        raise ValueError("Deribit option-trade one-millisecond window is truncated")
    midpoint = window.start_ms + (window.end_ms - window.start_ms) // 2
    return (
        TradeWindow(window.start_ms, midpoint),
        TradeWindow(midpoint, window.end_ms),
    )


def _unique_trades(
    terminal_pages: list[TradePage],
) -> tuple[tuple[OptionTrade, ...], int]:
    by_id: dict[str, OptionTrade] = {}
    duplicates = 0
    for page in terminal_pages:
        for trade in page.trades:
            prior = by_id.get(trade.trade_id)
            if prior is None:
                by_id[trade.trade_id] = trade
            elif prior == trade:
                duplicates += 1
            else:
                raise ValueError(
                    f"Deribit option-trade ID {trade.trade_id} has conflicting rows"
                )
    ordered = sorted(
        by_id.values(), key=lambda trade: (trade.timestamp_ms, trade.trade_id)
    )
    return tuple(ordered), duplicates


def _decoded_object(content: bytes) -> dict[str, object]:
    if not isinstance(content, bytes) or not content:
        raise ValueError("Deribit option-trade page returned no bytes")
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Deribit option-trade page is invalid JSON") from exc
    return _object(payload, "root")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Deribit option-trade {label} is not an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"Deribit option-trade {label} has a non-string key")
    return value


def _option_trade(value: object, window: TradeWindow, row: int) -> OptionTrade:
    trade = _object(value, f"row {row}")
    timestamp = _integer(trade.get("timestamp"), row, "timestamp", minimum=0)
    if not window.start_ms <= timestamp < window.end_ms:
        raise ValueError(f"Deribit option-trade row {row} timestamp is out of window")
    direction = trade.get("direction")
    if direction not in ("buy", "sell"):
        raise ValueError(f"Deribit option-trade row {row} direction is invalid")
    instrument = _text(trade.get("instrument_name"), row, "instrument_name")
    if _INSTRUMENT.fullmatch(instrument) is None:
        raise ValueError(f"Deribit option-trade row {row} instrument is invalid")
    return OptionTrade(
        trade_id=_text(trade.get("trade_id"), row, "trade_id"),
        trade_seq=_integer(trade.get("trade_seq"), row, "trade_seq", minimum=0),
        instrument_name=instrument,
        timestamp_ms=timestamp,
        direction=direction,
        amount=_number(trade.get("amount"), row, "amount"),
        price=_number(trade.get("price"), row, "price"),
        index_price=_number(trade.get("index_price"), row, "index_price"),
        mark_price=_nonnegative_number(trade.get("mark_price"), row, "mark_price"),
        iv=_nonnegative_number(trade.get("iv"), row, "iv"),
        tick_direction=_integer(
            trade.get("tick_direction"), row, "tick_direction", minimum=0, maximum=3
        ),
        block_trade_id=_optional_text(
            trade.get("block_trade_id"), row, "block_trade_id"
        ),
        block_rfq_id=_optional_integer(trade.get("block_rfq_id"), row, "block_rfq_id"),
        combo_id=_optional_text(trade.get("combo_id"), row, "combo_id"),
        combo_trade_id=_optional_text(
            trade.get("combo_trade_id"), row, "combo_trade_id"
        ),
    )


def _option_instrument(value: object, row: int) -> OptionInstrument:
    instrument = _object(value, f"instrument row {row}")
    name = _text(instrument.get("instrument_name"), row, "instrument_name")
    if _INSTRUMENT.fullmatch(name) is None:
        raise ValueError(f"Deribit option-trade row {row} instrument is invalid")
    created = _integer(
        instrument.get("creation_timestamp"), row, "creation_timestamp", minimum=0
    )
    expires = _integer(
        instrument.get("expiration_timestamp"), row, "expiration_timestamp", minimum=0
    )
    if expires <= created:
        raise ValueError(f"Deribit option-trade row {row} expiry is not after creation")
    option_type = instrument.get("option_type")
    if option_type not in ("call", "put"):
        raise ValueError(f"Deribit option-trade row {row} option_type is invalid")
    suffix = "-C" if option_type == "call" else "-P"
    if not name.endswith(suffix):
        raise ValueError(
            f"Deribit option-trade row {row} option_type conflicts with name"
        )
    return OptionInstrument(
        instrument_name=name,
        creation_timestamp_ms=created,
        expiration_timestamp_ms=expires,
        strike=_number(instrument.get("strike"), row, "strike"),
        option_type=option_type,
        contract_size=_number(instrument.get("contract_size"), row, "contract_size"),
    )


def _text(value: object, row: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Deribit option-trade row {row} {label} is invalid")
    return value


def _optional_text(value: object, row: int, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, row, label)


def _optional_integer(value: object, row: int, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, row, label, minimum=0)


def _integer(
    value: object,
    row: int,
    label: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Deribit option-trade row {row} {label} is not integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"Deribit option-trade row {row} {label} is out of range")
    return value


def _number(value: object, row: int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Deribit option-trade row {row} {label} is not numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(
            f"Deribit option-trade row {row} {label} must be finite and positive"
        )
    return number


def _nonnegative_number(value: object, row: int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Deribit option-trade row {row} {label} is not numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(
            f"Deribit option-trade row {row} {label} must be finite and nonnegative"
        )
    return number
