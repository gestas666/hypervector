"""Bounded market inputs for the HIP-3 lifecycle command."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from hypervector.live.hip3_breakout_shadow_specs import Hip3BreakoutShadowSpec
from hypervector.research.hip3_shadow_command_sources import (
    CandleFetcher,
    FundingFetcher,
    completed_candles,
    funding_snapshot,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHip3MarkArchive,
    Hip3MarkSourceProtocol,
)

_SIGNAL_INTERVAL_MS = 15 * 60_000
_PROFIT_LOCK_INTERVAL_MS = 60_000


@dataclass(frozen=True)
class Hip3ShadowMarketInputs:
    """Verified price, funding, and mark-path command inputs."""

    candles: pd.DataFrame
    profit_lock_bars: pd.DataFrame | None
    funding: pd.DataFrame
    mark_source: Hip3MarkSourceProtocol
    marks: tuple[dict[str, object], ...]
    mark_evidence: dict[str, object]


def load_shadow_market_inputs(
    *,
    candle_fetcher: CandleFetcher,
    funding_fetcher: FundingFetcher,
    mark_source: Hip3MarkSourceProtocol | None,
    data_root: Path,
    spec: Hip3BreakoutShadowSpec,
    config: Hip3ShadowLifecycleConfig,
    start_ms: int,
    observed_at_ms: int,
    signal_start_ms: int | None = None,
) -> Hip3ShadowMarketInputs:
    """Acquire only the causally completed inputs required by one replay."""
    signal_start = start_ms if signal_start_ms is None else signal_start_ms
    if signal_start > start_ms:
        raise ValueError("HIP-3 signal warmup cannot start after lifecycle evidence")
    candles = completed_candles(
        candle_fetcher,
        spec.symbol,
        "15m",
        _SIGNAL_INTERVAL_MS,
        signal_start,
        observed_at_ms,
    )
    lock_bars = _profit_lock_bars(
        candle_fetcher, spec, config, start_ms, observed_at_ms
    )
    funding = funding_snapshot(funding_fetcher, spec.symbol, candles, observed_at_ms)
    source = mark_source or FrozenHip3MarkArchive()
    marks, evidence = source.load(
        data_root=data_root,
        symbol=spec.symbol,
        start_ms=start_ms,
        end_ms=observed_at_ms,
    )
    return Hip3ShadowMarketInputs(candles, lock_bars, funding, source, marks, evidence)


def _profit_lock_bars(
    fetcher: CandleFetcher,
    spec: Hip3BreakoutShadowSpec,
    config: Hip3ShadowLifecycleConfig,
    start_ms: int,
    observed_at_ms: int,
) -> pd.DataFrame | None:
    if config.profit_lock_policy is None:
        return None
    return completed_candles(
        fetcher,
        spec.symbol,
        "1m",
        _PROFIT_LOCK_INTERVAL_MS,
        start_ms,
        observed_at_ms,
    )
