"""Fresh, contiguous warm-up history for the paper/shadow daemon.

The daemon loads the research window (``SYMBOL_TF_<lb>d``) through
:func:`hypervector.data.pipeline.load_research_history`, which refreshes a
window older than a day when it can (and writes the refreshed cache). When that
refresh fails, for example during a Binance or Bybit outage, the runner warms
up from the cached window as is (or the HL-only window the failed load kept).
Either way, before live decisions run on it, the daemon tops up the missing
tail from public Hyperliquid candles here, in memory only (this top-up never
writes the shared cache):

* the last cached candle is always re-fetched, because the cache usually ends
  with the candle that was still forming when it was saved;
* if the missing span is longer than the indicator buffer, the old cache
  cannot connect to fresh data and is dropped instead of spliced, so the
  buffer never mixes months-old bars with today's;
* a resumed shadow state extends the window back to a full indicator buffer
  before its reconciliation timestamp, so downtime replay keeps venue coverage
  and a full seed where HL still has it;
* a failed refresh is a technical failure and aborts start-up (fail-closed).

Internal venue gaps are reported, never refused; no trading gate is added.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv
from hypervector.data.provenance import normalize_ohlcv
from hypervector.nautilus.actor import DEFAULT_MAX_LOOKBACK
from hypervector.paper.live_node import filter_bars_after, timeframe_delta

logger = logging.getLogger(__name__)

WarmTailFetcher = Callable[..., pd.DataFrame]


def refresh_warm_history(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    now: pd.Timestamp,
    fetcher: WarmTailFetcher | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return warm-up bars whose tail is current at ``now`` plus provenance."""
    step = timeframe_delta(timeframe)
    observed = _utc(now)
    cached = filter_bars_after(frame, after_ts=None)
    if cached.empty:
        raise RuntimeError(f"no warm-up bars for {symbol} {timeframe}")
    cached = cached.sort_values("timestamp").reset_index(drop=True)
    last_open = pd.Timestamp(cached["timestamp"].iloc[-1])
    provenance: dict[str, Any] = {
        "cache_bars": int(len(cached)),
        "cache_last_open": last_open.isoformat(),
    }
    if last_open + step > observed:
        # The newest cached candle is still forming; the causal boundary drops it.
        provenance.update(mode="cache_fresh", tail_bars=0)
        return cached, provenance

    floor_start = observed - step * (DEFAULT_MAX_LOOKBACK + 1)
    # Start one bar early: the window round-trips through float days and
    # millisecond truncation, and the last cached candle must be re-fetched.
    connects = last_open - step >= floor_start
    start = last_open - step if connects else floor_start
    window_days = (observed - start) / pd.Timedelta(days=1)
    fetch = fetcher if fetcher is not None else fetch_hl_ohlcv
    try:
        tail = fetch(symbol, timeframe, window_days)
    except Exception as exc:  # network/venue failure: fail closed
        raise RuntimeError(
            f"warm-up history stale for {symbol} {timeframe}: cache ends "
            f"{last_open.isoformat()} and the Hyperliquid tail refresh failed: {exc}"
        ) from exc
    tail = _normalized_tail(tail)
    provenance.update(
        tail_requested_from=start.isoformat(),
        tail_bars=int(len(tail)),
    )
    if tail.empty:
        if not connects:
            raise RuntimeError(
                f"warm-up history stale for {symbol} {timeframe}: cache ends "
                f"{last_open.isoformat()} and Hyperliquid returned no candles since "
                f"{start.isoformat()}"
            )
        logger.warning(
            "warm-up tail refresh returned no candles after %s; keeping cache",
            last_open.isoformat(),
        )
        provenance.update(mode="cache_venue_quiet")
        return cached, provenance
    if connects:
        merged = pd.concat([cached, tail], ignore_index=True)
        merged = (
            merged.drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        mode = "tail_merged"
    else:
        logger.warning(
            "warm-up cache ends %s, beyond the %s-bar buffer; using fresh tail only",
            last_open.isoformat(),
            DEFAULT_MAX_LOOKBACK,
        )
        merged = tail
        mode = "tail_replaced_stale_cache"
    newest = pd.Timestamp(merged["timestamp"].iloc[-1])
    if newest + 2 * step < observed:
        logger.warning(
            "warm-up tail ends %s (%s before %s); venue returned no newer candles",
            newest.isoformat(),
            observed - newest - step,
            observed.isoformat(),
        )
    provenance.update(
        mode=mode,
        warm_bars=int(len(merged)),
        warm_last_open=newest.isoformat(),
    )
    return merged, provenance


def _normalized_tail(tail: pd.DataFrame | None) -> pd.DataFrame:
    if tail is None or not isinstance(tail, pd.DataFrame) or tail.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "source"])
    normalized = normalize_ohlcv(tail, source="hl")
    return normalized.drop_duplicates(subset=["timestamp"], keep="last").reset_index(
        drop=True
    )



def _utc(value: str | pd.Timestamp) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")
