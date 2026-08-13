"""Deterministic report-only HYPE L2 Ridge bundle tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hypervector.ml.hype_l2_ridge_bundle import (
    HypeL2RidgeBundle,
    fit_hype_l2_ridge_bundle,
)
from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES


def test_bundle_score_matches_frozen_sklearn_pipeline() -> None:
    """Serialized arithmetic must exactly preserve the fitted Ridge score."""
    rows = _rows(40)
    bundle = fit_hype_l2_ridge_bundle(rows, evidence=_evidence())
    pipeline = Pipeline(
        [("scale", StandardScaler()), ("model", Ridge(alpha=10.0))]
    ).fit(rows.loc[:, HYPE_ENTRY_L2_FEATURES], rows["gross_return_bps"])
    features = rows.iloc[7].loc[list(HYPE_ENTRY_L2_FEATURES)].to_dict()

    expected = float(
        pipeline.predict(pd.DataFrame([features], columns=HYPE_ENTRY_L2_FEATURES))[0]
    )

    assert bundle.score(features) == pytest.approx(expected, abs=1e-10)
    assert 0.0 <= bundle.score_percentile(features) <= 1.0
    assert bundle.execution_authority == "none"


def test_bundle_payload_round_trip_is_deterministic(tmp_path: Path) -> None:
    """A frozen payload cannot depend on wall-clock or pickle implementation state."""
    bundle = fit_hype_l2_ridge_bundle(_rows(40), evidence=_evidence())
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle.to_payload(), sort_keys=True), encoding="utf-8")

    loaded = HypeL2RidgeBundle.from_payload(json.loads(path.read_text()))

    assert loaded == bundle
    assert loaded.to_payload() == bundle.to_payload()


def test_bundle_rejects_missing_or_nonfinite_live_features() -> None:
    """Runtime scoring must fail closed rather than impute model inputs."""
    bundle = fit_hype_l2_ridge_bundle(_rows(40), evidence=_evidence())
    features = _rows(1).iloc[0].loc[list(HYPE_ENTRY_L2_FEATURES)].to_dict()
    features.pop(HYPE_ENTRY_L2_FEATURES[0])
    with pytest.raises(ValueError, match="exactly match"):
        bundle.score(features)
    features[HYPE_ENTRY_L2_FEATURES[0]] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        bundle.score(features)


def _rows(count: int) -> pd.DataFrame:
    index = np.arange(count, dtype=float)
    values = {
        name: np.sin(index / (position + 2.0)) + position / 10.0
        for position, name in enumerate(HYPE_ENTRY_L2_FEATURES)
    }
    values["gross_return_bps"] = index * 0.7 - 12.0
    values["signal_time_utc"] = pd.date_range(
        "2026-01-01", periods=count, freq="5min", tz="UTC"
    )
    return pd.DataFrame(values)


def _evidence() -> dict[str, str]:
    return {
        "feature_artifact_sha256": "a" * 64,
        "model_plan_sha256": "b" * 64,
        "development_report_sha256": "c" * 64,
    }
