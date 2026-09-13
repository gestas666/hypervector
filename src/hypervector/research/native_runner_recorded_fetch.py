"""Authenticated candle packets with explicit relative profiler receipt clocks.

Captured elapsed durations are rounded upward to milliseconds and anchored at
the recorded observation cutoff. This models the retained profiler experiment;
it does not claim measured exchange arrival times or unprofiled live latency.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.research.native_replay_clock import EPOCH, ReplayClock


@dataclass(frozen=True)
class RecordedCandleCall:
    """Exact captured request and its modeled millisecond transport duration."""

    symbol: str
    timeframe: str
    lookback_days: float
    end_ms: int
    elapsed_ms: int


@dataclass(frozen=True)
class RecordedPollPacket:
    """One authenticated profiler packet; frame bytes are independently hashed."""

    cutoff_ms: int
    elapsed_ms: int
    calls: tuple[RecordedCandleCall, ...]
    frames: Mapping[str, pd.DataFrame]


class RecordedRunnerFetch:
    """Supply original candles to the native poller without network access."""

    def __init__(self, clock: ReplayClock) -> None:
        """Use the runner's shared clock and require explicit packet boundaries."""
        self.clock = clock
        self.completed_packets = 0
        self._packet: RecordedPollPacket | None = None
        self._consumed = 0

    def load_packet(self, path: Path, checksum: str) -> None:
        """Authenticate all source bytes before changing acquisition state."""
        if self._packet is not None:
            raise ValueError("recorded packet still has an unfinished poll")
        packet = _load_packet(path, checksum)
        if self.clock.now_ms > packet.cutoff_ms:
            raise ValueError("recorded packet cutoff precedes runner clock")
        self._packet, self._consumed = packet, 0

    def __call__(
        self, symbol: str, timeframe: str, lookback_days: float, *, end_ms: int | None = None
    ) -> pd.DataFrame:
        """Verify the next exact request and advance only its declared receipt duration."""
        packet = self._require_packet()
        if self._consumed == len(packet.calls):
            raise ValueError("extra recorded candle request")
        expected_clock = packet.cutoff_ms + sum(
            call.elapsed_ms for call in packet.calls[: self._consumed]
        )
        if self.clock.now_ms != expected_clock:
            raise ValueError("recorded request clock differs from captured acquisition schedule")
        call = packet.calls[self._consumed]
        if (symbol, timeframe, lookback_days, end_ms) != (
            call.symbol,
            call.timeframe,
            call.lookback_days,
            call.end_ms,
        ):
            raise ValueError("recorded candle request does not match captured sequence")
        result = packet.frames[symbol].copy(deep=True)
        self.clock.advance_to(self.clock.now_ms + call.elapsed_ms)
        self._consumed += 1
        return result

    def finish_poll(self) -> None:
        """Account for the packet's remaining profiled processing time exactly once."""
        packet = self._require_packet()
        if self._consumed != len(packet.calls):
            raise ValueError("unconsumed recorded candle requests")
        self.clock.advance_to(packet.cutoff_ms + packet.elapsed_ms)
        self.completed_packets += 1
        self._packet = None

    def _require_packet(self) -> RecordedPollPacket:
        if self._packet is None:
            raise ValueError("recorded candle acquisition has no active packet")
        return self._packet


def _load_packet(path: Path, checksum: str) -> RecordedPollPacket:
    data = path.read_bytes()
    if sha256(data).hexdigest() != checksum:
        raise ValueError("recorded packet checksum mismatch")
    record = _mapping(json.loads(data))
    cutoff = _cutoff_ms(record["observed_cutoff_utc"])
    calls = tuple(_call(_mapping(row)) for row in _rows(record["fetch_calls"]))
    frames = _frames(path.parent, _text(record["label"]), record["input_frames"])
    elapsed = _elapsed_ms(record["elapsed_seconds_with_profiler"])
    if not calls or {call.symbol for call in calls} != set(frames):
        raise ValueError("recorded calls and frames have different symbol coverage")
    if any(call.end_ms != cutoff for call in calls) or sum(c.elapsed_ms for c in calls) > elapsed:
        raise ValueError("recorded request clocks exceed the captured poll boundary")
    return RecordedPollPacket(cutoff, elapsed, calls, frames)


def _cutoff_ms(value: object) -> int:
    observed = datetime.fromisoformat(_text(value))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("recorded cutoff requires an explicit UTC offset")
    elapsed = observed - EPOCH
    precision = timedelta(milliseconds=1)
    if elapsed % precision:
        raise ValueError("recorded cutoff must use whole milliseconds")
    return elapsed // precision


def _call(row: Mapping[str, object]) -> RecordedCandleCall:
    end_ms = row["end_ms"]
    lookback = row["lookback_days"]
    if type(end_ms) is not int or end_ms < 0:
        raise ValueError("recorded request end_ms must be a nonnegative integer")
    if type(lookback) not in (int, float) or not math.isfinite(lookback) or lookback <= 0:
        raise ValueError("recorded lookback must be finite and positive")
    return RecordedCandleCall(
        _text(row["symbol"]),
        _text(row["timeframe"]),
        float(lookback),
        end_ms,
        _elapsed_ms(row["elapsed_seconds"]),
    )


def _frames(root: Path, label: str, rows: object) -> dict[str, pd.DataFrame]:
    result = {}
    for value in _rows(rows):
        row = _mapping(value)
        symbol = _text(row["symbol"])
        path = (root / "profile_inputs" / label / f"{symbol}.parquet").resolve()
        if not path.is_relative_to(root.resolve()) or symbol in result:
            raise ValueError("recorded frame path or symbol is ambiguous")
        if sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("recorded frame checksum mismatch")
        frame = pd.read_parquet(path)
        if type(row["rows"]) is not int or len(frame) != row["rows"]:
            raise ValueError("recorded frame row count mismatch")
        result[symbol] = frame
    return result


def _elapsed_ms(value: object) -> int:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("recorded elapsed time must be finite and nonnegative")
    return math.ceil(value * 1000)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError("recorded metadata must be an object with text keys")
    return value


def _rows(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("recorded metadata rows must be a list")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("recorded metadata requires nonempty text")
    return value
