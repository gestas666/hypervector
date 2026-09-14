"""Causal continuous candle acquisition with explicit source windows and cold-span scenarios."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
import math

import pandas as pd

from hypervector.research.native_replay_clock import ReplayClock
from hypervector.research.native_replay_events import require_clock, require_name

MINUTE_MS = 60_000
DAY_MS = 86_400_000
CANDLE_COLUMNS = frozenset({"timestamp", "open", "high", "low", "close", "volume"})


@dataclass(frozen=True)
class HistoricalCandleSource:
    """One explicitly identified half-open source window; missing minutes remain absent."""

    identity: str
    start_ms: int
    end_ms: int
    frame: pd.DataFrame

    def __post_init__(self) -> None:
        """Require explicit source identity and a valid declared acquisition interval."""
        require_name(self.identity, "historical candle source")
        require_clock(self.start_ms, "source start")
        require_clock(self.end_ms, "source end")
        if self.end_ms <= self.start_ms:
            raise ValueError("historical candle source requires start before end")


@dataclass(frozen=True)
class HistoricalFetchReceipt:
    """One successful native request with separate cutoff, response and source identities."""

    symbol: str
    source_identity: str
    cold: bool
    cutoff_ms: int
    start_ms: int
    dispatched_ms: int
    received_ms: int
    rows: int


class HistoricalNativeFetch:
    """Feed the real native poller without future bars, invented gaps or hidden row caps."""

    def __init__(
        self,
        *,
        clock: ReplayClock,
        sources: Mapping[str, HistoricalCandleSource],
        cold_span_ms: Mapping[str, int],
        elapsed_ms: Callable[[str, bool], int],
        record_request: Callable[[HistoricalFetchReceipt], None] | None = None,
    ) -> None:
        """Snapshot explicit source frames and require a cold-span/latency policy for every asset."""
        if not sources or set(sources) != set(cold_span_ms):
            raise ValueError("historical source and cold-span universes must match exactly")
        for symbol, span in cold_span_ms.items():
            require_name(symbol, "historical symbol")
            require_clock(span, "historical cold span")
            if span == 0:
                raise ValueError("historical cold spans must be positive")
        self.clock, self._elapsed_ms = clock, elapsed_ms
        self._sources = {symbol: _snapshot(source) for symbol, source in sources.items()}
        self._cold_span_ms = dict(cold_span_ms)
        self._record_request = record_request
        self._seen: set[str] = set()
        self.completed_requests = 0
        self.last_request: HistoricalFetchReceipt | None = None

    def __call__(
        self, symbol: str, timeframe: str, lookback_days: float, *, end_ms: int | None = None
    ) -> pd.DataFrame:
        """Retain one request cutoff even when subsequent transport passes a bar-close boundary."""
        cutoff = _request_cutoff(self.clock, timeframe, lookback_days, end_ms)
        if symbol not in self._sources:
            raise ValueError(f"no declared historical candle source for {symbol}")
        source, cold = self._sources[symbol], symbol not in self._seen
        window = int(float(lookback_days) * DAY_MS)
        start = cutoff - min(window, self._cold_span_ms[symbol]) if cold else cutoff - window
        if start < source.start_ms or cutoff > source.end_ms:
            raise ValueError(f"{symbol} candle request exceeds declared source coverage")
        delay = self._elapsed_ms(symbol, cold)
        require_clock(delay, "historical fetch elapsed time")
        times = source.frame["timestamp"]
        left = times.searchsorted(pd.to_datetime(start, unit="ms", utc=True), side="left")
        right = times.searchsorted(
            pd.to_datetime(cutoff - MINUTE_MS, unit="ms", utc=True), side="right"
        )
        result = source.frame.iloc[left:right].copy(deep=True).reset_index(drop=True)
        dispatched = self.clock.now_ms
        self.clock.advance_to(dispatched + delay)
        receipt = HistoricalFetchReceipt(
            symbol, source.identity, cold, cutoff, start, dispatched, self.clock.now_ms, len(result)
        )
        if self._record_request is not None:
            self._record_request(receipt)
        self._seen.add(symbol)
        self.completed_requests += 1
        self.last_request = receipt
        return result


def _snapshot(source: HistoricalCandleSource) -> HistoricalCandleSource:
    if not isinstance(source, HistoricalCandleSource) or not CANDLE_COLUMNS.issubset(source.frame):
        raise ValueError("historical source requires the explicit OHLCV candle columns")
    frame = source.frame.copy(deep=True)
    times = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if times.isna().any() or not times.is_monotonic_increasing or not times.is_unique:
        raise ValueError("historical candle timestamps must be present, ordered and unique")
    if not times.eq(times.dt.floor("min")).all():
        raise ValueError("historical one-minute bars require exact minute start timestamps")
    lower, upper = (
        pd.to_datetime(value, unit="ms", utc=True) for value in (source.start_ms, source.end_ms)
    )
    if not (times.ge(lower) & times.lt(upper)).all():
        raise ValueError("historical candle timestamps exceed their declared source window")
    frame["timestamp"] = times
    return replace(source, frame=frame)


def _request_cutoff(
    clock: ReplayClock, timeframe: str, lookback_days: float, end_ms: int | None
) -> int:
    if timeframe != "1m" or type(lookback_days) not in (int, float):
        raise ValueError("historical native fetch requires 1m and an explicit numeric lookback")
    if not math.isfinite(lookback_days) or lookback_days <= 0:
        raise ValueError("historical native lookback must be finite and positive")
    if end_ms is None:
        raise ValueError("historical request cutoff must be an explicit nonnegative integer")
    require_clock(end_ms, "historical request cutoff")
    if end_ms > clock.now_ms:
        raise ValueError("historical request cutoff cannot follow the current observation clock")
    return end_ms
