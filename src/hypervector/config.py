"""Research configuration and lookback validation (SRS_HV1_HIST_*)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FLOOR_LOOKBACK = 30
DEFAULT_LOOKBACK = 90
PROMO_LOOKBACK = 180

DEFAULT_SYMBOL = "BTC"
DEFAULT_TIMEFRAME = "1m"
DEFAULT_BACKFILL_PRIORITY = ("binance", "bybit")


def validate_lookback(days: int) -> int:
    """Return lookback days if >= floor; raise ValueError otherwise."""
    if days < FLOOR_LOOKBACK:
        raise ValueError(f"lookback_days must be >= {FLOOR_LOOKBACK} (got {days})")
    return days


@dataclass(frozen=True)
class ResearchConfig:
    """Phase 1 research defaults: BTC 1m, 90d lookback, backfill allowed."""

    symbol: str = DEFAULT_SYMBOL
    timeframe: str = DEFAULT_TIMEFRAME
    lookback_days: int = DEFAULT_LOOKBACK
    backfill_priority: tuple[str, ...] = DEFAULT_BACKFILL_PRIORITY
    strict_hl_only: bool = False
    fee_model: str = "hl_taker_default"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_lookback(self.lookback_days)
