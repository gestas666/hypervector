"""Shared deterministic fixtures for HIP-3 shadow lifecycle tests."""

from __future__ import annotations

import pandas as pd

from hypervector.live.hip3_breakout_shadow_specs import MU_SHADOW_SPEC
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)

BAR_MS = 15 * 60_000
START_MS = 1_800_000_000_000


def lifecycle_config() -> Hip3ShadowLifecycleConfig:
    """Return the frozen deterministic MU replay fixture configuration."""
    spec = MU_SHADOW_SPEC
    return Hip3ShadowLifecycleConfig(
        symbol=spec.symbol,
        provider_id=spec.provider_id,
        profile_id=spec.profile_id,
        ledger_profile_id=spec.ledger_profile_id,
        signal_config=spec.config,
        fee_bps_per_side=0.864,
        residual_latency_bps_per_side=1.0,
        stress_extra_bps_per_side=2.0,
        notional_usd=5_000.0,
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        maximum_hold_minutes=1_440,
        friction_source="fixture",
    )


def candles(
    long_onset_position: int,
    exit_position: int | None,
    *,
    periods: int = 40,
    side: str = "long",
    second_onset: int | None = None,
) -> pd.DataFrame:
    """Return exact 15-minute fixture candles for one synthetic onset."""
    index = pd.date_range(
        pd.Timestamp(START_MS, unit="ms", tz="UTC"), periods=periods, freq="15min"
    )
    direction = 1.0 if side == "long" else -1.0
    closes = [100.0] * periods
    closes[long_onset_position] = 100.0 + 2.0 * direction
    end = exit_position if exit_position is not None else periods
    closes[long_onset_position + 1 : end] = [100.0 + 3.0 * direction] * (
        end - long_onset_position - 1
    )
    if second_onset is not None:
        closes[second_onset - 1] = 100.0
        closes[second_onset] = 100.0 + 4.0 * direction
    if exit_position is not None:
        closes[exit_position:] = [100.0 - direction] * (periods - exit_position)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": closes,
            "high": [value + 0.2 for value in closes],
            "low": [value - 0.2 for value in closes],
            "close": closes,
            "volume": [1.0] * periods,
            "source": ["hl"] * periods,
        }
    )


def decisions(
    candle_rows: pd.DataFrame,
    *,
    eligible_position: int | None = None,
    eligible_positions: set[int] | None = None,
    side: str = "long",
) -> tuple[dict[str, object], ...]:
    """Return prospective authority-none decision rows matching candles."""
    selected = eligible_positions or (
        {eligible_position} if eligible_position is not None else set()
    )
    output: list[dict[str, object]] = []
    for position, timestamp in enumerate(candle_rows["timestamp"]):
        decision_time = int(pd.Timestamp(timestamp).timestamp() * 1_000) + BAR_MS
        eligible = position in selected
        decision = {
            "symbol": MU_SHADOW_SPEC.symbol,
            "provider_id": MU_SHADOW_SPEC.provider_id,
            "profile_id": MU_SHADOW_SPEC.profile_id,
            "decision_time_ms": decision_time,
            "observed_at_ms": decision_time + 500,
            "prospective": True,
            "eligible": eligible,
            "side": side if eligible else None,
            "decision_imbalance_10": (0.8 if side == "long" else -0.8)
            if eligible
            else 0.0,
            "pressure_fresh": True,
            "pressure_scan_complete": True,
            "pressure_state_history_complete": True,
            "execution_authority": "none",
        }
        output.append(
            {
                "event_type": "mu_hip3_breakout_shadow_decision",
                "event_id": f"fixture|{decision_time}",
                "report_only": True,
                "execution_authority": "none",
                "runtime_strategy_changed": False,
                "intents": [],
                "decision": decision,
            }
        )
    return tuple(output)


def book(
    timestamp_ms: int, midpoint: float, *, size: float = 100.0
) -> dict[str, object]:
    """Return one exact-identity depth-ten book observation."""
    return {
        "event_type": "book_observation",
        "profile_id": MU_SHADOW_SPEC.ledger_profile_id,
        "execution_authority": "none",
        "payload": {
            "symbol": MU_SHADOW_SPEC.symbol,
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": timestamp_ms - 5,
            "recv_ts_ms": timestamp_ms,
            "bids": _levels(midpoint - 0.01, -0.01, size),
            "asks": _levels(midpoint + 0.01, 0.01, size),
        },
    }


def marks(
    start_ms: int, end_ms: int, price: float, *, step_ms: int = 1_000
) -> tuple[dict[str, object], ...]:
    """Return a complete local-receipt mark path."""
    return tuple(
        mark(timestamp, price) for timestamp in range(start_ms, end_ms + 1, step_ms)
    )


def mark(timestamp_ms: int, price: float) -> dict[str, object]:
    """Return one exact-identity locally received mark observation."""
    return {
        "symbol": MU_SHADOW_SPEC.symbol,
        "observed_ts_ms": timestamp_ms,
        "received_ts_ns": timestamp_ms * 1_000_000,
        "mark_price": price,
        "source": "hyperliquid_ws_activeAssetCtx",
    }


def funding(candle_rows: pd.DataFrame) -> pd.DataFrame:
    """Return zero-rate official hourly funding over the fixture window."""
    start = pd.Timestamp(candle_rows["timestamp"].iloc[0]).floor("h")
    end = pd.Timestamp(candle_rows["timestamp"].iloc[-1]).ceil("h")
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, end, freq="h"),
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    )


def decision_time(candle_rows: pd.DataFrame, position: int) -> int:
    """Return the causal decision time after one completed fixture bar."""
    return (
        int(pd.Timestamp(candle_rows["timestamp"].iloc[position]).timestamp() * 1_000)
        + BAR_MS
    )


def timestamp(value_ms: int) -> pd.Timestamp:
    """Return a UTC pandas timestamp for one epoch-millisecond value."""
    return pd.Timestamp(value_ms, unit="ms", tz="UTC")


def _levels(start: float, step: float, size: float) -> list[dict[str, float]]:
    return [{"price": start + index * step, "size": size} for index in range(10)]
