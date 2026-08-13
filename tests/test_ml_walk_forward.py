"""Walk-forward metalabel labeling + purged windows (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn

from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.ml.labels import build_strategy_labels, resolve_barrier_outcome
from hypervector.ml.purged_cv import purged_kfold_split, walk_forward_windows
from hypervector.sweep.exits import ExitConfig


def _synth_ohlcv(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 50_000 + np.cumsum(rng.normal(0, 20, size=n))
    high = close + rng.uniform(5, 40, size=n)
    low = close - rng.uniform(5, 40, size=n)
    open_ = close + rng.normal(0, 10, size=n)
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(1, 10, size=n),
        }
    )


def test_feature_matrix_has_stable_schema():
    df = _synth_ohlcv(200)
    feats = build_feature_matrix(df)
    assert list(feats.columns) == FEATURE_NAMES
    assert len(feats) == len(df)
    assert feats.iloc[-1].notna().all()


def test_barrier_tp_long():
    high = np.array([100.0, 101.0, 103.0])
    low = np.array([99.0, 100.0, 101.0])
    close = np.array([100.0, 101.0, 102.0])
    idx, reason, _ = resolve_barrier_outcome(
        high=high,
        low=low,
        close=close,
        entry_idx=0,
        entry_price=100.0,
        sl_frac=0.05,
        tp_frac=0.02,
        direction="long",
        max_hold=5,
    )
    assert reason == "tp"
    assert idx == 2


def test_barrier_sl_long():
    high = np.array([100.0, 100.5, 99.0])
    low = np.array([99.0, 98.0, 97.0])
    close = np.array([100.0, 99.0, 98.0])
    idx, reason, _ = resolve_barrier_outcome(
        high=high,
        low=low,
        close=close,
        entry_idx=0,
        entry_price=100.0,
        sl_frac=0.015,
        tp_frac=0.05,
        direction="long",
        max_hold=5,
    )
    assert reason == "sl"
    assert idx >= 1


def test_build_strategy_labels_produces_rows():
    df = _synth_ohlcv(400)
    # Force sparse entries every 40 bars after warm-up
    entries = pd.Series(False, index=df.index)
    entries.iloc[50:350:40] = True
    labels = build_strategy_labels(
        df,
        entries,
        direction="long",
        exit_cfg=ExitConfig(mode="atr", sl_atr_mult=1.5, rr=2.0),
        max_hold_bars=30,
    )
    assert len(labels) >= 5
    assert set(FEATURE_NAMES).issubset(labels.columns)
    assert labels["label"].isin([0, 1]).all()


def test_purged_kfold_and_wf_windows():
    n = 100
    entry = np.arange(n, dtype=np.int64) * 60_000
    outcome = entry + 10 * 60_000
    folds = list(purged_kfold_split(entry, outcome, n_splits=4, embargo_minutes=30))
    assert len(folds) >= 2
    for tr, te in folds:
        assert len(tr) > 0 and len(te) > 0
        assert len(set(tr) & set(te)) == 0

    windows = walk_forward_windows(
        entry,
        train_ms=40 * 60_000,
        test_ms=15 * 60_000,
        step_ms=15 * 60_000,
        min_train_samples=10,
        min_test_samples=5,
    )
    assert len(windows) >= 1


def test_train_bundle_smoke(tmp_path: Path):
    lightgbm = pytest.importorskip("lightgbm")
    _ = lightgbm
    from hypervector.ml.train_bundle import train_metalabel_bundle

    df = _synth_ohlcv(600, seed=1)
    entries = pd.Series(False, index=df.index)
    entries.iloc[60:550:15] = True
    labels = build_strategy_labels(
        df,
        entries,
        direction="long",
        exit_cfg=ExitConfig(mode="fixed_rr", sl_pct=0.01, rr=2.0),
        max_hold_bars=40,
    )
    # ensure both classes for training
    if labels["label"].nunique() < 2:
        labels = labels.copy()
        labels.loc[labels.index[: max(3, len(labels) // 4)], "label"] = 1
        labels.loc[labels.index[max(3, len(labels) // 4) :], "label"] = 0

    res = train_metalabel_bundle(
        labels,
        tmp_path / "bundle",
        n_splits=3,
        embargo_minutes=5,
        num_boost_round=20,
    )
    assert res.model_path.is_file()
    assert res.metadata_path.is_file()
    assert res.n_samples == len(labels)
    metadata = json.loads(res.metadata_path.read_text(encoding="utf-8"))
    assert metadata["training_versions"] == {
        "joblib": joblib.__version__,
        "lightgbm": lightgbm.__version__,
        "scikit_learn": sklearn.__version__,
    }
    assert metadata["cv"]["lgbm_auc_mean"] is None
