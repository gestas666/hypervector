"""Periodic public HIP-3 mark snapshots with no execution surface."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Protocol, cast

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import AssetContextEvent
from hypervector.data.oxa_api import validate_market_symbol

HIP3_REST_MARK_SOURCE = "hyperliquid_info_metaAndAssetCtxs"
_DEFAULT_POLL_SECONDS = 3.0
_DEFAULT_STATUS_SECONDS = 30.0
_DEFAULT_FLUSH_SECONDS = 30.0
_DEFAULT_BATCH_SIZE = 1_000


class Hip3ContextInfoProtocol(Protocol):
    """Unsigned official Info endpoint needed by the recorder."""

    def post(self, path: str, payload: dict[str, object]) -> object:
        """Return one public metadata-and-context response."""


@dataclass(frozen=True)
class Hip3MarkRecorderConfig:
    """Validated report-only polling and storage configuration."""

    symbols: tuple[str, ...]
    data_root: Path
    poll_seconds: float = _DEFAULT_POLL_SECONDS
    status_seconds: float = _DEFAULT_STATUS_SECONDS
    flush_seconds: float = _DEFAULT_FLUSH_SECONDS
    archive_batch_size: int = _DEFAULT_BATCH_SIZE
    max_polls: int | None = None

    def __post_init__(self) -> None:
        """Reject identities or cadence that cannot support the 5s contract."""
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("HIP-3 mark symbols must be unique and non-empty")
        for symbol in self.symbols:
            validate_market_symbol(symbol, "hip3")
        if len({_dex(symbol) for symbol in self.symbols}) != 1:
            raise ValueError("one HIP-3 mark recorder must target exactly one dex")
        _require_positive(self.poll_seconds, "poll_seconds", maximum=5.0)
        _require_positive(self.status_seconds, "status_seconds")
        _require_positive(self.flush_seconds, "flush_seconds")
        if self.archive_batch_size <= 0:
            raise ValueError("archive_batch_size must be positive")
        if self.max_polls is not None and self.max_polls <= 0:
            raise ValueError("max_polls must be positive when configured")

    @property
    def dex(self) -> str:
        """Return the exact common HIP-3 dex namespace."""
        return _dex(self.symbols[0])


class Hip3MarkSnapshotRecorder:
    """Archive public context snapshots for an exact HIP-3 symbol set."""

    def __init__(self, config: Hip3MarkRecorderConfig) -> None:
        """Create one independent append-only archive per symbol."""
        self._config = config
        self._archives = {
            symbol: EventArchive(
                data_root=config.data_root,
                symbol=symbol,
                batch_size=config.archive_batch_size,
            )
            for symbol in config.symbols
        }
        self._counts = {symbol: 0 for symbol in config.symbols}

    def sample(
        self,
        info: Hip3ContextInfoProtocol,
        clock_ns: Callable[[], int],
    ) -> tuple[AssetContextEvent, ...]:
        """Fetch once, timestamp receipt, validate, and archive exact marks."""
        response = info.post(
            "/info", {"type": "metaAndAssetCtxs", "dex": self._config.dex}
        )
        events = parse_hip3_mark_snapshot(
            response,
            symbols=self._config.symbols,
            received_ts_ns=clock_ns(),
        )
        for event in events:
            self._archives[event.symbol].append((event,))
            self._counts[event.symbol] += 1
        return events

    def flush(self) -> None:
        """Persist every currently buffered immutable archive tail."""
        for archive in self._archives.values():
            archive.flush()

    def close(self) -> None:
        """Flush and close every symbol archive exactly once."""
        for archive in self._archives.values():
            archive.flush()

    @property
    def counts(self) -> dict[str, int]:
        """Return copied monotonically increasing row counts."""
        return dict(self._counts)


def parse_hip3_mark_snapshot(
    response: object,
    *,
    symbols: tuple[str, ...],
    received_ts_ns: int,
) -> tuple[AssetContextEvent, ...]:
    """Bind requested symbols to position-aligned public context records."""
    _require_positive_integer(received_ts_ns, "received_ts_ns")
    pair = _sequence(response, "metaAndAssetCtxs response")
    if len(pair) != 2:
        raise ValueError("metaAndAssetCtxs must contain metadata and contexts")
    metadata = _mapping(pair[0], "HIP-3 metadata")
    universe = _sequence(metadata.get("universe"), "HIP-3 universe")
    contexts = _sequence(pair[1], "HIP-3 contexts")
    if len(universe) != len(contexts):
        raise ValueError("HIP-3 universe and contexts must be position-aligned")
    return tuple(
        _event(symbol, universe, contexts, received_ts_ns) for symbol in symbols
    )


def run_hip3_mark_recorder(
    config: Hip3MarkRecorderConfig,
    *,
    info: Hip3ContextInfoProtocol,
    clock_ns: Callable[[], int] = time.time_ns,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    stop_requested: Callable[[], bool] = lambda: False,
    status_sink: Callable[[dict[str, object]], None] = lambda _row: None,
) -> int:
    """Run a bounded or continuous archive-only public mark sampler."""
    recorder = Hip3MarkSnapshotRecorder(config)
    polls = 0
    next_status = monotonic() + config.status_seconds
    next_flush = monotonic() + config.flush_seconds
    status_sink(_status("hip3_mark_recorder_started", config, recorder, polls))
    try:
        while not stop_requested():
            recorder.sample(info, clock_ns)
            polls += 1
            now = monotonic()
            if now >= next_flush:
                recorder.flush()
                next_flush = now + config.flush_seconds
            if now >= next_status:
                status_sink(
                    _status("hip3_mark_recorder_heartbeat", config, recorder, polls)
                )
                next_status = now + config.status_seconds
            if config.max_polls is not None and polls >= config.max_polls:
                break
            sleeper(config.poll_seconds)
    finally:
        recorder.close()
        status_sink(_status("hip3_mark_recorder_stopped", config, recorder, polls))
    return polls


def _event(
    symbol: str,
    universe: Sequence[object],
    contexts: Sequence[object],
    received_ts_ns: int,
) -> AssetContextEvent:
    matches = [
        index
        for index, raw in enumerate(universe)
        if _mapping(raw, "HIP-3 market").get("name") == symbol
    ]
    if len(matches) != 1:
        raise ValueError(f"HIP-3 mark symbol {symbol} must resolve exactly once")
    context = _mapping(contexts[matches[0]], f"{symbol} context")
    return AssetContextEvent(
        symbol=symbol,
        observed_ts_ms=received_ts_ns // 1_000_000,
        received_ts_ns=received_ts_ns,
        mark_price=_decimal(context.get("markPx"), f"{symbol} mark", positive=True),
        oracle_price=_decimal(
            context.get("oraclePx"), f"{symbol} oracle", positive=True
        ),
        funding_rate_hourly=_decimal(context.get("funding"), f"{symbol} funding"),
        open_interest=_decimal(
            context.get("openInterest"), f"{symbol} open interest", nonnegative=True
        ),
        mid_price=_optional_decimal(context.get("midPx"), f"{symbol} midpoint"),
        source=HIP3_REST_MARK_SOURCE,
    )


def _status(
    event_type: str,
    config: Hip3MarkRecorderConfig,
    recorder: Hip3MarkSnapshotRecorder,
    polls: int,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "symbols": list(config.symbols),
        "source": HIP3_REST_MARK_SOURCE,
        "poll_seconds": config.poll_seconds,
        "polls": polls,
        "rows_by_symbol": recorder.counts,
        "recorded_at_ns": time.time_ns(),
        "execution_authority": "none",
        "report_only": True,
        "signing_client_constructed": False,
        "orders_supported": False,
    }


def _decimal(
    value: object,
    label: str,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> float:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string")
    try:
        output = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(output):
        raise ValueError(f"{label} must be finite")
    if positive and output <= 0.0:
        raise ValueError(f"{label} must be positive")
    if nonnegative and output < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return output


def _optional_decimal(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _decimal(value, label, positive=True)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _dex(symbol: str) -> str:
    dex, separator, _asset = symbol.partition(":")
    if not separator:
        raise ValueError("HIP-3 mark symbol must contain a dex namespace")
    return dex


def _require_positive(value: float, label: str, maximum: float | None = None) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    if maximum is not None and value >= maximum:
        raise ValueError(f"{label} must remain below {maximum:g} seconds")


def _require_positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
