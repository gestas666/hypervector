from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_index_live_condition_diagnostic import (
    Hip3IndexLiveConditionConfig,
    build_hip3_index_live_condition_diagnostic,
)

_BAR_MS = 900_000


def _candles() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-01", periods=64, freq="15min", tz="UTC")
    close = [100.0 + index * 0.1 for index in range(64)]
    high = [value + 0.2 for value in close]
    low = [value - 0.2 for value in close]
    close[62] = max(high[30:62]) + 0.1
    high[62] = close[62] + 0.2
    low[62] = close[62] - 0.2
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
        }
    )


def _row(boundary_ms: int, *, eligible: bool, pressure: float) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "intents": [],
        "decision": {
            "decision_time_ms": boundary_ms,
            "decision_imbalance_10": pressure,
            "eligible": eligible,
            "execution_authority": "none",
            "pressure_fresh": True,
            "pressure_state_history_complete": True,
            "prospective": True,
            "provider_id": "index-v3",
            "profile_id": "sp500-v3",
            "side": "long" if eligible else None,
            "symbol": "xyz:SP500",
        },
    }


def _config(run_start_ms: int) -> Hip3IndexLiveConditionConfig:
    return Hip3IndexLiveConditionConfig(
        symbol="xyz:SP500",
        provider_id="index-v3",
        profile_id="sp500-v3",
        run_started_at_ms=run_start_ms,
        breakout=Hip3BreakoutPressureConfig(32, 21, 55, 0.1, 80.0),
    )


def test_diagnostic_excludes_pre_run_rows_and_explains_one_blocker() -> None:
    candles = _candles()
    boundaries = [
        int(candles.loc[index, "timestamp"].timestamp() * 1_000) + _BAR_MS
        for index in (60, 61, 62)
    ]
    rows = [
        _row(boundaries[0], eligible=False, pressure=0.4),
        _row(boundaries[1], eligible=False, pressure=0.4),
        _row(boundaries[2], eligible=True, pressure=0.4),
    ]

    report = build_hip3_index_live_condition_diagnostic(
        candles=candles,
        observer_rows=rows,
        config=_config(boundaries[1]),
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["coverage"]["current_run_decisions"] == 2
    assert report["coverage"]["excluded_pre_run_decisions"] == 1
    assert report["observer_outcomes"] == {"eligible": 1, "long": 1, "short": 0}
    assert report["sides"]["long"]["one_blocker"] == {"price_breakout": 1}
    assert report["sides"]["long"]["raw_condition_true"] == 1
    assert report["assessment"]["parameter_change_supported"] is False


def test_diagnostic_rejects_wrong_observer_identity() -> None:
    candles = _candles()
    boundary = int(candles.loc[62, "timestamp"].timestamp() * 1_000) + _BAR_MS
    row = _row(boundary, eligible=False, pressure=0.4)
    row["decision"]["symbol"] = "xyz:SPCX"

    with pytest.raises(ValueError, match="identity or authority"):
        build_hip3_index_live_condition_diagnostic(
            candles=candles,
            observer_rows=[row],
            config=_config(boundary - 1),
        )


def test_diagnostic_rejects_missing_ema_history() -> None:
    candles = _candles().tail(20).reset_index(drop=True)
    boundary = int(candles.loc[19, "timestamp"].timestamp() * 1_000) + _BAR_MS

    with pytest.raises(ValueError, match="indicator history"):
        build_hip3_index_live_condition_diagnostic(
            candles=candles,
            observer_rows=[_row(boundary, eligible=False, pressure=0.4)],
            config=_config(boundary - 1),
        )
