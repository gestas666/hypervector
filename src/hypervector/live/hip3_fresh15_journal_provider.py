"""Execute prospective repaired HIP-3 index decisions from durable journals."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import math
from pathlib import Path
from typing import cast

import pandas as pd

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.hip3_breakout_shadow_specs import (
    Hip3BreakoutShadowSpec,
)
from hypervector.live.hip3_fresh15_condition_telemetry import (
    canonical_pressure_status,
    condition_readiness_indicators,
    condition_readiness_metrics,
    parse_condition_telemetry,
)
from hypervector.live.hip3_fresh15_journal_contracts import (
    CONFIRMATION_REASONS,
    INDEX_SYMBOLS,
    DEFAULT_JOURNALS as _DEFAULT_JOURNALS,
    DEFAULT_OBSERVER_STATES as _DEFAULT_OBSERVER_STATES,
    JOURNAL_SPECS as _SPECS,
    Hip3Fresh15Decision as _Decision,
    HIP3_INDEX_FRESH15_V3_STRATEGY as HIP3_INDEX_FRESH15_V3_STRATEGY,
    HIP3_SNDK_FRESH15_V4_STRATEGY as HIP3_SNDK_FRESH15_V4_STRATEGY,
)
from hypervector.live.hip3_provider_inputs import completed_hip3_inputs
from hypervector.live.hip3_provider_availability import Hip3ObserverUnavailableError
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger

_MAXIMUM_DECISION_DELAY_MS = 15_000
_MAXIMUM_OBSERVER_STATUS_AGE_MS = 30_000
_MAXIMUM_OBSERVER_CLOCK_SKEW_MS = 1_000


def _utc_now() -> pd.Timestamp:
    """Return the health-check instant independently of a poll's data cutoff."""
    return pd.Timestamp.now(tz="UTC")


class Hip3Fresh15JournalCollector:
    """Translate exact prospective pressure journal rows into attributed intents."""

    def __init__(
        self,
        *,
        journals: Mapping[str, Path] | None = None,
        observer_states: Mapping[str, tuple[Path, Path]] | None = None,
        health_now_fn: Callable[[], pd.Timestamp] = _utc_now,
    ) -> None:
        """Bind validated index and SNDK identities to append-only observer journals."""
        selected = dict(_DEFAULT_JOURNALS if journals is None else journals)
        if not selected or not set(selected).issubset(_SPECS):
            raise ValueError("HIP-3 v3 journals contain an unsupported symbol")
        self._journals = selected
        if observer_states is None and journals is None:
            observer_states = _DEFAULT_OBSERVER_STATES
        states = {} if observer_states is None else dict(observer_states)
        if not set(states).issubset(selected):
            raise ValueError("HIP-3 v3 observer states must match bound journals")
        self._observer_states = states
        self._health_now_fn = health_now_fn

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        """Return unseen prospective decisions without replaying old entries."""
        path = self._journals.get(symbol)
        if path is None:
            raise ValueError(f"HIP-3 v3 journal is not bound for {symbol}")
        loaded = _load_decisions(path, _SPECS[symbol])
        if symbol in self._observer_states:
            _require_observer_health(
                self._observer_states[symbol],
                self._health_now_fn(),
                loaded,
                _SPECS[symbol],
            )
        frame, _positions, completed_boundary = completed_hip3_inputs(
            bars,
            observed_at,
            after_decision_time_ms,
        )
        prior = 0 if after_decision_time_ms is None else after_decision_time_ms
        decisions = tuple(
            row for row in loaded if prior < row.decision_time_ms <= completed_boundary
        )
        if not decisions:
            return IntentBatch((), prior, ())
        evaluations = tuple(_evaluation(row, frame) for row in decisions)
        intents = tuple(
            _intent(row, evaluation.reference_price)
            for row, evaluation in zip(decisions, evaluations, strict=True)
            if row.eligible
        )
        return IntentBatch(intents, decisions[-1].decision_time_ms, evaluations)


def default_index_fresh15_journals() -> Mapping[str, Path]:
    """Return the two exact index journal paths without adding SNDK dependencies."""
    return {symbol: _DEFAULT_JOURNALS[symbol] for symbol in INDEX_SYMBOLS}


def require_fresh_index_observers(observed_at: pd.Timestamp) -> None:
    """Fail unless both default index observers are fresh and coherent."""
    for symbol in INDEX_SYMBOLS:
        require_fresh_index_observer(symbol, observed_at)


def require_fresh_index_observer(
    symbol: str,
    observed_at: pd.Timestamp,
) -> None:
    """Fail unless one exact default pressure observer is fresh and coherent."""
    if symbol not in _SPECS:
        raise ValueError(f"unsupported HIP-3 v3 observer symbol: {symbol}")
    decisions = _load_decisions(_DEFAULT_JOURNALS[symbol], _SPECS[symbol])
    _require_observer_health(
        _DEFAULT_OBSERVER_STATES[symbol],
        observed_at,
        decisions,
        _SPECS[symbol],
    )


def _require_observer_health(
    paths: tuple[Path, Path],
    observed_at: pd.Timestamp,
    decisions: tuple[_Decision, ...],
    spec: Hip3BreakoutShadowSpec,
) -> None:
    status = _mapping(
        json.loads(paths[0].read_text(encoding="utf-8")), "observer status"
    )
    cursor = _mapping(
        json.loads(paths[1].read_text(encoding="utf-8")), "observer cursor"
    )
    if not _observer_identity_valid(status, cursor, spec):
        raise ValueError("HIP-3 v3 observer identity is invalid")
    _require_running_observer(status)
    timestamp = pd.Timestamp(observed_at)
    if timestamp.tzinfo is None:
        raise ValueError("HIP-3 observed_at must be timezone-aware")
    observed_at_ms = int(timestamp.timestamp() * 1_000)
    status_at_ms = _integer(status.get("observed_at_ms"), "observer observed_at_ms")
    age_ms = observed_at_ms - status_at_ms
    if (
        not -_MAXIMUM_OBSERVER_CLOCK_SKEW_MS
        <= age_ms
        <= _MAXIMUM_OBSERVER_STATUS_AGE_MS
    ):
        raise Hip3ObserverUnavailableError("observer_status_stale")
    status_boundary = _integer(
        status.get("cursor_decision_time_ms"), "status cursor boundary"
    )
    cursor_boundary = _integer(
        cursor.get("decision_time_ms"), "cursor decision boundary"
    )
    journal_boundary = decisions[-1].decision_time_ms if decisions else None
    mixed_publication = status_boundary != cursor_boundary or (
        journal_boundary is not None and journal_boundary > cursor_boundary
    )
    if mixed_publication:
        raise Hip3ObserverUnavailableError("observer_checkpoint_publication_incomplete")


def _require_running_observer(status: Mapping[str, object]) -> None:
    """Reject stopped or faulted writers; freshness bounds degraded state."""
    raw_runtime = status.get("observer_runtime")
    if raw_runtime is None:
        return
    runtime = _mapping(raw_runtime, "observer runtime")
    lifecycle = _text(runtime.get("lifecycle"), "observer runtime lifecycle")
    if lifecycle in {"running", "degraded_transient"}:
        return
    raise Hip3ObserverUnavailableError("observer_runtime_not_running")


def _observer_identity_valid(
    status: Mapping[str, object],
    cursor: Mapping[str, object],
    spec: Hip3BreakoutShadowSpec,
) -> bool:
    token = spec.symbol.removeprefix("xyz:").lower()
    shared = (
        ("schema_version", 1),
        ("symbol", spec.symbol),
        ("provider_id", spec.provider_id),
        ("profile_id", spec.profile_id),
        ("execution_authority", "none"),
        ("report_only", True),
    )
    return bool(
        all(status.get(key) == value for key, value in shared)
        and all(cursor.get(key) == value for key, value in shared)
        and status.get("mode") == f"{token}_hip3_breakout_shadow_observer"
        and cursor.get("mode") == f"{token}_hip3_breakout_shadow_cursor"
        and status.get("signing_client_constructed") is False
        and status.get("orders_supported") is False
        and status.get("runtime_strategy_changed") is False
        and status.get("signal_ohlc_source") == "hyperliquid_public_candleSnapshot_15m"
        and status.get("pressure_source") == "hyperliquid_mainnet_l2_rest"
    )


def _load_decisions(path: Path, spec: Hip3BreakoutShadowSpec) -> tuple[_Decision, ...]:
    with snapshot_decision_ledger(path, allow_incomplete_tail=True) as (rows, _):
        values = tuple(_parse_row(row, spec) for row in rows)
    identities = [str(row.get("event_id")) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("HIP-3 v3 journal contains a duplicate event")
    boundaries = [row.decision_time_ms for row in values]
    if len(boundaries) != len(set(boundaries)):
        raise ValueError("HIP-3 v3 journal contains a duplicate decision boundary")
    if boundaries != sorted(boundaries):
        raise ValueError("HIP-3 v3 journal decisions must be ordered")
    return values


def _parse_row(row: Mapping[str, object], spec: Hip3BreakoutShadowSpec) -> _Decision:
    token = spec.symbol.removeprefix("xyz:").lower()
    decision = _mapping(row.get("decision"), "decision")
    boundary = _integer(decision.get("decision_time_ms"), "decision_time_ms")
    expected_id = f"{spec.provider_id}|{spec.symbol}|{boundary}"
    exact = (
        row.get("schema_version") == 1
        and row.get("event_type") == f"{token}_hip3_breakout_shadow_decision"
        and row.get("event_id") == expected_id
        and row.get("report_only") is True
        and row.get("execution_authority") == "none"
        and row.get("intents") == []
        and row.get("runtime_strategy_changed") is False
    )
    if not exact:
        raise ValueError("HIP-3 v3 journal envelope is invalid")
    return _parse_decision(decision, spec, boundary)


def _parse_decision(
    raw: Mapping[str, object],
    spec: Hip3BreakoutShadowSpec,
    boundary: int,
) -> _Decision:
    imbalance = _number(raw.get("decision_imbalance_10"), "decision_imbalance_10")
    decision = _Decision(
        _text(raw.get("provider_id"), "provider_id"),
        _text(raw.get("profile_id"), "profile_id"),
        _text(raw.get("symbol"), "symbol"),
        boundary,
        _side(raw.get("side")),
        _boolean(raw.get("eligible"), "eligible"),
        imbalance,
        _boolean(raw.get("pressure_fresh"), "pressure_fresh"),
        _text(raw.get("pressure_status"), "pressure_status"),
        _text(raw.get("pressure_source"), "pressure_source"),
        _boolean(raw.get("pressure_scan_complete"), "pressure_scan_complete"),
        _optional_integer(raw.get("pressure_exchange_ts_ms")),
        _optional_integer(raw.get("pressure_recv_ts_ms")),
        _integer(raw.get("pressure_snapshot_count"), "pressure_snapshot_count"),
        _optional_integer(raw.get("pressure_end_boundary_age_ms")),
        _integer(raw.get("observed_at_ms"), "observed_at_ms"),
        _integer(raw.get("decision_delay_ms"), "decision_delay_ms"),
        _boolean(raw.get("prospective"), "prospective"),
        _boolean(
            raw.get("pressure_state_history_complete"),
            "pressure_state_history_complete",
        ),
        parse_condition_telemetry(raw.get("condition_anatomy"), spec.config, imbalance),
    )
    _validate_decision(decision, spec, raw)
    return decision


def _validate_decision(
    value: _Decision,
    spec: Hip3BreakoutShadowSpec,
    raw: Mapping[str, object],
) -> None:
    identity = (
        value.provider_id == spec.provider_id
        and value.profile_id == spec.profile_id
        and value.symbol == spec.symbol
        and raw.get("execution_authority") == "none"
    )
    if not identity:
        raise ValueError("HIP-3 v3 decision identity is invalid")
    if value.observed_at_ms - value.decision_time_ms != value.decision_delay_ms:
        raise ValueError("HIP-3 v3 decision delay is inconsistent")
    if not 0 <= value.decision_delay_ms <= _MAXIMUM_DECISION_DELAY_MS:
        raise ValueError("HIP-3 v3 decision is not prospective")
    _validate_pressure(value)
    expected = bool(
        value.side
        and value.prospective
        and value.pressure_fresh
        and value.pressure_scan_complete
        and value.history_complete
    )
    if value.eligible != expected:
        raise ValueError("HIP-3 v3 eligible decision contract is inconsistent")


def _validate_pressure(value: _Decision) -> None:
    if value.pressure_source != "hyperliquid_mainnet_l2_rest":
        raise ValueError("HIP-3 v3 pressure source is invalid")
    if abs(value.imbalance) > 1.0:
        raise ValueError("HIP-3 v3 imbalance must be within [-1, 1]")
    exchange = value.pressure_exchange_ts_ms
    receipt = value.pressure_recv_ts_ms
    if exchange is not None or receipt is not None:
        _validate_pressure_times(value, exchange, receipt)
    if value.pressure_fresh and (
        value.pressure_status != "fresh"
        or value.snapshot_count < 2
        or exchange is None
        or receipt is None
        or value.boundary_age_ms is None
        or value.boundary_age_ms > 15_000
    ):
        raise ValueError("HIP-3 v3 fresh pressure contract is inconsistent")


def _validate_pressure_times(
    value: _Decision,
    exchange: int | None,
    receipt: int | None,
) -> None:
    if exchange is None or receipt is None:
        raise ValueError("HIP-3 v3 pressure timestamps must coexist")
    bar_open = value.decision_time_ms - 900_000
    valid = (
        bar_open <= exchange < value.decision_time_ms
        and exchange <= receipt <= value.observed_at_ms
        and value.boundary_age_ms == value.decision_time_ms - exchange
    )
    if not valid:
        raise ValueError("HIP-3 v3 pressure timestamps are inconsistent")


def _evaluation(value: _Decision, frame: pd.DataFrame) -> ProviderEvaluation:
    timestamp = pd.Timestamp(value.decision_time_ms - 900_000, unit="ms", tz="UTC")
    if timestamp not in frame.index:
        raise ValueError("HIP-3 v3 decision has no matching completed candle")
    reference = float(frame.loc[timestamp, "close"])
    conditions = (
        value.prospective,
        value.pressure_scan_complete,
        value.pressure_fresh,
        value.history_complete,
        value.side is not None,
    )
    blockers = tuple(
        label for passed, label in zip(conditions, _condition_labels()) if not passed
    )
    config = _SPECS[value.symbol].config
    indicators = condition_readiness_indicators(value.condition_anatomy, config)
    metrics = {
        **_metrics(value),
        **condition_readiness_metrics(value.condition_anatomy, config, value.imbalance),
    }
    readiness = SignalReadiness(
        side=value.side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=() if value.eligible else blockers,
        indicators=(
            f"SIDE {(value.side or 'NONE').upper()}",
            f"L2 IMB10 {value.imbalance:+.3f}",
            f"L2 STATUS {value.pressure_status.upper()}",
            f"BOOKS {value.snapshot_count}",
        )
        + indicators,
        metrics=metrics,
    )
    return ProviderEvaluation(
        strategy_id=value.provider_id,
        symbol=value.symbol,
        decision_time_ms=value.decision_time_ms,
        reference_price=reference,
        decision_action=f"enter_{value.side}" if value.eligible else "hold",
        eligible=value.eligible,
        reason=CONFIRMATION_REASONS[value.provider_id]
        if value.eligible
        else blockers[0],
        side=value.side,
        readiness=readiness,
        trigger="breakout_ema_depth10_pressure" if value.eligible else "none",
    )


def _metrics(value: _Decision) -> Mapping[str, object]:
    return {
        "imbalance_10": value.imbalance,
        "pressure_age_seconds": (
            None if value.boundary_age_ms is None else value.boundary_age_ms / 1_000.0
        ),
        "pressure_status": canonical_pressure_status(
            value.pressure_fresh,
            value.snapshot_count,
            value.pressure_exchange_ts_ms,
        ),
        "decision_delay_ms": value.decision_delay_ms,
        "pressure_boundary_age_ms": value.boundary_age_ms,
        "pressure_snapshot_count": value.snapshot_count,
        "pressure_imbalance_10": value.imbalance,
        "pressure_history_complete": value.history_complete,
        "pressure_scan_complete": value.pressure_scan_complete,
        "pressure_source": value.pressure_source,
        "source_timeframe": "15m",
    }


def _intent(value: _Decision, reference_price: float) -> StrategyIntent:
    if value.side not in {"long", "short"}:
        raise ValueError("HIP-3 v3 eligible intent requires an exact side")
    return StrategyIntent(
        strategy_id=value.provider_id,
        symbol=value.symbol,
        side=value.side,
        decision_time_ms=value.decision_time_ms,
        reference_price=reference_price,
        reason=f"{CONFIRMATION_REASONS[value.provider_id]}:{value.side}",
    )


def _condition_labels() -> tuple[str, ...]:
    return (
        "prospective_decision_unavailable",
        "pressure_scan_incomplete",
        "order_pressure_stale",
        "prior_pressure_state_unavailable",
        "fresh_breakout_onset_absent",
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"HIP-3 v3 {label} must be an object")
    return cast(dict[str, object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HIP-3 v3 {label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"HIP-3 v3 {label} must be a nonnegative integer")
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value, "optional integer")


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 v3 {label} must be numeric")
    output = float(value)
    if not math.isfinite(output):
        raise ValueError(f"HIP-3 v3 {label} must be finite")
    return output


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"HIP-3 v3 {label} must be boolean")
    return value


def _side(value: object) -> str | None:
    if value not in {None, "long", "short"}:
        raise ValueError("HIP-3 v3 side must be long, short, or null")
    return cast(str | None, value)
