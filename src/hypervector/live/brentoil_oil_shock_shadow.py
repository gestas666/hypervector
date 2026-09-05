"""Causal report-only decisions for the BRENTOIL oil-shock challenger."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
    build_hip3_oil_shock_reversion_signals,
)

BRENTOIL_OIL_SHOCK_PROVIDER_ID = (
    "hip3_brentoil_oil_shock_reversion_bidirectional_5m_shadow_v1"
)
BRENTOIL_OIL_SHOCK_PROFILE_ID = "brentoil_oil_shock_reversion_5m_shadow_v1"
BRENTOIL_OIL_SHOCK_SYMBOL = "xyz:BRENTOIL"
BRENTOIL_SIGNAL_SOURCE = "hyperliquid_public_candleSnapshot_5m"
_BAR_INTERVAL = pd.Timedelta(minutes=5)
_MAXIMUM_DECISION_DELAY_MS = 15_000


@dataclass(frozen=True)
class BrentoilOilShockShadowCursor:
    """Last prospectively processed completed-bar boundary."""

    provider_id: str
    profile_id: str
    symbol: str
    decision_time_ms: int
    observed_at_ms: int
    execution_authority: str = "none"


@dataclass(frozen=True)
class BrentoilOilShockShadowDecision:
    """One completed-bar shock observation with no execution authority."""

    provider_id: str
    profile_id: str
    symbol: str
    decision_time_ms: int
    observed_at_ms: int
    decision_delay_ms: int
    prior_decision_boundary_ms: int
    side: str | None
    eligible: bool
    prospective: bool
    non_action_reason: str | None
    trailing_return_bps: float | None
    shock_threshold_bps: float | None
    candle_open: float
    candle_high: float
    candle_low: float
    candle_close: float
    candle_volume: float
    signal_window_sha256: str
    signal_ohlc_source: str = BRENTOIL_SIGNAL_SOURCE
    execution_authority: str = "none"


@dataclass(frozen=True)
class BrentoilOilShockShadowBatch:
    """One collector result with an advanced durable cursor."""

    decisions: tuple[BrentoilOilShockShadowDecision, ...]
    next_cursor: BrentoilOilShockShadowCursor
    retroactive_decisions_censored: int
    intents: tuple[()] = ()
    execution_authority: str = "none"


class BrentoilOilShockShadowCollector:
    """Evaluate only newly completed exact BRENTOIL five-minute bars."""

    def __init__(
        self,
        config: Hip3OilShockReversionConfig = Hip3OilShockReversionConfig(),
    ) -> None:
        """Freeze the development-selected signal contract."""
        self._config = config

    @property
    def config(self) -> Hip3OilShockReversionConfig:
        """Return the frozen causal signal configuration."""
        return self._config

    def __call__(
        self,
        bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        cursor: BrentoilOilShockShadowCursor,
    ) -> BrentoilOilShockShadowBatch:
        """Return at most one current prospective decision and skip backlog."""
        _require_identity(symbol, cursor)
        frame, positions = completed_brentoil_oil_inputs(
            bars,
            observed_at=observed_at,
            after_decision_time_ms=cursor.decision_time_ms,
        )
        if not positions:
            return BrentoilOilShockShadowBatch((), cursor, 0)
        signals = build_hip3_oil_shock_reversion_signals(frame, self._config)
        timestamp = positions[-1]
        decision = _decision(
            signals.loc[timestamp],
            frame.loc[timestamp],
            frame,
            timestamp,
            observed_at,
            cursor,
        )
        next_cursor = _next_cursor(decision)
        return BrentoilOilShockShadowBatch(
            (decision,), next_cursor, max(0, len(positions) - 1)
        )


def completed_brentoil_oil_inputs(
    bars: pd.DataFrame,
    *,
    observed_at: pd.Timestamp,
    after_decision_time_ms: int,
) -> tuple[pd.DataFrame, tuple[pd.Timestamp, ...]]:
    """Return causal completed five-minute bars and unseen row positions."""
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"BRENTOIL shadow bars missing columns: {missing}")
    observed = pd.Timestamp(observed_at)
    if observed.tzinfo is None:
        raise ValueError("BRENTOIL shadow observed_at must be timezone-aware")
    frame = bars.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    index = pd.DatetimeIndex(frame.pop("timestamp"))
    if index.empty or not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("BRENTOIL shadow bars must be ordered and unique")
    frame.index = index
    complete = index + _BAR_INTERVAL <= observed.tz_convert("UTC")
    frame = frame.loc[complete].copy()
    if frame.empty:
        raise ValueError("BRENTOIL shadow has no completed 5m bar")
    frame["gap_before_bars"] = _gap_counts(frame.index)
    positions = tuple(
        timestamp
        for timestamp in frame.index
        if _decision_time_ms(timestamp) > after_decision_time_ms
    )
    return frame, positions


def _decision(
    signal: pd.Series,
    candle: pd.Series,
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    observed_at: pd.Timestamp,
    cursor: BrentoilOilShockShadowCursor,
) -> BrentoilOilShockShadowDecision:
    decision_ms = _decision_time_ms(timestamp)
    observed_ms = int(pd.Timestamp(observed_at).timestamp() * 1_000)
    delay = observed_ms - decision_ms
    if delay < 0:
        raise ValueError("BRENTOIL shadow decision precedes its completed bar")
    side = _side(signal.get("entry_direction"))
    prospective = delay <= _MAXIMUM_DECISION_DELAY_MS
    eligible = side is not None and prospective
    return BrentoilOilShockShadowDecision(
        BRENTOIL_OIL_SHOCK_PROVIDER_ID,
        BRENTOIL_OIL_SHOCK_PROFILE_ID,
        BRENTOIL_OIL_SHOCK_SYMBOL,
        decision_ms,
        observed_ms,
        delay,
        cursor.decision_time_ms,
        side,
        eligible,
        prospective,
        _non_action_reason(side, prospective, signal.get("shock_threshold_bps")),
        _optional_float(signal.get("trailing_return_bps")),
        _optional_float(signal.get("shock_threshold_bps")),
        float(candle["open"]),
        float(candle["high"]),
        float(candle["low"]),
        float(candle["close"]),
        float(candle["volume"]),
        _signal_window_hash(frame),
    )


def _next_cursor(
    decision: BrentoilOilShockShadowDecision,
) -> BrentoilOilShockShadowCursor:
    return BrentoilOilShockShadowCursor(
        decision.provider_id,
        decision.profile_id,
        decision.symbol,
        decision.decision_time_ms,
        decision.observed_at_ms,
    )


def _require_identity(symbol: str, cursor: BrentoilOilShockShadowCursor) -> None:
    expected = (
        BRENTOIL_OIL_SHOCK_PROVIDER_ID,
        BRENTOIL_OIL_SHOCK_PROFILE_ID,
        BRENTOIL_OIL_SHOCK_SYMBOL,
        "none",
    )
    actual = (
        cursor.provider_id,
        cursor.profile_id,
        cursor.symbol,
        cursor.execution_authority,
    )
    if symbol != BRENTOIL_OIL_SHOCK_SYMBOL or actual != expected:
        raise ValueError("BRENTOIL oil-shock shadow identity is inconsistent")


def _gap_counts(index: pd.DatetimeIndex) -> pd.Series:
    intervals = index.to_series().diff() / _BAR_INTERVAL
    return intervals.sub(1).clip(lower=0).fillna(0).astype(int)


def _decision_time_ms(timestamp: pd.Timestamp) -> int:
    return int((timestamp + _BAR_INTERVAL).timestamp() * 1_000)


def _side(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    if value not in {"long", "short"}:
        raise ValueError("BRENTOIL shadow signal side is invalid")
    return str(value)


def _non_action_reason(
    side: str | None, prospective: bool, threshold: object
) -> str | None:
    if side is not None and prospective:
        return None
    if side is not None:
        return "decision_stale"
    if threshold is None or pd.isna(threshold):
        return "signal_history_incomplete"
    return "no_shock_onset"


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _signal_window_hash(frame: pd.DataFrame) -> str:
    rows = [
        {
            "timestamp": timestamp.isoformat(),
            **{name: float(row[name]) for name in ("open", "high", "low", "close")},
            "volume": float(row["volume"]),
            "gap_before_bars": int(row["gap_before_bars"]),
        }
        for timestamp, row in frame.iterrows()
    ]
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
