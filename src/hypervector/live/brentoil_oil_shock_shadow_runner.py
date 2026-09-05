"""Durable public-only runner for the BRENTOIL oil-shock shadow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Protocol, cast

import pandas as pd

from hypervector.data.hl import fetch_hl_l2_book, fetch_hl_ohlcv_snapshot
from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
    BRENTOIL_OIL_SHOCK_SYMBOL,
    BRENTOIL_SIGNAL_SOURCE,
    BrentoilOilShockShadowCollector,
    BrentoilOilShockShadowCursor,
    BrentoilOilShockShadowDecision,
    completed_brentoil_oil_inputs,
)
from hypervector.live.brentoil_oil_shock_shadow_storage import (
    append_candles_once,
    append_jsonl,
    candle_summary,
    jsonl_rows,
    source_revision_status,
)
from hypervector.live.hip3_shadow_book import (
    Hip3ShadowBookSpec,
    hip3_shadow_book_row,
)
from hypervector.paper.book import BookSnapshot
from hypervector.research.checkpoint_storage import write_atomic_json

BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID = "brentoil_oil_shock_rest_books_v1"
_INTERVAL_MS = 300_000
_LOOKBACK_DAYS = 8.0
_LIVE_CANARY_OBSERVATIONS = 6
_LIVE_CANARY_MAX_ABS_SLIPPAGE_BPS = 8.464583786205068
_BOOK_SPEC = Hip3ShadowBookSpec(
    BRENTOIL_OIL_SHOCK_SYMBOL,
    "hyperliquid_mainnet_l2_rest",
    BRENTOIL_OIL_SHOCK_LEDGER_PROFILE_ID,
    "BRENTOIL",
)
_PROMOTION_BLOCKERS = (
    "archive_public_trade_ohlc_vs_live_candleSnapshot_parity_unverified",
    "mechanism_specific_live_fill_slippage_not_observed",
    "historical_mark_path_incomplete",
    "validation_and_holdout_unopened",
)


class BrentoilOilShockPublicSourceProtocol(Protocol):
    """Unsigned public reads required by the oil shadow."""

    def book_snapshot(self) -> BookSnapshot:
        """Return one exact public BRENTOIL book."""

    def completed_candle_history(self, *, observed_at_ms: int) -> pd.DataFrame:
        """Return recent public five-minute candles."""


class BrentoilOilShockPublicRestSource:
    """Bind official unsigned REST reads to exact BRENTOIL."""

    def book_snapshot(self) -> BookSnapshot:
        """Fetch one public book without constructing a signer."""
        return fetch_hl_l2_book(BRENTOIL_OIL_SHOCK_SYMBOL)

    def completed_candle_history(self, *, observed_at_ms: int) -> pd.DataFrame:
        """Fetch enough public candles for the frozen rolling threshold."""
        return fetch_hl_ohlcv_snapshot(
            BRENTOIL_OIL_SHOCK_SYMBOL,
            "5m",
            _LOOKBACK_DAYS,
            end_ms=observed_at_ms,
        )


@dataclass(frozen=True)
class BrentoilOilShockShadowPaths:
    """Pairwise-distinct isolated research storage paths."""

    book_ledger: Path
    candle_ledger: Path
    cursor: Path
    journal: Path
    status: Path
    websocket_archive: Path
    rest_mark_archive: Path

    def __post_init__(self) -> None:
        """Reject aliased output or supporting-evidence paths."""
        values = (
            self.book_ledger,
            self.candle_ledger,
            self.cursor,
            self.journal,
            self.status,
            self.websocket_archive,
            self.rest_mark_archive,
        )
        if len(set(values)) != len(values):
            raise ValueError("BRENTOIL shadow paths must be pairwise distinct")


@dataclass(frozen=True)
class BrentoilOilShockShadowPollResult:
    """One durable polling result with no executable surface."""

    decisions: tuple[BrentoilOilShockShadowDecision, ...]
    bootstrap: bool
    observed_at_ms: int
    cursor_decision_time_ms: int
    retroactive_decisions_censored: int
    intents: tuple[()] = ()
    execution_authority: str = "none"
    source_revision_rows_current_snapshot: int = 0
    source_revision_fields_current_snapshot: tuple[str, ...] = ()
    source_revision_bar_open_ms_current_snapshot: tuple[int, ...] = ()


class BrentoilOilShockShadowRunner:
    """Capture public books and prospective oil-shock decisions only."""

    def __init__(
        self,
        *,
        source: BrentoilOilShockPublicSourceProtocol,
        paths: BrentoilOilShockShadowPaths,
    ) -> None:
        """Bind one unsigned source to isolated durable research paths."""
        self._source = source
        self._paths = paths
        self._collector = BrentoilOilShockShadowCollector()

    def poll(self, *, observed_at_ms: int) -> BrentoilOilShockShadowPollResult:
        """Capture a book and advance at most one completed-bar decision."""
        requested = _nonnegative_integer(observed_at_ms, "observed_at_ms")
        book_row, receipt_ms = hip3_shadow_book_row(
            self._source.book_snapshot(), _BOOK_SPEC
        )
        observed = max(requested, receipt_ms)
        append_jsonl(self._paths.book_ledger, book_row)
        cursor = _load_cursor(self._paths.cursor)
        if cursor is None:
            result = self._bootstrap(observed)
        elif observed < cursor.decision_time_ms + _INTERVAL_MS:
            result = BrentoilOilShockShadowPollResult(
                (), False, observed, cursor.decision_time_ms, 0
            )
        else:
            result = self._advance(cursor, observed)
        _write_status(self._paths.status, result, self._paths)
        return result

    def _bootstrap(self, observed_at_ms: int) -> BrentoilOilShockShadowPollResult:
        bars = self._source.completed_candle_history(observed_at_ms=observed_at_ms)
        frame, _positions = completed_brentoil_oil_inputs(
            bars, observed_at=_timestamp(observed_at_ms), after_decision_time_ms=0
        )
        boundary = int((frame.index[-1] + pd.Timedelta(minutes=5)).timestamp() * 1_000)
        append_candles_once(
            self._paths.candle_ledger,
            frame,
            observed_at_ms=observed_at_ms,
            prior_boundary_ms=boundary,
        )
        cursor = BrentoilOilShockShadowCursor(
            BRENTOIL_OIL_SHOCK_PROVIDER_ID,
            BRENTOIL_OIL_SHOCK_PROFILE_ID,
            BRENTOIL_OIL_SHOCK_SYMBOL,
            boundary,
            observed_at_ms,
        )
        _write_cursor(self._paths.cursor, cursor)
        return BrentoilOilShockShadowPollResult((), True, observed_at_ms, boundary, 0)

    def _advance(
        self, cursor: BrentoilOilShockShadowCursor, observed_at_ms: int
    ) -> BrentoilOilShockShadowPollResult:
        bars = self._source.completed_candle_history(observed_at_ms=observed_at_ms)
        frame, _positions = completed_brentoil_oil_inputs(
            bars,
            observed_at=_timestamp(observed_at_ms),
            after_decision_time_ms=cursor.decision_time_ms,
        )
        reconciliation = append_candles_once(
            self._paths.candle_ledger,
            frame,
            observed_at_ms=observed_at_ms,
            prior_boundary_ms=cursor.decision_time_ms,
        )
        batch = self._collector(
            _raw_candle_frame(reconciliation.frame),
            symbol=BRENTOIL_OIL_SHOCK_SYMBOL,
            observed_at=_timestamp(observed_at_ms),
            cursor=cursor,
        )
        for decision in batch.decisions:
            _append_decision_once(self._paths.journal, decision)
        _write_cursor(self._paths.cursor, batch.next_cursor)
        return BrentoilOilShockShadowPollResult(
            batch.decisions,
            False,
            observed_at_ms,
            batch.next_cursor.decision_time_ms,
            batch.retroactive_decisions_censored,
            source_revision_rows_current_snapshot=reconciliation.revision_rows,
            source_revision_fields_current_snapshot=reconciliation.revision_fields,
            source_revision_bar_open_ms_current_snapshot=(
                reconciliation.revision_bar_open_ms
            ),
        )


def _raw_candle_frame(frame: pd.DataFrame) -> pd.DataFrame:
    raw = frame.loc[:, ["open", "high", "low", "close", "volume"]].reset_index()
    return raw.rename(columns={raw.columns[0]: "timestamp"})


def _write_cursor(path: Path, cursor: BrentoilOilShockShadowCursor) -> None:
    payload = asdict(cursor)
    payload.update(
        {
            "schema_version": 1,
            "mode": "brentoil_oil_shock_shadow_cursor",
            "report_only": True,
        }
    )
    write_atomic_json(path, payload)


def _load_cursor(path: Path) -> BrentoilOilShockShadowCursor | None:
    if not path.exists():
        return None
    payload = _object(json.loads(path.read_text(encoding="utf-8")), "cursor")
    if (
        payload.get("schema_version") != 1
        or payload.get("mode") != "brentoil_oil_shock_shadow_cursor"
        or payload.get("report_only") is not True
    ):
        raise ValueError("BRENTOIL shadow cursor storage contract is invalid")
    cursor = BrentoilOilShockShadowCursor(
        _text(payload.get("provider_id"), "provider_id"),
        _text(payload.get("profile_id"), "profile_id"),
        _text(payload.get("symbol"), "symbol"),
        _nonnegative_integer(payload.get("decision_time_ms"), "decision_time_ms"),
        _nonnegative_integer(payload.get("observed_at_ms"), "observed_at_ms"),
        _text(payload.get("execution_authority"), "execution_authority"),
    )
    if (
        cursor.provider_id != BRENTOIL_OIL_SHOCK_PROVIDER_ID
        or cursor.profile_id != BRENTOIL_OIL_SHOCK_PROFILE_ID
        or cursor.symbol != BRENTOIL_OIL_SHOCK_SYMBOL
        or cursor.execution_authority != "none"
    ):
        raise ValueError("BRENTOIL shadow cursor identity is invalid")
    return cursor


def _append_decision_once(path: Path, decision: BrentoilOilShockShadowDecision) -> None:
    event_id = f"{decision.provider_id}|{decision.symbol}|{decision.decision_time_ms}"
    if event_id in _journal_event_ids(path):
        return
    append_jsonl(
        path,
        {
            "schema_version": 1,
            "event_type": "brentoil_oil_shock_shadow_decision",
            "event_id": event_id,
            "report_only": True,
            "execution_authority": "none",
            "intents": [],
            "runtime_strategy_changed": False,
            "decision": asdict(decision),
        },
    )


def _journal_event_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    values: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            row = _object(json.loads(line), f"journal line {line_number}")
            event_id = _text(row.get("event_id"), "event_id")
            if event_id in values:
                raise ValueError("BRENTOIL shadow journal contains a duplicate event")
            values.add(event_id)
    return values


def _write_status(
    path: Path,
    result: BrentoilOilShockShadowPollResult,
    paths: BrentoilOilShockShadowPaths,
) -> None:
    journal = _journal_summary(paths.journal)
    candles = candle_summary(paths.candle_ledger)
    revisions = source_revision_status(
        path,
        current_bars=result.source_revision_bar_open_ms_current_snapshot,
        current_fields=result.source_revision_fields_current_snapshot,
    )
    write_atomic_json(
        path,
        {
            "schema_version": 1,
            "mode": "brentoil_oil_shock_shadow_observer",
            "symbol": BRENTOIL_OIL_SHOCK_SYMBOL,
            "provider_id": BRENTOIL_OIL_SHOCK_PROVIDER_ID,
            "profile_id": BRENTOIL_OIL_SHOCK_PROFILE_ID,
            "execution_authority": "none",
            "report_only": True,
            "signing_client_constructed": False,
            "orders_supported": False,
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
            "signal_ohlc_source": BRENTOIL_SIGNAL_SOURCE,
            "websocket_archive": str(paths.websocket_archive),
            "rest_mark_archive": str(paths.rest_mark_archive),
            "live_canary_execution_observations": _LIVE_CANARY_OBSERVATIONS,
            "live_canary_max_abs_slippage_bps": _LIVE_CANARY_MAX_ABS_SLIPPAGE_BPS,
            "promotion_blockers": list(_PROMOTION_BLOCKERS),
            "observed_at_ms": result.observed_at_ms,
            "cursor_decision_time_ms": result.cursor_decision_time_ms,
            "bootstrap": result.bootstrap,
            "decisions_published": len(result.decisions),
            "decisions_this_poll": len(result.decisions),
            "retroactive_decisions_censored": result.retroactive_decisions_censored,
            **revisions,
            **journal,
            **candles,
        },
    )


def _journal_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "decision_rows_total": 0,
            "eligible_decisions_total": 0,
            "long_decisions_total": 0,
            "short_decisions_total": 0,
            "non_action_decisions_total": 0,
            "last_decision_time_ms": None,
            "last_non_action_reason": None,
            "latest_trailing_return_bps": None,
            "latest_shock_threshold_bps": None,
            "latest_threshold_fraction": None,
            "maximum_threshold_fraction_total": None,
        }
    rows = tuple(_journal_rows(path))
    decisions = tuple(_object(row.get("decision"), "decision") for row in rows)
    latest = decisions[-1]
    return {
        "decision_rows_total": len(rows),
        **_decision_metrics(decisions),
        "last_decision_time_ms": _nonnegative_integer(
            latest.get("decision_time_ms"), "latest decision time"
        ),
        "last_non_action_reason": latest.get("non_action_reason"),
    }


def _decision_metrics(decisions: tuple[dict[str, object], ...]) -> dict[str, object]:
    eligible = tuple(row for row in decisions if row.get("eligible") is True)
    sides = tuple(row.get("side") for row in eligible)
    if any(side not in {"long", "short"} for side in sides):
        raise ValueError("BRENTOIL eligible decision side is invalid")
    fractions = tuple(
        value
        for value in (_threshold_fraction(row) for row in decisions)
        if value is not None
    )
    latest = decisions[-1]
    return {
        "eligible_decisions_total": len(eligible),
        "long_decisions_total": sides.count("long"),
        "short_decisions_total": sides.count("short"),
        "non_action_decisions_total": len(decisions) - len(eligible),
        "latest_trailing_return_bps": _optional_number(
            latest.get("trailing_return_bps"), "latest trailing return"
        ),
        "latest_shock_threshold_bps": _optional_number(
            latest.get("shock_threshold_bps"), "latest shock threshold"
        ),
        "latest_threshold_fraction": _threshold_fraction(latest),
        "maximum_threshold_fraction_total": max(fractions, default=None),
    }


def _threshold_fraction(decision: dict[str, object]) -> float | None:
    trailing = _optional_number(decision.get("trailing_return_bps"), "trailing return")
    threshold = _optional_number(decision.get("shock_threshold_bps"), "shock threshold")
    if trailing is None or threshold is None:
        return None
    if threshold <= 0.0:
        raise ValueError("BRENTOIL shadow shock threshold must be positive")
    return abs(trailing) / threshold


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BRENTOIL shadow {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"BRENTOIL shadow {label} must be finite")
    return number


def _journal_rows(path: Path) -> tuple[dict[str, object], ...]:
    rows = list(jsonl_rows(path, "journal"))
    for row in rows:
        if row.get("event_type") != "brentoil_oil_shock_shadow_decision":
            raise ValueError("BRENTOIL shadow journal event type is invalid")
        if row.get("execution_authority") != "none" or row.get("intents") != []:
            raise ValueError("BRENTOIL shadow journal authority is invalid")
    if not rows:
        raise ValueError("BRENTOIL shadow journal cannot be empty")
    return tuple(rows)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"BRENTOIL shadow {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"BRENTOIL shadow {label} must be non-empty text")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"BRENTOIL shadow {label} must be a nonnegative integer")
    return value


def _timestamp(value: int) -> pd.Timestamp:
    return pd.Timestamp(value, unit="ms", tz="UTC")
