"""Contracts for development-only SPCX long entry diagnosis."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import numpy as np
import pytest

from hypervector.research.hip3_cash_open_long_entry_diagnosis import (
    _count,
    build_cash_open_long_entry_diagnosis,
)
from hypervector.research.shared_portfolio_models import SharedPortfolioTrade


def test_diagnosis_joins_causal_features_outcomes_and_path_status() -> None:
    bars, signals = _inputs()
    nominal = (_trade(0, 10.0), _trade(1, -5.0))
    stress = (_trade(0, 8.0), _trade(1, -7.0))

    report = build_cash_open_long_entry_diagnosis(
        bars, signals, nominal, stress, _path_detail(nominal[0])
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["threshold_selection"] is False
    assert report["entry_count"] == 2
    first, second = report["entries"]
    assert first["causal_features"]["opening_reversal_bps"] == pytest.approx(100.0)
    assert first["causal_features"]["gap_recovery_fraction"] == pytest.approx(0.1)
    assert second["causal_features"]["gap_recovery_fraction"] == pytest.approx(-0.2)
    assert first["technical_path"]["resolved"] is False
    assert second["technical_path"]["resolved"] is True
    assert report["stress_outcome_summary"]["wins"]["count"] == 1
    assert report["stress_outcome_summary"]["losses"]["count"] == 1


def test_diagnosis_rejects_nominal_stress_entry_identity_mismatch() -> None:
    bars, signals = _inputs()
    nominal = (_trade(0, 10.0),)
    mismatched = replace(_trade(0, 8.0), signal_time_utc=_time(1))

    with pytest.raises(ValueError, match="entry identities differ"):
        build_cash_open_long_entry_diagnosis(
            bars, signals, nominal, (mismatched,), _path_detail(nominal[0])
        )


def test_exact_numpy_count_scalars_are_accepted() -> None:
    assert _count(np.int64(7431), "trade count") == 7431


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.DatetimeIndex([_time(0), _time(1)])
    bars = pd.DataFrame(
        {
            "signal_open": [100.0, 100.0],
            "signal_close": [101.0, 99.0],
            "decision_spread_bps": [2.0, 4.0],
            "decision_imbalance_10": [0.2, -0.1],
            "public_trade_count": [100, 50],
            "signal_volume": [20.0, 10.0],
            "source_snapshot_count": [200, 180],
        },
        index=index,
    )
    signals = pd.DataFrame(
        {
            "long_entry": [True, True],
            "previous_cash_close": [110.0, 105.0],
            "opening_gap_bps": [-900.0, -500.0],
        },
        index=index,
    )
    return bars, signals


def _trade(position: int, net_pnl_usd: float) -> SharedPortfolioTrade:
    signal = pd.Timestamp(_time(position))
    entry = signal + pd.Timedelta(minutes=15)
    exit_at = entry + pd.Timedelta(minutes=30)
    return SharedPortfolioTrade(
        "hip3_cash_open_gap_reversal_long@15m",
        "long",
        signal.isoformat(),
        entry.isoformat(),
        exit_at.isoformat(),
        position,
        position + 1,
        position + 3,
        100.0,
        101.0,
        110.0,
        99.2,
        84.0,
        1.0,
        10.0,
        100.0,
        10.0,
        net_pnl_usd + 0.1,
        0.1,
        0.0,
        net_pnl_usd,
        5000.0,
        5000.0 + net_pnl_usd,
        "target" if net_pnl_usd > 0 else "stop",
        False,
    )


def _path_detail(trade: SharedPortfolioTrade) -> dict[str, object]:
    unresolved = {
        "signal_time_utc": trade.signal_time_utc,
        "entry_time_utc": trade.entry_time_utc,
        "full_mark_path_unresolved": True,
        "entry_slice_unresolved": False,
        "stale_l2_entry": False,
        "stale_l2_exit": False,
        "data_gap_exit": False,
    }
    scenario = {"completed_trades": 2, "unresolved_lifecycles": [unresolved]}
    return {"nominal": scenario, "stress": scenario}


def _time(position: int) -> str:
    return (
        pd.Timestamp("2026-06-10T13:30:00Z") + pd.Timedelta(days=position)
    ).isoformat()
