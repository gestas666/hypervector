"""Prospective first-observed one-minute candles for HIP-3 exit evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.live.hip3_shadow_candle_contracts import (
    hip3_shadow_candle_contract,
)
from hypervector.live.hip3_shadow_candle_storage import (
    ShadowCandleAppendResult,
    ShadowCandleContract,
    append_candles_once,
    jsonl_rows,
    validate_candle_row,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError

_INTERVAL_MS = 60_000


class Hip3ProfitLockCandleSource(Protocol):
    """Unsigned candle source used by the report-only capture path."""

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        """Return public candles with a post-fetch receipt timestamp attribute."""


class Hip3ProfitLockCandleCapture:
    """Append each completed one-minute source candle at most once."""

    def __init__(
        self, source: Hip3ProfitLockCandleSource, symbol: str, path: Path
    ) -> None:
        """Bind one exact observer route and restore its durable boundary."""
        self._source = source
        self._symbol = symbol
        self._path = path
        self._contract = hip3_shadow_candle_contract(symbol, "1m")
        self._last_boundary_ms = _restore_boundary(path, self._contract)

    def poll(self, observed_at_ms: int) -> ShadowCandleAppendResult | None:
        """Capture a new completed minute using its post-fetch receipt time."""
        observed = _positive_integer(observed_at_ms, "observation timestamp")
        boundary = observed // _INTERVAL_MS * _INTERVAL_MS
        if self._last_boundary_ms is not None and boundary <= self._last_boundary_ms:
            return None
        fetched = self._source.completed_candle_history(
            observed_at_ms=observed, timeframe="1m"
        )
        received = _receipt_timestamp(fetched, observed)
        frame = _completed_frame(
            fetched,
            received,
            boundary,
            source=self._contract.source,
        )
        prior = boundary if self._last_boundary_ms is None else self._last_boundary_ms
        result = append_candles_once(
            self._path,
            frame,
            contract=self._contract,
            observed_at_ms=received,
            prior_boundary_ms=prior,
        )
        self._last_boundary_ms = boundary
        return result


def profit_lock_candle_path(journal: Path) -> Path:
    """Return the deterministic sibling ledger for one decision journal."""
    return journal.with_name(f"{journal.stem}_profit_lock_candles.jsonl")


def _completed_frame(
    fetched: pd.DataFrame,
    received_ms: int,
    required_boundary_ms: int,
    *,
    source: str,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(fetched.columns))
    if missing:
        raise ValueError(f"HIP-3 profit-lock source missing columns: {missing}")
    frame = fetched.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    completed = frame["timestamp"] + pd.Timedelta(minutes=1) <= pd.Timestamp(
        received_ms, unit="ms", tz="UTC"
    )
    output = frame.loc[completed].sort_values("timestamp").set_index("timestamp")
    if output.empty or _close_boundary(output.index[-1]) < required_boundary_ms:
        raise TransientCohortMarketDataError(
            source=source,
            reason="latest_completed_minute_unavailable",
        )
    if output.index.has_duplicates:
        raise ValueError("HIP-3 profit-lock source contains duplicate candles")
    return output.loc[:, ["open", "high", "low", "close", "volume"]]


def _restore_boundary(path: Path, contract: ShadowCandleContract) -> int | None:
    if not path.exists():
        return None
    rows = jsonl_rows(path, "profit-lock candle")
    for row in rows:
        validate_candle_row(row, contract)
    return max(int(row["bar_close_ms"]) for row in rows)


def _receipt_timestamp(frame: pd.DataFrame, observed_ms: int) -> int:
    received = _positive_integer(frame.attrs.get("received_at_ms"), "receipt timestamp")
    if received < observed_ms:
        raise ValueError("HIP-3 profit-lock receipt timestamp predates its request")
    return received


def _close_boundary(timestamp: pd.Timestamp) -> int:
    return int(timestamp.as_unit("ns").value // 1_000_000) + _INTERVAL_MS


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"HIP-3 profit-lock {label} must be a positive integer")
    return value
