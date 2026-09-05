"""Durable report-only runner for prospective ``xyz:MU`` shadow evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import time
from typing import Protocol, cast

import pandas as pd

from hypervector.data.hl import fetch_hl_l2_book, fetch_hl_ohlcv_snapshot
from hypervector.live.hip3_provider_inputs import completed_hip3_inputs
from hypervector.live.hip3_shadow_candle_storage import (
    ShadowCandleContract,
    append_candles_once,
    candle_summary,
    source_revision_status,
)
from hypervector.live.hip3_shadow_candle_contracts import (
    hip3_shadow_candle_contract,
)
from hypervector.live.mu_hip3_breakout_shadow import (
    Hip3BreakoutShadowSpec,
    MU_SHADOW_SPEC,
    MuHip3BreakoutShadowCollector,
    MuHip3BreakoutShadowCursor,
    MuHip3BreakoutShadowDecision,
)
from hypervector.live.mu_hip3_preclose_pressure import (
    MU_PRESSURE_SOURCE,
    MuAssetLedgerBinding,
    MuHip3LedgerPreclosePressureSource,
    MuPreclosePressureEvidence,
)
from hypervector.live.mu_hip3_shadow_journal import (
    mu_shadow_journal_event_ids,
    mu_shadow_journal_summary,
)
from hypervector.live.mu_hip3_shadow_book import mu_shadow_book_row
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError
from hypervector.live.hip3_profit_lock_candle_capture import (
    Hip3ProfitLockCandleCapture,
    profit_lock_candle_path,
)
from hypervector.live.transient_transport import transient_read_failure_reason
from hypervector.paper.book import BookSnapshot
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

MU_LEDGER_PROFILE_ID = MU_SHADOW_SPEC.ledger_profile_id
_INTERVAL_MS = 900_000
_CANDLE_LOOKBACK_DAYS = 2.0
_PROMOTION_BLOCKERS = (
    "archive_public_trade_ohlc_vs_live_candleSnapshot_parity_unverified",
    "archive_ws_l2Book_vs_live_rest_pressure_decision_parity_unresolved",
)


class MuHip3PublicSourceProtocol(Protocol):
    """Public, unsigned venue reads required by the MU shadow runner."""

    def book_snapshot(self) -> BookSnapshot:
        """Return one exact public ``xyz:MU`` L2 snapshot."""

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        """Return recent public 15-minute candles through the observation time."""


class MuHip3PublicRestSource:
    """Use only Hyperliquid's unsigned public Info REST surface for MU."""

    def __init__(self, spec: Hip3BreakoutShadowSpec = MU_SHADOW_SPEC) -> None:
        """Bind public reads to one exact report-only HIP-3 identity."""
        self._spec = spec

    def book_snapshot(self) -> BookSnapshot:
        """Fetch one exact public MU L2 book without constructing a signer."""
        try:
            return fetch_hl_l2_book(self._spec.symbol)
        except (RuntimeError, OSError) as exc:
            _raise_if_transient(exc, "hyperliquid_public_l2")
            raise

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        """Fetch a bounded public MU 15-minute candle window."""
        try:
            frame = fetch_hl_ohlcv_snapshot(
                self._spec.symbol,
                timeframe,
                _CANDLE_LOOKBACK_DAYS,
                end_ms=observed_at_ms,
            )
            frame.attrs["received_at_ms"] = time.time_ns() // 1_000_000
            return frame
        except (RuntimeError, OSError) as exc:
            _raise_if_transient(exc, "hyperliquid_public_candles")
            raise


@dataclass(frozen=True)
class MuHip3ShadowPaths:
    """Isolated durable files for the no-authority MU observer."""

    asset_ledger: Path
    cohort_ledger: Path
    cursor: Path
    journal: Path
    status: Path

    @property
    def candle_ledger(self) -> Path:
        """Return the deterministic sibling ledger for exact source candles."""
        return self.journal.with_name(f"{self.journal.stem}_candles.jsonl")

    def __post_init__(self) -> None:
        """Reject aliased or overlapping output identities."""
        values = (
            self.asset_ledger,
            self.cohort_ledger,
            self.cursor,
            self.journal,
            self.candle_ledger,
            self.status,
        )
        if len(set(values)) != len(values):
            raise ValueError("MU shadow output paths must be pairwise distinct")


@dataclass(frozen=True)
class MuHip3ShadowPollResult:
    """One durable poll result with no executable surface."""

    decisions: tuple[MuHip3BreakoutShadowDecision, ...]
    bootstrap: bool
    observed_at_ms: int
    cursor_decision_time_ms: int
    retroactive_decisions_censored: int
    source_revision_rows_current_snapshot: int = 0
    source_revision_fields_current_snapshot: tuple[str, ...] = ()
    source_revision_bar_open_ms_current_snapshot: tuple[int, ...] = ()
    intents: tuple[()] = ()
    execution_authority: str = "none"


class MuHip3BreakoutShadowRunner:
    """Capture MU books and persist prospective shadow decisions only."""

    def __init__(
        self,
        *,
        source: MuHip3PublicSourceProtocol,
        paths: MuHip3ShadowPaths,
        spec: Hip3BreakoutShadowSpec = MU_SHADOW_SPEC,
    ) -> None:
        """Bind unsigned venue reads to isolated durable research files."""
        self._source = source
        self._paths = paths
        self._spec = spec
        if spec.symbol.lower() not in paths.asset_ledger.name.lower():
            raise ValueError("HIP-3 shadow asset ledger does not match route spec")
        pressure = MuHip3LedgerPreclosePressureSource(
            asset_binding=MuAssetLedgerBinding(
                spec.symbol,
                paths.asset_ledger,
                spec.ledger_profile_id,
            ),
            cohort_ledger=paths.cohort_ledger,
        )
        self._collector = MuHip3BreakoutShadowCollector(
            pressure_source=pressure,
            spec=spec,
        )
        self._profit_lock_capture = (
            Hip3ProfitLockCandleCapture(
                source, spec.symbol, profit_lock_candle_path(paths.journal)
            )
            if spec.symbol in {"xyz:SP500", "xyz:SPCX"}
            else None
        )

    @property
    def config(self) -> Hip3BreakoutPressureConfig:
        """Return the frozen route signal configuration."""
        return self._collector.config

    def poll(self, *, observed_at_ms: int) -> MuHip3ShadowPollResult:
        """Capture one book and durably advance at most one prospective bar."""
        requested = _nonnegative_integer(observed_at_ms, "observed_at_ms")
        snapshot = self._source.book_snapshot()
        book_row, receipt_ms = mu_shadow_book_row(snapshot, self._spec)
        observed = max(requested, receipt_ms)
        _append_jsonl(self._paths.asset_ledger, book_row)
        if self._profit_lock_capture is not None:
            self._profit_lock_capture.poll(observed)
        cursor = _load_cursor(self._paths.cursor)
        if cursor is None:
            result = self._bootstrap(observed)
        elif observed < cursor.decision_time_ms + _INTERVAL_MS:
            result = MuHip3ShadowPollResult(
                (), False, observed, cursor.decision_time_ms, 0
            )
        else:
            result = self._advance(cursor, observed)
        _write_status(self._paths, result, self._spec)
        return result

    def _bootstrap(self, observed_at_ms: int) -> MuHip3ShadowPollResult:
        """Anchor at the latest completed bar without reading a past signal."""
        bars = self._source.completed_candle_history(observed_at_ms=observed_at_ms)
        frame, _positions, boundary = completed_hip3_inputs(
            bars,
            _timestamp(observed_at_ms),
            None,
        )
        latest = frame.index[-1]
        append_candles_once(
            self._paths.candle_ledger,
            frame,
            contract=_candle_contract(self._spec),
            observed_at_ms=observed_at_ms,
            prior_boundary_ms=boundary,
        )
        cursor = MuHip3BreakoutShadowCursor(
            self._spec.provider_id,
            self._spec.profile_id,
            self._spec.symbol,
            boundary,
            _timestamp_ms(latest),
            observed_at_ms,
            None,
            None,
            None,
        )
        _write_cursor(self._paths.cursor, cursor)
        return MuHip3ShadowPollResult((), True, observed_at_ms, boundary, 0)

    def _advance(
        self,
        cursor: MuHip3BreakoutShadowCursor,
        observed_at_ms: int,
    ) -> MuHip3ShadowPollResult:
        """Evaluate unseen completed bars and atomically persist the next cursor."""
        bars = self._source.completed_candle_history(observed_at_ms=observed_at_ms)
        frame, _positions, _boundary = completed_hip3_inputs(
            bars,
            _timestamp(observed_at_ms),
            cursor.decision_time_ms,
        )
        reconciliation = append_candles_once(
            self._paths.candle_ledger,
            frame,
            contract=_candle_contract(self._spec),
            observed_at_ms=observed_at_ms,
            prior_boundary_ms=cursor.decision_time_ms,
        )
        batch = self._collector(
            _raw_candle_frame(reconciliation.frame),
            symbol=self._spec.symbol,
            observed_at=_timestamp(observed_at_ms),
            cursor=cursor,
        )
        for decision in batch.decisions:
            _append_decision_once(self._paths.journal, decision)
        _write_cursor(self._paths.cursor, batch.next_cursor)
        return MuHip3ShadowPollResult(
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


def _write_cursor(path: Path, cursor: MuHip3BreakoutShadowCursor) -> None:
    payload = asdict(cursor)
    payload.update(
        {
            "schema_version": 1,
            "mode": f"{_route_token(cursor.symbol)}_hip3_breakout_shadow_cursor",
            "report_only": True,
        }
    )
    write_atomic_json(path, payload)


def _load_cursor(path: Path) -> MuHip3BreakoutShadowCursor | None:
    if not path.exists():
        return None
    payload = _object(json.loads(path.read_text(encoding="utf-8")), "cursor")
    symbol = _text(payload.get("symbol"), "symbol")
    expected_mode = f"{_route_token(symbol)}_hip3_breakout_shadow_cursor"
    if payload.get("schema_version") != 1 or payload.get("mode") != expected_mode:
        raise ValueError("HIP-3 shadow cursor storage contract is invalid")
    if payload.get("report_only") is not True:
        raise ValueError("MU shadow cursor storage contract is invalid")
    pressure_raw = payload.get("pressure")
    pressure = None
    if pressure_raw is not None:
        pressure = MuPreclosePressureEvidence(**_object(pressure_raw, "pressure"))
    return MuHip3BreakoutShadowCursor(
        provider_id=_text(payload.get("provider_id"), "provider_id"),
        profile_id=_text(payload.get("profile_id"), "profile_id"),
        symbol=symbol,
        decision_time_ms=_nonnegative_integer(
            payload.get("decision_time_ms"), "decision_time_ms"
        ),
        bar_open_ms=_nonnegative_integer(payload.get("bar_open_ms"), "bar_open_ms"),
        observed_at_ms=_nonnegative_integer(
            payload.get("observed_at_ms"), "observed_at_ms"
        ),
        long_raw=_optional_boolean(payload.get("long_raw"), "long_raw"),
        short_raw=_optional_boolean(payload.get("short_raw"), "short_raw"),
        pressure=pressure,
        execution_authority=_text(
            payload.get("execution_authority"), "execution_authority"
        ),
    )


def _append_decision_once(
    path: Path,
    decision: MuHip3BreakoutShadowDecision,
) -> None:
    event_id = f"{decision.provider_id}|{decision.symbol}|{decision.decision_time_ms}"
    event_type = f"{_route_token(decision.symbol)}_hip3_breakout_shadow_decision"
    if event_id in mu_shadow_journal_event_ids(
        path,
        expected_event_type=event_type,
    ):
        return
    row = {
        "schema_version": 1,
        "event_type": event_type,
        "event_id": event_id,
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": asdict(decision),
    }
    _append_jsonl(path, row)


def _append_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_status(
    paths: MuHip3ShadowPaths,
    result: MuHip3ShadowPollResult,
    spec: Hip3BreakoutShadowSpec = MU_SHADOW_SPEC,
) -> None:
    journal = mu_shadow_journal_summary(
        paths.journal,
        expected_event_type=(
            f"{_route_token(spec.symbol)}_hip3_breakout_shadow_decision"
        ),
    )
    revisions = source_revision_status(
        paths.status,
        current_bars=result.source_revision_bar_open_ms_current_snapshot,
        current_fields=result.source_revision_fields_current_snapshot,
        allowed_fields=_candle_contract(spec).revision_tolerant_fields,
    )
    write_atomic_json(
        paths.status,
        {
            "schema_version": 1,
            "mode": f"{_route_token(spec.symbol)}_hip3_breakout_shadow_observer",
            "symbol": spec.symbol,
            "provider_id": spec.provider_id,
            "profile_id": spec.profile_id,
            "execution_authority": "none",
            "report_only": True,
            "signing_client_constructed": False,
            "orders_supported": False,
            "runtime_strategy_changed": False,
            "automatic_promotion": False,
            "signal_ohlc_source": "hyperliquid_public_candleSnapshot_15m",
            "signal_ohlc_revision_policy": "freeze_first_observed_disclose_revisions",
            "pressure_source": MU_PRESSURE_SOURCE,
            "promotion_blockers": list(_PROMOTION_BLOCKERS),
            "observed_at_ms": result.observed_at_ms,
            "cursor_decision_time_ms": result.cursor_decision_time_ms,
            "bootstrap": result.bootstrap,
            "decisions_published": len(result.decisions),
            "decisions_this_poll": len(result.decisions),
            "retroactive_decisions_censored": result.retroactive_decisions_censored,
            **journal,
            **candle_summary(paths.candle_ledger),
            "profit_lock_candles": candle_summary(
                profit_lock_candle_path(paths.journal)
            ),
            **revisions,
        },
    )


def _candle_contract(spec: Hip3BreakoutShadowSpec) -> ShadowCandleContract:
    return hip3_shadow_candle_contract(spec.symbol, "15m")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"MU shadow {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"MU shadow {label} must be non-empty text")
    return value


def _optional_boolean(value: object, label: str) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"MU shadow {label} must be boolean or null")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"MU shadow {label} must be a nonnegative integer")
    return value


def _exact_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"MU shadow {label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
        raise ValueError(f"MU shadow {label} must be an exact nonnegative integer")
    return int(numeric)


def _ceiling_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"MU shadow {label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ValueError(f"MU shadow {label} must be finite and nonnegative")
    return math.ceil(numeric)


def _raise_if_transient(error: Exception, source: str) -> None:
    """Classify an exhausted transport failure anywhere in its cause chain."""
    current: BaseException | None = error
    visited: set[int] = set()
    while isinstance(current, Exception) and id(current) not in visited:
        visited.add(id(current))
        reason = transient_read_failure_reason(current)
        if reason is not None:
            raise TransientCohortMarketDataError(
                source=source,
                reason=reason,
            ) from error
        current = current.__cause__ or current.__context__


def _timestamp(value: int) -> pd.Timestamp:
    return pd.Timestamp(value, unit="ms", tz="UTC")


def _timestamp_ms(value: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("MU shadow candle timestamp must be timezone-aware")
    return int(timestamp.timestamp() * 1_000)


def _route_token(symbol: str) -> str:
    if not symbol.startswith("xyz:") or len(symbol) <= 4:
        raise ValueError("HIP-3 shadow symbol must use exact xyz namespace")
    return symbol.removeprefix("xyz:").lower()
