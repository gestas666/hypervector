"""Report-only coverage audit for prospectively recorded HIP-3 venue paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import math

from hypervector.data.hl_events import (
    AssetContextEvent,
    L2SnapshotEvent,
    PublicTradeEvent,
    StreamGap,
)
from hypervector.data.oxa_api import validate_market_symbol

_DEFAULT_TIMEFRAME_MINUTES = 15
_DEFAULT_MARK_GAP_MS = 5_000
_DEFAULT_L2_GAP_MS = 15_000
EvidenceEvent = L2SnapshotEvent | PublicTradeEvent | AssetContextEvent | StreamGap


@dataclass(frozen=True)
class Hip3ProspectivePathAuditConfig:
    """Frozen causal coverage boundaries for one exact HIP-3 symbol."""

    symbol: str
    timeframe_minutes: int = _DEFAULT_TIMEFRAME_MINUTES
    maximum_mark_gap_ms: int = _DEFAULT_MARK_GAP_MS
    maximum_l2_gap_ms: int = _DEFAULT_L2_GAP_MS

    def __post_init__(self) -> None:
        validate_market_symbol(self.symbol, "hip3")
        for name, value in (
            ("timeframe_minutes", self.timeframe_minutes),
            ("maximum_mark_gap_ms", self.maximum_mark_gap_ms),
            ("maximum_l2_gap_ms", self.maximum_l2_gap_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def timeframe_ms(self) -> int:
        """Return the audited bar interval in milliseconds."""
        return self.timeframe_minutes * 60_000


def build_hip3_prospective_path_audit(
    *,
    l2_snapshots: Sequence[L2SnapshotEvent],
    public_trades: Sequence[PublicTradeEvent],
    asset_contexts: Sequence[AssetContextEvent],
    stream_gaps: Sequence[StreamGap],
    observed_at_ms: int,
    config: Hip3ProspectivePathAuditConfig,
) -> dict[str, object]:
    """Audit completed bars without creating signals, orders, or authority."""
    _validate_observed_at(observed_at_ms)
    _require_symbol(
        config.symbol, l2_snapshots, public_trades, asset_contexts, stream_gaps
    )
    _require_sources(l2_snapshots, public_trades, asset_contexts)
    _require_receipt_cutoff(
        observed_at_ms, l2_snapshots, public_trades, asset_contexts, stream_gaps
    )
    marks = _unique_timestamps(
        tuple(event.observed_ts_ms for event in asset_contexts), "mark"
    )
    books = _unique_timestamps(
        tuple(event.exchange_ts_ms for event in l2_snapshots), "L2"
    )
    _require_causal_tail(observed_at_ms, marks, books)
    start, end = _completed_bounds(marks, books, observed_at_ms, config.timeframe_ms)
    bars = _bar_rows(start, end, marks, books, stream_gaps, config)
    mark = _channel_summary(bars, "mark", len(asset_contexts), len(marks))
    l2 = _channel_summary(bars, "l2", len(l2_snapshots), len(books))
    trades = _trade_summary(public_trades, start, end, config.timeframe_ms)
    unresolved = sum(not bool(row["resolved"]) for row in bars)
    identity = _evidence_identity(
        l2_snapshots,
        public_trades,
        asset_contexts,
        stream_gaps,
        start,
        end,
    )
    return _report(
        config, observed_at_ms, start, end, bars, mark, l2, trades, unresolved, identity
    )


def _report(
    config: Hip3ProspectivePathAuditConfig,
    observed_at_ms: int,
    start: int,
    end: int,
    bars: list[dict[str, object]],
    mark: dict[str, object],
    l2: dict[str, object],
    trades: dict[str, object],
    unresolved: int,
    identity: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "hip3_prospective_path_audit_v1",
        "mode": "prospective_public_venue_path_coverage",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "promotion_authority": "none",
            "runtime_strategy_changed": False,
        },
        "source": {"symbol": config.symbol, "observed_at_ms": observed_at_ms},
        "coverage": {
            "first_full_bar_open_ms": start,
            "completed_bar_end_ms": end,
            "completed_bars": len(bars),
            "timeframe_minutes": config.timeframe_minutes,
        },
        "evidence_identity": identity,
        "channels": {"mark": mark, "l2": l2, "trades": trades},
        "bar_diagnostics": bars,
        "technical_assessment": {
            "prospective_bar_path_coverage_resolved": bool(bars) and unresolved == 0,
            "unresolved_bars": unresolved,
            "candle_ohlc_parity_resolved": False,
        },
        "limitations": [
            "coverage does not establish strategy profitability or promotion authority",
            "public-trade OHLC versus live candleSnapshot parity remains unverified",
            "completed-bar coverage does not resolve historical archive gaps",
        ],
    }


def _evidence_identity(
    books: Sequence[L2SnapshotEvent],
    trades: Sequence[PublicTradeEvent],
    contexts: Sequence[AssetContextEvent],
    gaps: Sequence[StreamGap],
    completed_start_ms: int,
    completed_end_ms: int,
) -> dict[str, object]:
    completed_books = tuple(
        book
        for book in books
        if completed_start_ms <= book.exchange_ts_ms < completed_end_ms
    )
    completed_trades = tuple(
        trade
        for trade in trades
        if completed_start_ms <= trade.exchange_ts_ms < completed_end_ms
    )
    channels = {
        "l2": _channel_identity(books),
        "completed_bar_l2": _channel_identity(completed_books),
        "trades": _channel_identity(trades),
        "completed_bar_trades": _channel_identity(completed_trades),
        "mark": _channel_identity(contexts),
        "gaps": _channel_identity(gaps),
    }
    material = json.dumps(channels, sort_keys=True, separators=(",", ":"))
    return channels | {
        "material_state_sha256": hashlib.sha256(material.encode("utf-8")).hexdigest()
    }


def _channel_identity(events: Sequence[EvidenceEvent]) -> dict[str, object]:
    rows = sorted(
        (
            json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))
            for event in events
        )
    )
    payload = "\n".join(rows).encode("utf-8")
    return {"rows": len(rows), "sha256": hashlib.sha256(payload).hexdigest()}


def _completed_bounds(
    marks: tuple[int, ...],
    books: tuple[int, ...],
    observed_at_ms: int,
    interval_ms: int,
) -> tuple[int, int]:
    if not marks or not books:
        return 0, 0
    first = max(marks[0], books[0])
    start = math.ceil(first / interval_ms) * interval_ms
    end = observed_at_ms // interval_ms * interval_ms
    return (start, max(start, end))


def _bar_rows(
    start: int,
    end: int,
    marks: tuple[int, ...],
    books: tuple[int, ...],
    gaps: Sequence[StreamGap],
    config: Hip3ProspectivePathAuditConfig,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for bar_open in range(start, end, config.timeframe_ms):
        bar_close = bar_open + config.timeframe_ms
        mark = _bar_quality(marks, bar_open, bar_close, config.maximum_mark_gap_ms)
        l2 = _bar_quality(books, bar_open, bar_close, config.maximum_l2_gap_ms)
        mark_gap = _gap_quality(
            gaps,
            bar_open,
            bar_close,
            "activeAssetCtx",
            config.maximum_mark_gap_ms,
            use_exchange_bounds=False,
        )
        l2_gap = _gap_quality(
            gaps,
            bar_open,
            bar_close,
            "l2Book",
            config.maximum_l2_gap_ms,
            use_exchange_bounds=True,
        )
        _apply_gap_quality(mark, mark_gap)
        _apply_gap_quality(l2, l2_gap)
        rows.append(
            {
                "bar_open_ms": bar_open,
                "bar_close_ms": bar_close,
                "mark": mark,
                "l2": l2,
                "resolved": bool(mark["complete"]) and bool(l2["complete"]),
            }
        )
    return rows


def _bar_quality(
    timestamps: tuple[int, ...],
    start: int,
    end: int,
    maximum_gap_ms: int,
) -> dict[str, object]:
    values = tuple(value for value in timestamps if start <= value < end)
    if not values:
        return {"observations": 0, "maximum_gap_ms": None, "complete": False}
    gaps = tuple(right - left for left, right in zip(values, values[1:], strict=False))
    maximum = max((values[0] - start, end - values[-1], *gaps))
    return {
        "observations": len(values),
        "first_boundary_delay_ms": values[0] - start,
        "end_boundary_age_ms": end - values[-1],
        "maximum_gap_ms": maximum,
        "complete": len(values) >= 2 and maximum <= maximum_gap_ms,
    }


def hip3_bar_path_quality(
    timestamps_ms: Sequence[int],
    *,
    start_ms: int,
    end_ms: int,
    maximum_gap_ms: int,
) -> dict[str, object]:
    """Return the frozen boundary-aware quality calculation for one bar."""
    values = tuple(sorted(timestamps_ms))
    return _bar_quality(values, start_ms, end_ms, maximum_gap_ms)


def _channel_summary(
    bars: Sequence[dict[str, object]],
    channel: str,
    observations: int,
    unique_observations: int,
) -> dict[str, object]:
    rows = tuple(_mapping(row[channel], channel) for row in bars)
    gaps = [
        int(row["maximum_gap_ms"]) for row in rows if row["maximum_gap_ms"] is not None
    ]
    complete = sum(row["complete"] is True for row in rows)
    return {
        "observations": observations,
        "unique_observations": unique_observations,
        "duplicate_observations": observations - unique_observations,
        "complete_bars": complete,
        "incomplete_bars": len(rows) - complete,
        "maximum_observed_gap_ms": max(gaps, default=None),
        "declared_gap_bars": sum(row.get("declared_gap") is True for row in rows),
        "unbounded_gap_bars": sum(row.get("unbounded_gap") is True for row in rows),
        "gap_boundary_semantics": (
            "local_receipt_observation_cadence"
            if channel == "mark"
            else "declared_exchange_timestamp_bounds"
        ),
    }


def _trade_summary(
    trades: Sequence[PublicTradeEvent], start: int, end: int, interval_ms: int
) -> dict[str, object]:
    unique = _unique_trades(trades)
    bars = set(range(start, end, interval_ms))
    occupied = {
        event.exchange_ts_ms // interval_ms * interval_ms
        for event in unique
        if start <= event.exchange_ts_ms < end
    }
    return {
        "observations": len(trades),
        "unique_observations": len(unique),
        "duplicate_observations": len(trades) - len(unique),
        "bars_with_trades": len(bars & occupied),
        "bars_without_trades": len(bars - occupied),
    }


def _unique_trades(
    trades: Sequence[PublicTradeEvent],
) -> tuple[PublicTradeEvent, ...]:
    output: dict[str, PublicTradeEvent] = {}
    for event in trades:
        prior = output.get(event.trade_key)
        if prior is not None and prior != event:
            raise ValueError(f"conflicting public trade identity: {event.trade_key}")
        output[event.trade_key] = event
    return tuple(output.values())


def _gap_quality(
    gaps: Sequence[StreamGap],
    start: int,
    end: int,
    channel: str,
    maximum_gap_ms: int,
    *,
    use_exchange_bounds: bool,
) -> tuple[bool, bool]:
    declared = False
    unbounded = False
    for gap in gaps:
        if channel not in gap.channel:
            continue
        detected = gap.detected_ts_ns // 1_000_000
        prior = gap.previous_exchange_ts_ms or detected
        following = gap.next_exchange_ts_ms or detected
        if max(start, prior) < min(end, following + 1):
            declared = True
            interval = following - prior
            if use_exchange_bounds and (
                gap.previous_exchange_ts_ms is None
                or gap.next_exchange_ts_ms is None
                or interval < 0
                or interval > maximum_gap_ms
            ):
                unbounded = True
    return declared, unbounded


def _apply_gap_quality(evidence: dict[str, object], quality: tuple[bool, bool]) -> None:
    declared, unbounded = quality
    evidence["declared_gap"] = declared
    evidence["unbounded_gap"] = unbounded
    evidence["complete"] = bool(evidence["complete"]) and not unbounded


def _require_symbol(
    symbol: str,
    *groups: Sequence[
        L2SnapshotEvent | PublicTradeEvent | AssetContextEvent | StreamGap
    ],
) -> None:
    mismatches = sorted(
        {event.symbol for group in groups for event in group if event.symbol != symbol}
    )
    if mismatches:
        raise ValueError(f"prospective HIP-3 evidence symbol mismatch: {mismatches}")


def _require_sources(
    books: Sequence[L2SnapshotEvent],
    trades: Sequence[PublicTradeEvent],
    contexts: Sequence[AssetContextEvent],
) -> None:
    expected = (
        (books, "hyperliquid_ws_l2Book"),
        (trades, "hyperliquid_ws_trades"),
        (contexts, "hyperliquid_ws_activeAssetCtx"),
    )
    invalid = sorted(
        {
            event.source
            for group, source in expected
            for event in group
            if event.source != source
        }
    )
    if invalid:
        raise ValueError(f"prospective HIP-3 source contract mismatch: {invalid}")


def _require_receipt_cutoff(
    observed_at_ms: int,
    books: Sequence[L2SnapshotEvent],
    trades: Sequence[PublicTradeEvent],
    contexts: Sequence[AssetContextEvent],
    gaps: Sequence[StreamGap],
) -> None:
    receipts = [
        *(event.received_ts_ns for event in books),
        *(event.received_ts_ns for event in trades),
        *(event.received_ts_ns for event in contexts),
        *(event.detected_ts_ns for event in gaps),
    ]
    if any(value // 1_000_000 > observed_at_ms for value in receipts):
        raise ValueError("prospective HIP-3 receipt exceeds observed_at_ms")


def _unique_timestamps(values: tuple[int, ...], label: str) -> tuple[int, ...]:
    if any(isinstance(value, bool) or value <= 0 for value in values):
        raise ValueError(f"{label} timestamps must be positive integers")
    return tuple(sorted(set(values)))


def _require_causal_tail(
    observed_at_ms: int, marks: tuple[int, ...], books: tuple[int, ...]
) -> None:
    if (marks and marks[-1] > observed_at_ms) or (books and books[-1] > observed_at_ms):
        raise ValueError("prospective HIP-3 evidence exceeds observed_at_ms")


def _validate_observed_at(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("observed_at_ms must be a positive integer")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} bar evidence must be an object")
    return value
