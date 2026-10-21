"""Phase-2 export bundle schema (SRS_HV1_EXPORT_FS)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.export.phase2 import export_candidate
from hypervector.regime.detectors import detect_regime_ema


def test_export_bundle_minimum_artifacts(tmp_path: Path):
    df = fixture_ohlcv(n_bars=50, drift=2.0)
    labels = detect_regime_ema(df["close"], fast=5, slow=15)
    signals = pd.DataFrame(
        {"entries": [False] * len(df), "exits": [False] * len(df)},
        index=df.index,
    )
    out = export_candidate(
        tmp_path / "exports",
        run_id="runabc",
        meta={
            "symbol": "BTC",
            "timeframe": "1m",
            "lookback_days": 90,
            "fee_model": "hl_taker_default",
            "data_provenance": {"sources": {"fixture": 50}},
        },
        params={"strategy": "test_sma_cross_long", "role": "uptrend", "fast": 5, "slow": 20},
        metrics={
            "net_pnl": 12.5,
            "total_return_pct": 1.25,
            "sharpe": 0.8,
            "trade_count": 3,
            "wins": 2,
            "losses": 1,
            "win_pct": 66.7,
            "max_drawdown": -0.02,
        },
        signals=signals,
        regime_labels=labels,
        candidate_id="cand1",
    )
    assert out.is_dir()
    assert (out / "meta.json").is_file()
    assert (out / "params.json").is_file()
    assert (out / "metrics.json").is_file()
    assert (out / "metrics.csv").is_file()
    assert (out / "signals.parquet").is_file()
    assert (out / "regime_labels.parquet").is_file()

    meta = json.loads((out / "meta.json").read_text())
    assert meta["run_id"] == "runabc"
    assert meta["symbol"] == "BTC"
    assert "package_version" in meta
    assert meta["schema_version"] == "1"
    assert meta["strategy"] == "test_sma_cross_long"

    params = json.loads((out / "params.json").read_text())
    assert params["strategy"] == "test_sma_cross_long"

    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["net_pnl"] == 12.5
    assert "sharpe" in metrics


def test_export_without_optional_series(tmp_path: Path):
    out = export_candidate(
        tmp_path / "exports",
        run_id="r2",
        meta={"symbol": "BTC", "timeframe": "1m"},
        params={"strategy": "x"},
        metrics={"net_pnl": 0.0, "total_return_pct": 0.0},
        candidate_id="minimal",
    )
    assert (out / "meta.json").is_file()
    assert not (out / "signals.parquet").exists()
    assert not (out / "regime_labels.parquet").exists()
    meta = json.loads((out / "meta.json").read_text())
    assert meta["schema_version"] == "1"
    assert meta["strategy"] == "x"
