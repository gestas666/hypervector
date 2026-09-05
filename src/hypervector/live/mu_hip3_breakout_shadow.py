"""Execution-incapable shadow collector for the selected ``xyz:MU`` track."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.live.hip3_provider_inputs import (
    completed_hip3_inputs,
    decision_time_ms,
)
from hypervector.live.hip3_fresh15_condition_telemetry import (
    Hip3Fresh15ConditionTelemetry,
    build_condition_telemetry,
)
from hypervector.live.hip3_breakout_shadow_specs import (
    CL_SHADOW_SPEC,
    HIP3_SHADOW_SPECS,
    MU_SHADOW_SPEC,
    SILVER_SHADOW_SPEC,
    SKHX_SHADOW_SPEC,
    Hip3BreakoutShadowSpec,
)
from hypervector.live.mu_hip3_preclose_pressure import (
    MuPreclosePressureEvidence,
    MuPreclosePressureSourceProtocol,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)


__all__ = (
    "CL_SHADOW_SPEC",
    "MU_SHADOW_SPEC",
    "SILVER_SHADOW_SPEC",
    "SKHX_SHADOW_SPEC",
    "Hip3BreakoutShadowSpec",
    "MuHip3BreakoutShadowBatch",
    "MuHip3BreakoutShadowCollector",
    "MuHip3BreakoutShadowCursor",
    "MuHip3BreakoutShadowDecision",
)


MU_SHADOW_PROVIDER_ID = MU_SHADOW_SPEC.provider_id
MU_SHADOW_PROFILE_ID = MU_SHADOW_SPEC.profile_id
_MAXIMUM_DECISION_DELAY_MS = 15_000


@dataclass(frozen=True)
class MuHip3BreakoutShadowDecision:
    """One report-only completed-bar MU breakout decision."""

    provider_id: str
    profile_id: str
    symbol: str
    decision_time_ms: int
    side: str | None
    eligible: bool
    decision_imbalance_10: float
    pressure_fresh: bool
    pressure_status: str
    pressure_source: str
    pressure_scan_complete: bool
    pressure_exchange_ts_ms: int | None
    pressure_recv_ts_ms: int | None
    pressure_snapshot_count: int
    pressure_end_boundary_age_ms: int | None
    observed_at_ms: int
    decision_delay_ms: int
    prior_decision_boundary_ms: int
    prospective: bool
    pressure_state_history_complete: bool
    execution_authority: str = "none"
    condition_anatomy: Hip3Fresh15ConditionTelemetry | None = None


@dataclass(frozen=True)
class MuHip3BreakoutShadowCursor:
    """Frozen prior decision state required for prospective onset detection."""

    provider_id: str
    profile_id: str
    symbol: str
    decision_time_ms: int
    bar_open_ms: int
    observed_at_ms: int
    long_raw: bool | None
    short_raw: bool | None
    pressure: MuPreclosePressureEvidence | None
    execution_authority: str = "none"

    def __post_init__(self) -> None:
        """Reject aliased or internally inconsistent restart state."""
        _spec_for_identity(self.provider_id, self.profile_id, self.symbol)
        if self.execution_authority != "none":
            raise ValueError("HIP-3 shadow cursor identity is invalid")
        for value in (self.decision_time_ms, self.bar_open_ms, self.observed_at_ms):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("MU shadow cursor times must be nonnegative integers")
        if self.bar_open_ms + 900_000 != self.decision_time_ms:
            raise ValueError("MU shadow cursor must identify one exact 15m bar")
        if self.observed_at_ms < self.decision_time_ms:
            raise ValueError("MU shadow cursor observation precedes its decision")
        if (self.long_raw is None) != (self.short_raw is None):
            raise ValueError(
                "MU shadow cursor raw states must both be known or unknown"
            )
        if any(
            value is not None and not isinstance(value, bool)
            for value in (self.long_raw, self.short_raw)
        ):
            raise ValueError("MU shadow cursor raw states must be booleans")
        raw_unknown = self.long_raw is None
        if raw_unknown != (self.pressure is None):
            raise ValueError("MU shadow cursor raw state and pressure must coexist")
        if self.pressure is not None:
            self._validate_pressure()

    def _validate_pressure(self) -> None:
        pressure = self.pressure
        if pressure is None:
            raise AssertionError("validated MU cursor pressure cannot be absent")
        if (
            pressure.symbol != self.symbol
            or pressure.bar_open_ms != self.bar_open_ms
            or pressure.bar_close_ms != self.decision_time_ms
            or pressure.observed_at_ms != self.observed_at_ms
        ):
            raise ValueError("MU shadow cursor pressure identity is inconsistent")
        if self.observed_at_ms - self.decision_time_ms > _MAXIMUM_DECISION_DELAY_MS:
            raise ValueError("MU shadow cursor pressure was observed too late")


@dataclass(frozen=True)
class MuHip3BreakoutShadowBatch:
    """Shadow decisions with no executable intent surface."""

    decisions: tuple[MuHip3BreakoutShadowDecision, ...]
    latest_decision_time_ms: int
    observed_at_ms: int
    prior_decision_boundary_ms: int
    retroactive_decisions_censored: int
    next_cursor: MuHip3BreakoutShadowCursor
    intents: tuple[()] = ()
    execution_authority: str = "none"


class MuHip3BreakoutShadowCollector:
    """Evaluate frozen MU breakouts without registering execution authority."""

    def __init__(
        self,
        *,
        pressure_source: MuPreclosePressureSourceProtocol,
        spec: Hip3BreakoutShadowSpec = MU_SHADOW_SPEC,
    ) -> None:
        """Bind the causal completed-bar pressure evidence source."""
        self._pressure_source = pressure_source
        self._spec = spec

    @property
    def config(self) -> Hip3BreakoutPressureConfig:
        """Return the immutable development-selected signal configuration."""
        return self._spec.config

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        cursor: MuHip3BreakoutShadowCursor | None,
    ) -> MuHip3BreakoutShadowBatch:
        """Return unseen completed-bar decisions while emitting no intents."""
        if symbol != self._spec.symbol:
            raise ValueError(
                f"HIP-3 breakout shadow requires exact {self._spec.symbol}"
            )
        if cursor is None:
            raise ValueError("MU shadow requires a persisted restart cursor")
        _validate_cursor_symbol(cursor, symbol)
        frame, positions, boundary = completed_hip3_inputs(
            bars,
            observed_at,
            cursor.decision_time_ms,
        )
        observed_ms = _timestamp_ms(observed_at)
        prospective, censored = _prospective_positions(positions, observed_ms)
        if not prospective:
            return _batch(
                (),
                boundary,
                observed_ms,
                cursor,
                censored,
                _advanced_cursor(cursor, boundary, observed_ms, bool(positions)),
            )
        if len(prospective) != 1:
            raise ValueError("MU shadow accepts at most one prospective 15m decision")
        return _prospective_batch(
            frame,
            prospective[0],
            boundary,
            observed_ms,
            cursor,
            censored,
            self._pressure_source,
            symbol,
            self._spec,
        )


def _prospective_batch(
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    boundary: int,
    observed_at_ms: int,
    cursor: MuHip3BreakoutShadowCursor,
    censored: int,
    source: MuPreclosePressureSourceProtocol,
    symbol: str,
    spec: Hip3BreakoutShadowSpec,
) -> MuHip3BreakoutShadowBatch:
    pressure = source.completed_bar(
        symbol,
        bar_open_ms=_timestamp_ms(timestamp),
        bar_close_ms=decision_time_ms(timestamp),
        observed_at_ms=observed_at_ms,
    )
    signals = _signal_rows(frame, cursor, timestamp, pressure, spec)
    decision, next_cursor = _decision(
        timestamp,
        frame.loc[timestamp],
        signals.loc[timestamp],
        pressure,
        observed_at_ms,
        cursor,
        _pressure_history_complete(frame, cursor, timestamp),
        spec,
    )
    return _batch(
        (decision,),
        boundary,
        observed_at_ms,
        cursor,
        censored,
        next_cursor,
    )


def _signal_rows(
    frame: pd.DataFrame,
    cursor: MuHip3BreakoutShadowCursor,
    timestamp: pd.Timestamp,
    pressure: MuPreclosePressureEvidence,
    spec: Hip3BreakoutShadowSpec,
) -> pd.DataFrame:
    signal_input = frame.copy()
    signal_input["decision_imbalance_10"] = 0.0
    prior_timestamp = pd.Timestamp(cursor.bar_open_ms, unit="ms", tz="UTC")
    if cursor.pressure is not None and prior_timestamp in signal_input.index:
        signal_input.loc[prior_timestamp, "decision_imbalance_10"] = (
            _effective_pressure(cursor.pressure)
        )
    signal_input.loc[timestamp, "decision_imbalance_10"] = _effective_pressure(pressure)
    return build_breakout_pressure_signals(signal_input, spec.config)


def _decision(
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
    pressure: MuPreclosePressureEvidence,
    observed_at_ms: int,
    cursor: MuHip3BreakoutShadowCursor,
    pressure_history_complete: bool,
    spec: Hip3BreakoutShadowSpec,
) -> tuple[MuHip3BreakoutShadowDecision, MuHip3BreakoutShadowCursor]:
    condition_anatomy = build_condition_telemetry(bar, signal, spec.config)
    long_raw, short_raw = _raw_states(bar, signal, spec.config)
    prior_long, prior_short = _prior_raw_states(bar, cursor, pressure_history_complete)
    long_entry = long_raw and not prior_long
    short_entry = short_raw and not prior_short
    side = "long" if long_entry else ("short" if short_entry else None)
    decision_ms = decision_time_ms(timestamp)
    decision = MuHip3BreakoutShadowDecision(
        spec.provider_id,
        spec.profile_id,
        spec.symbol,
        decision_ms,
        side,
        side is not None and pressure.fresh and pressure_history_complete,
        _effective_pressure(pressure),
        pressure.fresh,
        pressure.status,
        pressure.source,
        pressure.scan_complete,
        pressure.last_exchange_ts_ms,
        pressure.last_recv_ts_ms,
        pressure.snapshot_count,
        pressure.end_boundary_age_ms,
        observed_at_ms,
        observed_at_ms - decision_ms,
        cursor.decision_time_ms,
        True,
        pressure_history_complete,
        condition_anatomy=condition_anatomy,
    )
    return decision, _cursor_from_decision(
        timestamp,
        observed_at_ms,
        long_raw,
        short_raw,
        pressure,
        spec,
    )


def _batch(
    decisions: tuple[MuHip3BreakoutShadowDecision, ...],
    boundary: int,
    observed_at_ms: int,
    prior_cursor: MuHip3BreakoutShadowCursor,
    censored: int,
    next_cursor: MuHip3BreakoutShadowCursor,
) -> MuHip3BreakoutShadowBatch:
    return MuHip3BreakoutShadowBatch(
        decisions,
        boundary,
        observed_at_ms,
        prior_cursor.decision_time_ms,
        censored,
        next_cursor,
    )


def _prospective(timestamp: pd.Timestamp, observed_at_ms: int) -> bool:
    delay_ms = observed_at_ms - decision_time_ms(timestamp)
    return 0 <= delay_ms <= _MAXIMUM_DECISION_DELAY_MS


def _prospective_positions(
    positions: tuple[pd.Timestamp, ...], observed_at_ms: int
) -> tuple[tuple[pd.Timestamp, ...], int]:
    prospective = tuple(
        timestamp for timestamp in positions if _prospective(timestamp, observed_at_ms)
    )
    return prospective, len(positions) - len(prospective)


def _pressure_history_complete(
    frame: pd.DataFrame,
    cursor: MuHip3BreakoutShadowCursor,
    timestamp: pd.Timestamp,
) -> bool:
    position = frame.index.get_loc(timestamp)
    if not isinstance(position, int):
        raise ValueError("MU shadow decision timestamp must resolve to one bar")
    if int(frame.iloc[position]["gap_before_bars"]) > 0:
        return True
    if position == 0:
        return False
    prior = frame.index[position - 1]
    return bool(
        cursor.bar_open_ms == _timestamp_ms(prior)
        and cursor.decision_time_ms == _timestamp_ms(timestamp)
        and cursor.pressure is not None
        and cursor.pressure.fresh
        and cursor.long_raw is not None
        and cursor.short_raw is not None
    )


def _raw_states(
    bar: pd.Series,
    signal: pd.Series,
    config: Hip3BreakoutPressureConfig,
) -> tuple[bool, bool]:
    close = float(bar["close"])
    pressure = float(signal["decision_imbalance_10"])
    fast = float(signal["fast_ema"])
    slow = float(signal["slow_ema"])
    high = float(signal["prior_breakout_high"])
    low = float(signal["prior_breakout_low"])
    long_raw = close > high and fast > slow and pressure >= config.minimum_abs_imbalance
    short_raw = (
        close < low and fast < slow and pressure <= -config.minimum_abs_imbalance
    )
    return long_raw, short_raw


def _prior_raw_states(
    bar: pd.Series,
    cursor: MuHip3BreakoutShadowCursor,
    history_complete: bool,
) -> tuple[bool, bool]:
    if int(bar["gap_before_bars"]) > 0 or not history_complete:
        return False, False
    return bool(cursor.long_raw), bool(cursor.short_raw)


def _cursor_from_decision(
    timestamp: pd.Timestamp,
    observed_at_ms: int,
    long_raw: bool,
    short_raw: bool,
    pressure: MuPreclosePressureEvidence,
    spec: Hip3BreakoutShadowSpec,
) -> MuHip3BreakoutShadowCursor:
    return MuHip3BreakoutShadowCursor(
        spec.provider_id,
        spec.profile_id,
        spec.symbol,
        decision_time_ms(timestamp),
        _timestamp_ms(timestamp),
        observed_at_ms,
        long_raw,
        short_raw,
        pressure,
    )


def _advanced_cursor(
    prior: MuHip3BreakoutShadowCursor,
    boundary: int,
    observed_at_ms: int,
    unseen_positions: bool,
) -> MuHip3BreakoutShadowCursor:
    if not unseen_positions:
        return prior
    spec = _spec_for_identity(prior.provider_id, prior.profile_id, prior.symbol)
    return MuHip3BreakoutShadowCursor(
        spec.provider_id,
        spec.profile_id,
        spec.symbol,
        boundary,
        boundary - 900_000,
        observed_at_ms,
        None,
        None,
        None,
    )


def _validate_cursor_symbol(
    cursor: MuHip3BreakoutShadowCursor,
    symbol: str,
) -> None:
    if cursor.symbol != symbol:
        raise ValueError("MU shadow cursor symbol does not match the request")


def _effective_pressure(evidence: MuPreclosePressureEvidence) -> float:
    if not evidence.fresh or evidence.imbalance_10 is None:
        return 0.0
    return evidence.imbalance_10


def _timestamp_ms(timestamp: pd.Timestamp) -> int:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError("MU shadow timestamps must be timezone-aware")
    return int(value.timestamp() * 1_000)


def _spec_for_identity(
    provider_id: str,
    profile_id: str,
    symbol: str,
) -> Hip3BreakoutShadowSpec:
    matches = tuple(
        spec
        for spec in HIP3_SHADOW_SPECS
        if (spec.provider_id, spec.profile_id, spec.symbol)
        == (provider_id, profile_id, symbol)
    )
    if len(matches) != 1:
        raise ValueError("HIP-3 shadow cursor identity is invalid")
    return matches[0]
