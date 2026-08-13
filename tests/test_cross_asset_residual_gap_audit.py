"""Tests for explicit continuity-fill impact attribution."""

from __future__ import annotations

import pandas as pd

from hypervector.research.cross_asset_residual_gap_audit import (
    build_residual_gap_audit,
)
from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualSignal,
)
from hypervector.research.cross_asset_residual_replay import evaluate_residual_pair


def _minutes(symbol: str, price: float) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=16, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "funding_rate": 0.0,
            "source": "hl",
            "symbol": symbol,
        }
    )
    frame.loc[3, "source"] = "hl_gap_fill"
    frame.loc[6, "source"] = "hl_gap_fill"
    return frame


def _signal() -> ResidualSignal:
    return ResidualSignal(
        decision_time_utc="2026-01-01T00:05:00+00:00",
        left_symbol="BTC",
        right_symbol="ETH",
        direction="long_spread",
        hedge_ratio=1.0,
        intercept=0.0,
        residual=-0.02,
        residual_mean=0.0,
        residual_std=0.01,
        zscore=-2.5,
        error_correction_t=-3.0,
        fit_start_utc="2026-01-01T00:00:00+00:00",
        fit_end_utc="2026-01-01T00:05:00+00:00",
    )


def test_audit_attributes_signal_and_lifecycle_gap_dependence() -> None:
    bars = {"BTC": _minutes("BTC", 100.0), "ETH": _minutes("ETH", 50.0)}
    signal = _signal()
    report = evaluate_residual_pair(
        minute_bars=bars,
        states=pd.DataFrame(
            {
                "decision_time_utc": ["2026-01-01T00:10:00+00:00"],
                "zscore": [0.1],
            }
        ),
        signals=(signal,),
        config=CrossAssetResidualConfig(maximum_hold_bars=12),
    )

    audit = build_residual_gap_audit(
        left_symbol="BTC",
        right_symbol="ETH",
        minute_frames=bars,
        signals=(signal,),
        trades=report.trades,
    )

    assert audit["pair_gap_minutes"] == 2
    assert audit["gap_minutes_by_symbol"] == {"BTC": 2, "ETH": 2}
    assert audit["formation_affected_signals"] == 1
    assert audit["decision_bucket_affected_signals"] == 1
    assert audit["lifecycle_affected_trades"] == 1
    assert audit["lifecycle_affected_net_pnl_usd"] == report.trades[0].net_pnl_usd
    assert audit["unaffected_net_pnl_usd"] == 0.0


def test_audit_reports_clean_evidence_without_false_contamination() -> None:
    bars = {"BTC": _minutes("BTC", 100.0), "ETH": _minutes("ETH", 50.0)}
    for frame in bars.values():
        frame.loc[:, "source"] = "hl"

    audit = build_residual_gap_audit(
        left_symbol="BTC",
        right_symbol="ETH",
        minute_frames=bars,
        signals=(),
        trades=(),
    )

    assert audit["pair_gap_minutes"] == 0
    assert audit["formation_affected_signals"] == 0
    assert audit["lifecycle_affected_trades"] == 0
