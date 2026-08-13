"""Tests for the frozen HT structural/breakout agreement challenger."""

from __future__ import annotations

import pandas as pd

from hypervector.research.ht_agree_only_comparison import (
    build_ht_agree_only_comparison,
    build_ht_agree_only_market,
)


def _market(entry_sides: dict[int, str]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5_000, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_1m": "TREND_UP",
            "state_5m": "BREAKOUT",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    for position, side in entry_sides.items():
        frame.iloc[position, frame.columns.get_loc("entry_side")] = side
    return frame


def test_agree_only_market_censors_opposed_and_unavailable_onsets() -> None:
    structural = _market({100: "long", 200: "short", 300: "long"})
    breakout = _market({100: "long", 200: "long"})

    agree, accounting = build_ht_agree_only_market(structural, breakout)

    assert agree["entry_side"].dropna().to_dict() == {structural.index[100]: "long"}
    assert accounting == {
        "structural_onsets": 3,
        "aligned_onsets": 1,
        "opposed_onsets": 1,
        "unavailable_onsets": 1,
        "censored_onsets": 2,
    }


def test_comparison_is_report_only_and_preserves_v39_execution_contract() -> None:
    structural = _market({100: "long", 1_700: "short", 3_700: "long"})
    breakout = _market({100: "long", 1_700: "long", 3_700: "long"})

    report = build_ht_agree_only_comparison(
        structural,
        breakout,
        symbol="BTC",
        holdout_days=1,
    )

    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert report["contract"]["execution"] == {
        "stop_bps": 80.0,
        "maximum_hold_minutes": 480,
        "maximum_hold_policy": "extend_while_regime_supported",
        "hard_maximum_hold_minutes": 1440,
        "fee_bps_per_side": 4.5,
        "slippage_bps_per_side": 2.0,
    }
    assert report["source"]["symbol"] == "BTC"
    assert report["development"]["entry_accounting"]["opposed_onsets"] == 1
    assert report["holdout_already_opened"]["entry_accounting"]["aligned_onsets"] == 1
    locks = report["holdout_already_opened"]["control_profit_lock_surface"]
    assert set(locks) == {
        "a25_floor15_trail10",
        "a25_floor15_trail10_reset",
        "a40_floor15_trail20",
        "a40_floor15_trail20_reset",
        "a60_floor15_trail30",
        "a60_floor15_trail30_reset",
    }
    assert all(result["automatic_promotion"] is False for result in locks.values())
    assert all("reset_blocked_signals" in result for result in locks.values())
    assert report["disposition"] == "REPORT_ONLY_COMPARISON_NO_PROMOTION"
