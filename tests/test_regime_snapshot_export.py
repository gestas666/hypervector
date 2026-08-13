"""Parity and honesty tests for file-based regime snapshot playback."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from hypervector.regime.composite import classify_multitimeframe
from hypervector.regime.snapshot_export import build_regime_snapshots
from hypervector.strategies.hypervelocity_contract import faithful_regime_config


def _bars(count: int = 240) -> pd.DataFrame:
    index = pd.date_range("2026-07-20", periods=count, freq="1min", tz="UTC")
    close = pd.Series(64_000.0 + np.linspace(0.0, 500.0, count), index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": 10.0,
        },
        index=index,
    )


def test_snapshot_states_and_score_match_canonical_backend(tmp_path: Path) -> None:
    bars = _bars()
    canonical = classify_multitimeframe(bars, faithful_regime_config()).iloc[-1]

    latest = build_regime_snapshots(bars, data_root=tmp_path, max_bars=1)[0]

    assert latest["open"] == pytest.approx(float(bars["open"].iloc[-1]))
    assert latest["regime_state"] == canonical["primary_regime"]
    assert latest["trend_1m"] == canonical["state_1m"]
    assert latest["trend_5m"] == canonical["state_5m"]
    assert latest["trend_15m"] == canonical["context_15m"]
    assert latest["regime_reason"] == canonical["reason"]
    assert latest["regime_strength_score"] == pytest.approx(
        canonical["regime_strength_score"], abs=0.0005
    )
    assert (
        latest["regime_score_source"]
        == "mean_multitimeframe_ema_gap_strength_percentile_rank"
    )
    assert latest["confidence_is_gate"] is False
    assert latest["bbwp_percentile"] == pytest.approx(
        canonical["bbwp_percentile"], abs=0.005
    )
    assert latest["rsi"] == pytest.approx(canonical["rsi"], abs=0.005)
    assert latest["rsi_ema"] == pytest.approx(canonical["rsi_ema"], abs=0.005)
    assert latest["compression_ready"] is bool(canonical["compression_ready"])
    assert latest["ema_gap_bps_signed"] == pytest.approx(
        canonical["ema_gap_bps_signed"], abs=0.005
    )


def test_snapshot_does_not_invent_missing_microstructure_or_funding(
    tmp_path: Path,
) -> None:
    latest = build_regime_snapshots(_bars(), data_root=tmp_path, max_bars=1)[0]

    assert latest["opi"] is None
    assert latest["spread_bps"] is None
    assert latest["bid_depth_ratio"] is None
    assert latest["microstructure_source"] == "not_available"
    assert latest["funding_zscore"] is None
    assert latest["funding_source"] == "not_available"


def test_snapshot_export_rejects_invalid_max_bars(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_bars"):
        build_regime_snapshots(_bars(), data_root=tmp_path, max_bars=0)
