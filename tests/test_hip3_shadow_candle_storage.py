"""Integrity tests for shared report-only HIP-3 source-candle storage."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_shadow_candle_storage import (
    ShadowCandleContract,
    append_candles_once,
    candle_summary,
)


def test_changed_existing_source_candle_is_rejected(tmp_path: Path) -> None:
    """One bar identity cannot silently retain conflicting retrieved values."""
    path = tmp_path / "candles.jsonl"
    contract = ShadowCandleContract(
        symbol="xyz:MU",
        source="hyperliquid_public_candleSnapshot_15m",
        event_type="mu_hip3_breakout_shadow_candle_observation",
        interval_ms=900_000,
        maximum_observation_delay_ms=15_000,
    )
    frame = _frame(100.0)
    append_candles_once(
        path,
        frame,
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:15:01Z"),
        prior_boundary_ms=0,
    )

    with pytest.raises(ValueError, match="changed source candle"):
        append_candles_once(
            path,
            _frame(101.0),
            contract=contract,
            observed_at_ms=_ms("2026-08-15T12:30:01Z"),
            prior_boundary_ms=0,
        )


def test_declared_non_signal_revision_keeps_first_observed_value(
    tmp_path: Path,
) -> None:
    """A declared volume revision is disclosed without rewriting evidence."""
    path = tmp_path / "candles.jsonl"
    contract = ShadowCandleContract(
        symbol="xyz:BRENTOIL",
        source="hyperliquid_public_candleSnapshot_5m",
        event_type="brentoil_oil_shock_candle_observation",
        interval_ms=300_000,
        maximum_observation_delay_ms=15_000,
        revision_tolerant_fields=("volume",),
    )
    append_candles_once(
        path,
        _frame(100.0, volume=7.0),
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:05:03Z"),
        prior_boundary_ms=0,
    )

    result = append_candles_once(
        path,
        _frame(100.0, volume=7.25),
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:10:03Z"),
        prior_boundary_ms=0,
    )

    stored = json.loads(path.read_text(encoding="utf-8").strip())
    assert stored["volume"] == 7.0
    assert result.frame.iloc[0]["volume"] == 7.0
    assert result.revision_rows == 1
    assert result.revision_fields == ("volume",)
    assert result.revision_bar_open_ms == (_ms("2026-08-15T12:00:00Z"),)


def test_declared_signal_revision_keeps_causal_first_observation(
    tmp_path: Path,
) -> None:
    """A disclosed OHLC revision cannot rewrite the decision-time input."""
    path = tmp_path / "candles.jsonl"
    contract = ShadowCandleContract(
        symbol="xyz:SP500",
        source="hyperliquid_public_candleSnapshot_15m",
        event_type="sp500_hip3_breakout_shadow_candle_observation",
        interval_ms=900_000,
        maximum_observation_delay_ms=15_000,
        revision_tolerant_fields=("close", "volume"),
    )
    append_candles_once(
        path,
        _frame(100.0, volume=7.0),
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:15:03Z"),
        prior_boundary_ms=0,
    )

    result = append_candles_once(
        path,
        _frame(100.1, volume=7.5),
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:30:03Z"),
        prior_boundary_ms=0,
    )

    stored = json.loads(path.read_text(encoding="utf-8").strip())
    assert stored["close"] == 100.0
    assert stored["volume"] == 7.0
    assert result.frame.iloc[0]["close"] == 100.0
    assert result.frame.iloc[0]["volume"] == 7.0
    assert result.revision_fields == ("close", "volume")


def test_summary_retains_late_non_warmup_candle_count(tmp_path: Path) -> None:
    """A retroactively captured decision bar remains visibly unresolved."""
    path = tmp_path / "candles.jsonl"
    contract = ShadowCandleContract(
        symbol="xyz:BRENTOIL",
        source="hyperliquid_public_candleSnapshot_5m",
        event_type="brentoil_oil_shock_candle_observation",
        interval_ms=300_000,
        maximum_observation_delay_ms=15_000,
    )
    append_candles_once(
        path,
        _frame(100.0),
        contract=contract,
        observed_at_ms=_ms("2026-08-15T12:06:00Z"),
        prior_boundary_ms=0,
    )

    assert candle_summary(path)["late_non_warmup_candle_rows_total"] == 1


def _frame(close: float, *, volume: float = 7.0) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp("2026-08-15T12:00:00Z")])
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
