"""Tests for exact SP500 outage mark recovery without hindsight promotion."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.sp500_fresh15_gap_recovery import (
    Sp500Fresh15GapRecoveryConfig,
    build_sp500_fresh15_gap_recovery,
)

_GAP_START = 1_787_125_260_000
_GAP_END = _GAP_START + 13 * 60_000


def test_exact_marks_repair_risk_but_missing_decision_keeps_lifecycle_censored() -> (
    None
):
    report = build_sp500_fresh15_gap_recovery(
        preregistration=_preregistration(),
        watcher_status=_watcher_status(),
        decisions=_decisions(),
        candles=_recovery_candles(),
        price_manifest=_manifest(),
        prices=_prices(),
        config=Sp500Fresh15GapRecoveryConfig(),
    )

    assert report["mark_recovery"]["complete"] is True
    assert report["mark_recovery"]["stop_crossed"] is False
    assert report["recovered_candles"]["profit_lock_triggered"] is False
    assert report["decision_recovery"]["missing_boundaries_ms"] == [1_787_125_500_000]
    assert report["technical_assessment"] == {
        "mark_risk_path_resolved": True,
        "historical_candle_path_resolved": True,
        "prospective_decision_path_resolved": False,
        "full_lifecycle_path_resolved": False,
        "live_change_supported": False,
    }
    assert report["disposition"] == "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"


def test_stop_cross_inside_recovered_mark_path_requires_exact_exit_replay() -> None:
    prices = _prices()
    inside_gap = prices.index[prices["ts_ms"].ge(_GAP_START)][3]
    prices.loc[inside_gap, "mark_price"] = "7740.0"

    report = build_sp500_fresh15_gap_recovery(
        preregistration=_preregistration(),
        watcher_status=_watcher_status(),
        decisions=_decisions(),
        candles=_recovery_candles(),
        price_manifest=_manifest(),
        prices=prices,
        config=Sp500Fresh15GapRecoveryConfig(),
    )

    assert report["mark_recovery"]["stop_crossed"] is True
    assert report["disposition"] == "EXACT_EXIT_REPLAY_REQUIRED"
    assert report["technical_assessment"]["full_lifecycle_path_resolved"] is False


def test_mark_interval_over_frozen_limit_stays_unresolved() -> None:
    prices = _prices(step_ms=6_000)
    manifest = _manifest(row_count=len(prices))

    report = build_sp500_fresh15_gap_recovery(
        preregistration=_preregistration(),
        watcher_status=_watcher_status(),
        decisions=_decisions(),
        candles=_recovery_candles(),
        price_manifest=manifest,
        prices=prices,
        config=Sp500Fresh15GapRecoveryConfig(),
    )

    assert report["mark_recovery"]["complete"] is False
    assert report["technical_assessment"]["mark_risk_path_resolved"] is False
    assert report["disposition"] == "OPEN_LIFECYCLE_CENSORED_MARK_GAP"


def test_first_post_gap_mark_does_not_retroactively_trigger_outage_stop() -> None:
    prices = _prices()
    boundary = prices.index[prices["ts_ms"].eq(_GAP_END)][0]
    prices.loc[boundary, "mark_price"] = "7740.0"

    report = build_sp500_fresh15_gap_recovery(
        preregistration=_preregistration(),
        watcher_status=_watcher_status(),
        decisions=_decisions(),
        candles=_recovery_candles(),
        price_manifest=_manifest(),
        prices=prices,
        config=Sp500Fresh15GapRecoveryConfig(),
    )

    assert report["mark_recovery"]["stop_crossed"] is False


def test_duplicate_recovery_candle_is_rejected() -> None:
    candles = _recovery_candles()
    candles.append(dict(candles[0]))

    with pytest.raises(ValueError, match="duplicate"):
        build_sp500_fresh15_gap_recovery(
            preregistration=_preregistration(),
            watcher_status=_watcher_status(),
            decisions=_decisions(),
            candles=candles,
            price_manifest=_manifest(),
            prices=_prices(),
            config=Sp500Fresh15GapRecoveryConfig(),
        )


def _preregistration() -> dict[str, object]:
    return {
        "schema_version": "v58_sp500_fresh15_lifecycle_watch_preregistration_v1",
        "symbol": "xyz:SP500",
        "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
        "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
        "event": {
            "decision_time_ms": 1_787_120_100_000,
            "entry_time_ms": 1_787_120_101_436,
            "side": "short",
            "entry_price": 7675.6,
            "stop_price": 7737.0048,
        },
        "profit_lock": {
            "policy_id": "v58_hip3_sp500_100_40_80",
            "activation_bps": 100.0,
            "floor_bps": 40.0,
            "trailing_giveback_bps": 80.0,
        },
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
    }


def _watcher_status() -> dict[str, object]:
    return {
        "schema_version": "sp500_fresh15_lifecycle_watch_status_v1",
        "symbol": "xyz:SP500",
        "execution_authority": "none",
        "lifecycle": dict(_preregistration()["event"]),
        "trigger_reasons": ["profit_lock_source_gap", "profit_lock_source_stale"],
        "path": {
            "last_bar_close_ms": _GAP_START,
            "profit_lock_activated": False,
            "source_gap": True,
        },
    }


def _decisions() -> list[dict[str, object]]:
    return [
        {"decision": {"decision_time_ms": 1_787_124_600_000}},
        {"decision": {"decision_time_ms": 1_787_126_400_000}},
    ]


def _recovery_candles() -> list[dict[str, object]]:
    return [
        {
            "event_type": "sp500_hip3_breakout_shadow_profit_lock_candle_observation",
            "symbol": "xyz:SP500",
            "source": "hyperliquid_public_candleSnapshot_1m",
            "prospective": False,
            "execution_authority": "none",
            "bar_open_ms": timestamp,
            "bar_close_ms": timestamp + 60_000,
            "observed_at_ms": _GAP_END + 1_000,
            "open": 7692.0,
            "high": 7694.0,
            "low": 7690.0,
            "close": 7692.0,
        }
        for timestamp in range(_GAP_START, _GAP_END, 60_000)
    ]


def _manifest(row_count: int | None = None) -> dict[str, object]:
    rows = len(_prices()) if row_count is None else row_count
    return {
        "schema_version": 1,
        "complete": True,
        "continuation_cursor": None,
        "market_family": "hip3",
        "source": "0xarchive_hyperliquid_prices",
        "symbol": "xyz:SP500",
        "requested_start": "2026-08-19T07:40:00+00:00",
        "requested_end": "2026-08-19T07:56:00+00:00",
        "row_count": rows,
    }


def _prices(step_ms: int = 3_000) -> pd.DataFrame:
    timestamps = list(range(_GAP_START - 60_000, _GAP_END + 120_000, step_ms))
    return pd.DataFrame(
        {
            "ts_ms": timestamps,
            "mark_price": ["7692.0"] * len(timestamps),
            "source": ["0xarchive_hyperliquid_prices"] * len(timestamps),
        }
    )
