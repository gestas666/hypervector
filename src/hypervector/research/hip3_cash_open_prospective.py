"""Prospective, report-only reconstruction of HIP-3 cash-open signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

import pandas as pd

from hypervector.data.hl_events import PublicTradeEvent, StreamGap
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    build_hip3_cash_open_gap_reversal_signals,
    cash_session_bar_opens,
)

_BAR_MINUTES = 15
_BAR_MS = _BAR_MINUTES * 60_000
_TRADE_SOURCE = "hyperliquid_ws_trades"


@dataclass(frozen=True)
class Hip3CashOpenProspectiveSpec:
    """Frozen identity for one execution-incapable prospective measurement."""

    symbol: str
    provider_id: str
    profile_id: str
    signal: Hip3CashOpenGapReversalConfig = Hip3CashOpenGapReversalConfig()

    def __post_init__(self) -> None:
        """Reject aliased assets or anonymous strategy identities."""
        validate_market_symbol(self.symbol, "hip3")
        if not self.provider_id.strip() or not self.profile_id.strip():
            raise ValueError("cash-open prospective identity must be non-empty")


def build_hip3_cash_open_prospective_report(
    *,
    trades: tuple[PublicTradeEvent, ...],
    start_ms: int,
    end_ms: int,
    observed_at_ms: int,
    spec: Hip3CashOpenProspectiveSpec,
) -> dict[str, object]:
    """Reconstruct the unchanged route over one completed prospective prefix."""
    _validate_window(start_ms, end_ms, observed_at_ms)
    scoped = _scoped_trades(trades, start_ms, end_ms, observed_at_ms, spec.symbol)
    canonical, duplicates = _canonical_trades(scoped)
    bars = _trade_bars(canonical, start_ms, end_ms, spec.signal)
    signals = build_hip3_cash_open_gap_reversal_signals(bars, spec.signal)
    return _report(spec, scoped, canonical, duplicates, bars, signals, start_ms, end_ms)


def build_receipt_causal_cash_open_trade_bars(
    *,
    trades: tuple[PublicTradeEvent, ...],
    gaps: tuple[StreamGap, ...] = (),
    symbol: str,
    start_ms: int,
    end_ms: int,
    observed_at_ms: int,
    config: Hip3CashOpenGapReversalConfig = Hip3CashOpenGapReversalConfig(),
) -> pd.DataFrame:
    """Build complete 15-minute public-trade OHLC without future receipts."""
    _validate_window(start_ms, end_ms, observed_at_ms)
    scoped = _scoped_trades(trades, start_ms, end_ms, observed_at_ms, symbol)
    scoped_gaps = _scoped_gaps(gaps, symbol, observed_at_ms)
    canonical, _duplicates = _canonical_trades(scoped)
    return _trade_bars(canonical, start_ms, end_ms, config, scoped_gaps)


def _scoped_trades(
    trades: tuple[PublicTradeEvent, ...],
    start_ms: int,
    end_ms: int,
    observed_at_ms: int,
    symbol: str,
) -> tuple[PublicTradeEvent, ...]:
    selected: list[PublicTradeEvent] = []
    for trade in trades:
        if trade.symbol != symbol or trade.source != _TRADE_SOURCE:
            raise ValueError("cash-open prospective trade identity is inconsistent")
        if trade.received_ts_ns // 1_000_000 > observed_at_ms:
            continue
        if start_ms <= trade.exchange_ts_ms < end_ms:
            selected.append(trade)
    if not selected:
        raise ValueError("cash-open prospective window has no exact public trades")
    return tuple(selected)


def _canonical_trades(
    trades: tuple[PublicTradeEvent, ...],
) -> tuple[tuple[PublicTradeEvent, ...], int]:
    selected: dict[int, PublicTradeEvent] = {}
    for trade in trades:
        previous = selected.get(trade.trade_id)
        if previous is not None and _venue_identity(previous) != _venue_identity(trade):
            raise ValueError("conflicting public trade identity")
        if previous is None or trade.received_ts_ns < previous.received_ts_ns:
            selected[trade.trade_id] = trade
    ordered = tuple(
        sorted(selected.values(), key=lambda row: (row.exchange_ts_ms, row.trade_id))
    )
    return ordered, len(trades) - len(ordered)


def _scoped_gaps(
    gaps: tuple[StreamGap, ...],
    symbol: str,
    observed_at_ms: int,
) -> tuple[StreamGap, ...]:
    """Validate gap identity and retain only receipt-causal declarations."""
    if any(gap.symbol != symbol for gap in gaps):
        raise ValueError("cash-open prospective gap identity is inconsistent")
    return tuple(
        gap for gap in gaps if gap.detected_ts_ns // 1_000_000 <= observed_at_ms
    )


def _venue_identity(trade: PublicTradeEvent) -> tuple[object, ...]:
    return (
        trade.symbol,
        trade.aggressor_side,
        trade.price,
        trade.size,
        trade.transaction_hash,
        trade.exchange_ts_ms,
        trade.trade_id,
        trade.buyer,
        trade.seller,
        trade.source,
    )


def _trade_bars(
    trades: tuple[PublicTradeEvent, ...],
    start_ms: int,
    end_ms: int,
    config: Hip3CashOpenGapReversalConfig,
    gaps: tuple[StreamGap, ...] = (),
) -> pd.DataFrame:
    values = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [trade.exchange_ts_ms for trade in trades], unit="ms", utc=True
            ),
            "price": [trade.price for trade in trades],
            "size": [trade.size for trade in trades],
        }
    )
    values["bar_open"] = values["timestamp"].dt.floor(f"{_BAR_MINUTES}min")
    bars = values.groupby("bar_open", sort=True).agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("size", "sum"),
        public_trade_count=("price", "size"),
    )
    expected = cash_session_bar_opens(start_ms, end_ms, config)
    if expected.empty:
        raise ValueError("cash-open prospective window has no scheduled cash bars")
    bars = bars.reindex(bars.index.intersection(expected))
    if bars.empty:
        raise ValueError(
            "cash-open prospective window has no exact cash-session trades"
        )
    bars["gap_before_bars"] = _cash_bar_gap_counts(expected, bars.index, gaps)
    return bars


def _cash_bar_gap_counts(
    expected: pd.DatetimeIndex,
    observed: pd.DatetimeIndex,
    gaps: tuple[StreamGap, ...],
) -> list[int]:
    trade_gaps = tuple(gap for gap in gaps if _contains_trade_channel(gap.channel))
    declared = [
        sum(
            _gap_overlaps_bar(gap, int(timestamp.timestamp() * 1_000))
            for gap in trade_gaps
        )
        for timestamp in observed
    ]
    missing = _missing_cash_bar_counts(expected, observed)
    return [left + right for left, right in zip(missing, declared, strict=True)]


def _missing_cash_bar_counts(
    expected: pd.DatetimeIndex,
    observed: pd.DatetimeIndex,
) -> list[int]:
    positions = expected.get_indexer(observed)
    previous = -1
    result: list[int] = []
    for position in positions:
        if position < 0:
            raise ValueError("cash-open observed bar is outside the session schedule")
        result.append(int(position) - previous - 1)
        previous = int(position)
    return result


def _contains_trade_channel(channel: str) -> bool:
    return "trades" in {value.strip() for value in channel.split(",")}


def _gap_overlaps_bar(gap: StreamGap, bar_open_ms: int) -> bool:
    detected_ms = gap.detected_ts_ns // 1_000_000
    left = gap.previous_exchange_ts_ms or detected_ms
    right = gap.next_exchange_ts_ms or detected_ms
    lower, upper = sorted((left, right))
    return lower < bar_open_ms + _BAR_MS and upper > bar_open_ms


def _report(
    spec: Hip3CashOpenProspectiveSpec,
    scoped: tuple[PublicTradeEvent, ...],
    canonical: tuple[PublicTradeEvent, ...],
    duplicates: int,
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    decisions = signals["session_eligible"].astype(bool) & signals["local_minute"].eq(
        570
    )
    scorable = decisions & signals["previous_cash_close"].notna()
    events = _entry_events(signals)
    return {
        "schema_version": "hip3_cash_open_prospective_v1",
        "contract": _contract(),
        "strategy_identity": _strategy_identity(spec),
        "source": {
            "symbol": spec.symbol,
            "source": _TRADE_SOURCE,
            "raw_trade_rows": len(scoped),
            "raw_trade_sha256": _trade_hash(scoped),
            "canonical_trade_rows": len(canonical),
            "duplicate_trade_rows": duplicates,
            "canonical_trade_sha256": _trade_hash(canonical),
        },
        "coverage": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "completed_bars": len(bars),
            "cash_open_decisions": int(decisions.sum()),
            "scorable_cash_open_decisions": int(scorable.sum()),
            "unscorable_cash_open_decisions": int((decisions & ~scorable).sum()),
        },
        "signals": {"entry_events": events, "entry_count": len(events)},
        "assessment": {
            "prospective_entries_observed": bool(events),
            "profitability_established": False,
            "promotion_authority": "none",
        },
        "limitations": [
            "a zero-entry window does not falsify a sparse strategy by itself",
            "signal reconstruction does not establish lifecycle profitability",
            "only exact public-trade OHLC is used; no candle fallback is accepted",
        ],
    }


def _entry_events(signals: pd.DataFrame) -> list[dict[str, object]]:
    entries = signals.loc[signals["long_entry"] | signals["short_entry"]]
    return [
        {
            "bar_open_ms": int(timestamp.as_unit("ms").value),
            "decision_time_ms": int(timestamp.as_unit("ms").value) + _BAR_MS,
            "side": "long" if bool(row["long_entry"]) else "short",
            "opening_gap_bps": float(row["opening_gap_bps"]),
            "target_price": float(row["target_price"]),
            "stop_price": float(row["stop_price"]),
        }
        for timestamp, row in entries.iterrows()
    ]


def _strategy_identity(spec: Hip3CashOpenProspectiveSpec) -> dict[str, object]:
    signal = asdict(spec.signal)
    signal["closed_session_dates"] = [
        value.isoformat() for value in spec.signal.closed_session_dates
    ]
    signal["early_close_minutes"] = [
        {"date": value.isoformat(), "minute": minute}
        for value, minute in spec.signal.early_close_minutes
    ]
    return {
        "provider_id": spec.provider_id,
        "profile_id": spec.profile_id,
        "timeframe": "15m",
        **signal,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
        "parameters_tuned_on_prospective_window": False,
    }


def _trade_hash(trades: tuple[PublicTradeEvent, ...]) -> str:
    rows = sorted(
        json.dumps(asdict(trade), sort_keys=True, separators=(",", ":"))
        for trade in trades
    )
    payload = "\n".join(rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_window(start_ms: int, end_ms: int, observed_at_ms: int) -> None:
    for label, value in (
        ("start_ms", start_ms),
        ("end_ms", end_ms),
        ("observed_at_ms", observed_at_ms),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    if start_ms >= end_ms or end_ms > observed_at_ms:
        raise ValueError("cash-open prospective window must be completed and ordered")
    if start_ms % _BAR_MS or end_ms % _BAR_MS:
        raise ValueError("cash-open prospective window must be 15m aligned")
