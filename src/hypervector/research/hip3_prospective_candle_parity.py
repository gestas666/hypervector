"""Report-only parity for prospective HIP-3 trades and venue candles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import pandas as pd

from hypervector.data.hl_events import PublicTradeEvent
from hypervector.data.oxa_api import validate_market_symbol

_DEFAULT_TIMEFRAME_MINUTES = 15
_DEFAULT_PRICE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Hip3ProspectiveCandleParityConfig:
    """Frozen symbol, time window, and comparison tolerance."""

    symbol: str
    start_ms: int
    end_ms: int
    observed_at_ms: int
    timeframe_minutes: int = _DEFAULT_TIMEFRAME_MINUTES
    price_tolerance: float = _DEFAULT_PRICE_TOLERANCE

    def __post_init__(self) -> None:
        """Reject unaligned or non-causal comparison windows."""
        validate_market_symbol(self.symbol, "hip3")
        for name, value in (
            ("start_ms", self.start_ms),
            ("end_ms", self.end_ms),
            ("observed_at_ms", self.observed_at_ms),
            ("timeframe_minutes", self.timeframe_minutes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.start_ms >= self.end_ms or self.end_ms > self.observed_at_ms:
            raise ValueError("candle parity requires start < end <= observed_at")
        if self.start_ms % self.timeframe_ms or self.end_ms % self.timeframe_ms:
            raise ValueError("candle parity bounds must align to the timeframe")
        if not math.isfinite(self.price_tolerance) or self.price_tolerance < 0.0:
            raise ValueError("price_tolerance must be finite and nonnegative")

    @property
    def timeframe_ms(self) -> int:
        """Return the configured interval in milliseconds."""
        return self.timeframe_minutes * 60_000


def build_hip3_prospective_candle_parity(
    *,
    public_trades: Sequence[PublicTradeEvent],
    candles: pd.DataFrame,
    config: Hip3ProspectiveCandleParityConfig,
) -> dict[str, object]:
    """Compare receipt-bounded public-trade OHLC with completed venue candles."""
    unique, duplicate_rows = _validated_trades(public_trades, config)
    trade_bars = _trade_bars(unique, config)
    candle_bars = _candle_bars(candles, config)
    expected = tuple(range(config.start_ms, config.end_ms, config.timeframe_ms))
    diagnostics = _bar_diagnostics(expected, trade_bars, candle_bars, config)
    unresolved = len(diagnostics)
    coverage = _coverage(expected, trade_bars, candle_bars, diagnostics)
    return _report(
        config,
        public_trades,
        unique,
        duplicate_rows,
        candles,
        coverage,
        diagnostics,
        unresolved,
    )


def build_hip3_prospective_candle_frames(
    *,
    public_trades: Sequence[PublicTradeEvent],
    candles: pd.DataFrame,
    config: Hip3ProspectiveCandleParityConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return aligned public-trade and venue OHLC for completed bars."""
    unique, _duplicates = _validated_trades(public_trades, config)
    trade_rows = _trade_bars(unique, config)
    candle_rows = _candle_bars(candles, config)
    expected = tuple(range(config.start_ms, config.end_ms, config.timeframe_ms))
    missing_trade = sorted(set(expected).difference(trade_rows))
    missing_candle = sorted(set(expected).difference(candle_rows))
    if missing_trade or missing_candle:
        raise ValueError(
            "prospective candle frames require complete trade and venue bars"
        )
    index = pd.to_datetime(expected, unit="ms", utc=True)
    trade = pd.DataFrame([trade_rows[key] for key in expected], index=index)
    venue = pd.DataFrame([candle_rows[key] for key in expected], index=index)
    return trade, venue


def _validated_trades(
    trades: Sequence[PublicTradeEvent],
    config: Hip3ProspectiveCandleParityConfig,
) -> tuple[tuple[PublicTradeEvent, ...], int]:
    by_id: dict[int, PublicTradeEvent] = {}
    duplicate_rows = 0
    for trade in trades:
        _validate_trade(trade, config)
        previous = by_id.get(trade.trade_id)
        if previous is None:
            by_id[trade.trade_id] = trade
            continue
        duplicate_rows += 1
        if _trade_signature(previous) != _trade_signature(trade):
            raise ValueError(f"conflicting duplicate trade_id {trade.trade_id}")
    ordered = sorted(by_id.values(), key=lambda row: (row.exchange_ts_ms, row.trade_id))
    return tuple(ordered), duplicate_rows


def _validate_trade(
    trade: PublicTradeEvent,
    config: Hip3ProspectiveCandleParityConfig,
) -> None:
    if trade.symbol != config.symbol:
        raise ValueError("prospective candle parity trade symbol is inconsistent")
    if trade.source != "hyperliquid_ws_trades":
        raise ValueError("prospective candle parity trade source is invalid")
    if trade.received_ts_ns // 1_000_000 > config.observed_at_ms:
        raise ValueError("trade receipt exceeds observed_at_ms")


def _trade_signature(trade: PublicTradeEvent) -> tuple[object, ...]:
    return (
        trade.symbol,
        trade.exchange_ts_ms,
        trade.aggressor_side,
        trade.price,
        trade.size,
        trade.transaction_hash,
        trade.buyer,
        trade.seller,
    )


def _trade_bars(
    trades: Sequence[PublicTradeEvent],
    config: Hip3ProspectiveCandleParityConfig,
) -> dict[int, dict[str, float]]:
    grouped: dict[int, list[PublicTradeEvent]] = {}
    for trade in trades:
        if config.start_ms <= trade.exchange_ts_ms < config.end_ms:
            bar_open = trade.exchange_ts_ms // config.timeframe_ms * config.timeframe_ms
            grouped.setdefault(bar_open, []).append(trade)
    return {bar_open: _trade_ohlc(rows) for bar_open, rows in grouped.items()}


def _trade_ohlc(rows: Sequence[PublicTradeEvent]) -> dict[str, float]:
    ordered = sorted(rows, key=lambda row: (row.exchange_ts_ms, row.trade_id))
    prices = [row.price for row in ordered]
    return {
        "open": prices[0],
        "high": max(prices),
        "low": min(prices),
        "close": prices[-1],
    }


def _candle_bars(
    candles: pd.DataFrame,
    config: Hip3ProspectiveCandleParityConfig,
) -> dict[int, dict[str, float]]:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(candles.columns)
    if missing:
        raise ValueError(f"venue candles missing columns: {sorted(missing)}")
    frame = candles.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if frame["timestamp"].duplicated().any():
        raise ValueError("venue candles contain duplicate timestamps")
    timestamp_ms = frame["timestamp"].dt.as_unit("ns").astype("int64") // 1_000_000
    selected = frame.loc[
        (timestamp_ms >= config.start_ms) & (timestamp_ms < config.end_ms)
    ].copy()
    selected["timestamp_ms"] = timestamp_ms.loc[selected.index]
    return _validated_candle_rows(selected, config)


def _validated_candle_rows(
    frame: pd.DataFrame,
    config: Hip3ProspectiveCandleParityConfig,
) -> dict[int, dict[str, float]]:
    output: dict[int, dict[str, float]] = {}
    for row in frame.itertuples(index=False):
        timestamp_ms = int(row.timestamp_ms)
        if timestamp_ms % config.timeframe_ms:
            raise ValueError("venue candle timestamp is not timeframe aligned")
        values = {name: float(getattr(row, name)) for name in _ohlc_fields()}
        if any(not math.isfinite(value) or value <= 0.0 for value in values.values()):
            raise ValueError("venue candle OHLC must be finite and positive")
        output[timestamp_ms] = values
    return output


def _bar_diagnostics(
    expected: Sequence[int],
    trades: dict[int, dict[str, float]],
    candles: dict[int, dict[str, float]],
    config: Hip3ProspectiveCandleParityConfig,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for bar_open in expected:
        if bar_open not in trades:
            rows.append(_diagnostic(bar_open, "missing_trade_bar"))
        elif bar_open not in candles:
            rows.append(_diagnostic(bar_open, "missing_candle_bar"))
        else:
            fields = _mismatched_fields(trades[bar_open], candles[bar_open], config)
            if fields:
                rows.append(_diagnostic(bar_open, "ohlc_mismatch", fields))
    return rows


def _mismatched_fields(
    trade: dict[str, float],
    candle: dict[str, float],
    config: Hip3ProspectiveCandleParityConfig,
) -> list[str]:
    return [
        name
        for name in _ohlc_fields()
        if abs(trade[name] - candle[name]) > config.price_tolerance
    ]


def _diagnostic(
    bar_open_ms: int,
    status: str,
    mismatched_fields: list[str] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {"bar_open_ms": bar_open_ms, "status": status}
    if mismatched_fields is not None:
        row["mismatched_fields"] = mismatched_fields
    return row


def _coverage(
    expected: Sequence[int],
    trades: dict[int, dict[str, float]],
    candles: dict[int, dict[str, float]],
    diagnostics: Sequence[dict[str, object]],
) -> dict[str, int]:
    statuses = [str(row["status"]) for row in diagnostics]
    overlap = set(trades).intersection(candles).intersection(expected)
    mismatches = statuses.count("ohlc_mismatch")
    return {
        "expected_bars": len(expected),
        "trade_bars": len(set(trades).intersection(expected)),
        "candle_bars": len(set(candles).intersection(expected)),
        "overlap_bars": len(overlap),
        "exact_ohlc_bars": len(overlap) - mismatches,
        "missing_trade_bars": statuses.count("missing_trade_bar"),
        "missing_candle_bars": statuses.count("missing_candle_bar"),
        "mismatched_ohlc_bars": mismatches,
    }


def _report(
    config: Hip3ProspectiveCandleParityConfig,
    raw_trades: Sequence[PublicTradeEvent],
    unique_trades: Sequence[PublicTradeEvent],
    duplicate_rows: int,
    candles: pd.DataFrame,
    coverage: dict[str, int],
    diagnostics: list[dict[str, object]],
    unresolved: int,
) -> dict[str, object]:
    comparison_trades = tuple(
        trade
        for trade in unique_trades
        if config.start_ms <= trade.exchange_ts_ms < config.end_ms
    )
    comparison_candles = _candle_bars(candles, config)
    return {
        "schema_version": "hip3_prospective_candle_parity_v1",
        "contract": _contract(),
        "scope": asdict(config),
        "source": {
            "raw_trade_rows": len(raw_trades),
            "unique_trade_rows": len(unique_trades),
            "duplicate_trade_rows": duplicate_rows,
            "trade_sha256": _trade_hash(unique_trades),
            "comparison_trade_rows": len(comparison_trades),
            "comparison_trade_sha256": _trade_hash(comparison_trades),
            "candle_sha256": _candle_hash(candles),
            "comparison_candle_rows": len(comparison_candles),
            "comparison_candle_sha256": _bar_hash(comparison_candles),
        },
        "coverage": coverage,
        "bar_diagnostics": diagnostics,
        "technical_assessment": {
            "candle_ohlc_parity_resolved": bool(coverage["expected_bars"])
            and unresolved == 0,
            "unresolved_bars": unresolved,
        },
        "limitations": [
            "OHLC source parity does not establish strategy profitability",
            "trade-tape parity does not model queue position or execution slippage",
            "this report grants no execution or promotion authority",
        ],
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }


def _trade_hash(trades: Sequence[PublicTradeEvent]) -> str:
    rows = sorted(
        json.dumps(asdict(trade), sort_keys=True, separators=(",", ":"))
        for trade in trades
    )
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _candle_hash(candles: pd.DataFrame) -> str:
    payload = candles.to_json(orient="records", date_format="iso", double_precision=15)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bar_hash(rows: Mapping[int, Mapping[str, float]]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ohlc_fields() -> tuple[str, ...]:
    return ("open", "high", "low", "close")
