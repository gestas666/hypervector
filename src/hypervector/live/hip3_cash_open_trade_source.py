"""Receipt-causal public-trade bars for the SPCX cash-open provider."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

import pandas as pd

from hypervector.data.hl_events import PublicTradeEvent, StreamGap
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
    spcx_cash_open_live_config,
)
from hypervector.research.hip3_cash_open_prospective import (
    build_receipt_causal_cash_open_trade_bars,
)

_BAR_MS = 900_000
_LOOKBACK_MS = 7 * 86_400_000
SPCX_CAPTURE_START_MS = 1_786_665_600_000


class CashOpenEventArchiveProtocol(Protocol):
    """Read the persisted event window required by one cash-open decision."""

    def replay_trade_window(self, start: datetime, end: datetime) -> Sequence[object]:
        """Return persisted public trades and gaps in one UTC interval."""


class Hip3CashOpenTradeBarSource:
    """Construct complete public-trade OHLC from an exact local archive."""

    def __init__(
        self,
        *,
        archive: CashOpenEventArchiveProtocol,
        symbol: str,
        capture_start_ms: int,
        config: Hip3CashOpenGapReversalConfig | None = None,
    ) -> None:
        """Bind one exact symbol and authenticated full-bar capture boundary."""
        validate_market_symbol(symbol, "hip3")
        if capture_start_ms <= 0 or capture_start_ms % _BAR_MS:
            raise ValueError("cash-open capture start must be a positive 15m boundary")
        self._archive = archive
        self._symbol = symbol
        self._capture_start_ms = capture_start_ms
        self._config = config or spcx_cash_open_live_config()

    def completed_bars(
        self,
        *,
        observed_at_ms: int,
        minimum_start_ms: int,
    ) -> pd.DataFrame:
        """Return the bounded complete prefix visible at the receipt cutoff."""
        end_ms = observed_at_ms // _BAR_MS * _BAR_MS
        start_ms = max(
            self._capture_start_ms,
            minimum_start_ms // _BAR_MS * _BAR_MS,
            end_ms - _LOOKBACK_MS,
        )
        if start_ms >= end_ms:
            raise Hip3ObserverUnavailableError("cash_open_completed_window_unavailable")
        rows = tuple(
            self._archive.replay_trade_window(_utc(start_ms), _utc(observed_at_ms))
        )
        trades = tuple(row for row in rows if isinstance(row, PublicTradeEvent))
        gaps = tuple(row for row in rows if isinstance(row, StreamGap))
        try:
            return build_receipt_causal_cash_open_trade_bars(
                trades=trades,
                gaps=gaps,
                symbol=self._symbol,
                start_ms=start_ms,
                end_ms=end_ms,
                observed_at_ms=observed_at_ms,
                config=self._config,
            )
        except ValueError as exc:
            if "no exact public trades" in str(exc):
                raise Hip3ObserverUnavailableError(
                    "cash_open_trade_rows_unavailable"
                ) from exc
            if "missing trade bars" in str(
                exc
            ) or "no exact cash-session trades" in str(exc):
                raise Hip3ObserverUnavailableError(
                    "cash_open_trade_bars_incomplete"
                ) from exc
            raise


def _utc(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1_000.0, tz=UTC)
