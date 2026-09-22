"""Offline purged comparison of frozen continuation models for all eight assets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from hypervector.research.v91_exit_continuation import (
    FEATURE_NAMES, continuation_dataset, purged_folds,
)

SYMBOLS = ("BTC", "ETH", "SOL", "HYPE", "xyz:SPCX", "xyz:SNDK", "xyz:BRENTOIL", "xyz:TSLA")


def _diagnostics(predicted: np.ndarray, actual: pd.Series) -> dict[str, float | None]:
    association = (pd.Series(predicted, index=actual.index).corr(actual, method="spearman")
                   if np.ptp(predicted) > 0 and actual.nunique() > 1 else float("nan"))
    return {"mae_bps": float(np.abs(actual.to_numpy() - predicted).mean()),
            "spearman": float(association) if np.isfinite(association) else None,
            "sign_accuracy": float(np.mean(np.sign(predicted) == np.sign(actual.to_numpy())))}


def evaluate(samples: pd.DataFrame) -> list[dict[str, object]]:
    """Fit within each train split and report every held-out model result."""
    reports: list[dict[str, object]] = []
    for number, (train_index, test_index) in enumerate(purged_folds(samples), 1):
        train, test = samples.loc[train_index], samples.loc[test_index]
        scaler = StandardScaler().fit(train.loc[:, FEATURE_NAMES])
        x_train, x_test = scaler.transform(train.loc[:, FEATURE_NAMES]), scaler.transform(test.loc[:, FEATURE_NAMES])
        ridge = Ridge(alpha=10.0).fit(x_train, train.label_bps)
        boosted = HistGradientBoostingRegressor(max_iter=100, max_depth=2, learning_rate=.05,
                                               early_stopping=False, random_state=0).fit(x_train, train.label_bps)
        predictions = {"zero": np.zeros(len(test)),
                       "train_mean": np.full(len(test), train.label_bps.mean()),
                       "ridge": ridge.predict(x_test), "boosted": boosted.predict(x_test)}
        reports.append({"fold": number, "train_rows": len(train), "test_rows": len(test),
                        "train_last_label_end": str(train.label_end.max()),
                        "test_first_decision": str(test.decision_time.min()),
                        "test_last_decision": str(test.decision_time.max()),
                        "nonoverlapping_test_labels_upper_bound": len(test) // 2,
                        "models": {name: _diagnostics(values, test.label_bps) for name, values in predictions.items()}})
    return reports


def ridge_bundle(samples: pd.DataFrame, source: Path, symbol: str) -> dict[str, object]:
    """Serialize a report-only final Ridge without executable pickle payloads."""
    features = samples.loc[:, FEATURE_NAMES]
    scaler = StandardScaler().fit(features)
    model = Ridge(alpha=10.0).fit(scaler.transform(features), samples.label_bps)
    return {"symbol": symbol, "features": list(FEATURE_NAMES), "alpha": 10.0,
            "means": scaler.mean_.tolist(), "scales": scaler.scale_.tolist(),
            "coefficients": model.coef_.tolist(), "intercept": float(model.intercept_),
            "training_rows": len(samples), "training_start": str(samples.decision_time.min()),
            "training_end": str(samples.label_end.max()),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def main() -> int:
    """Run only local candle research and write auditable metrics and model data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reports, models = {}, {}
    for symbol in SYMBOLS:
        filename = symbol.replace(":", "_")
        source = args.inputs / "inputs_15m_stitched" / filename / "bars.parquet"
        if not source.exists():
            source = args.inputs / "inputs_15m" / filename / "bars.parquet"
        bars = pd.read_parquet(source)
        samples = continuation_dataset(bars)
        reports[symbol] = {"raw_rows": len(bars), "usable_rows": len(samples),
                           "source": str(source), "folds": evaluate(samples)}
        models[symbol] = ridge_bundle(samples, source, symbol)
        print(json.dumps({"symbol": symbol, "usable_rows": len(samples), "folds": 3}), flush=True)
    common = {"schema_version": 1, "model_id": "v91_exit_continuation_ridge_v1",
              "execution_authority": "none", "bar_minutes": 15, "horizon_minutes": 30,
              "trial_family_count": 1, "trained_model_types": ["ridge", "boosted"],
              "limitations": ["generic continuation labels, not strategy-conditioned trade exits",
                              "historical candles already used in other strategy research",
                              "no historical L2 or oracle features; no realized trading-return claim"]}
    (args.output / "ml_comparison.json").write_text(json.dumps({**common, "results": reports}, indent=2, allow_nan=False) + "\n")
    (args.output / "continuation_models.json").write_text(json.dumps({**common, "models": models}, indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
