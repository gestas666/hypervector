"""Multi-Model LightGBM + HistGradientBoosting Ensemble Metalabeler.

Combines gradient boosted models with probability calibration and dynamic position sizing.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.isotonic import IsotonicRegression

    HAVE_ML = True
except ImportError:
    HAVE_ML = False


class EnsembleMetalabeler:
    """Ensemble metalabel model combining LightGBM + HistGBM with probability calibration."""

    def __init__(self, feature_names: list[str]) -> None:
        self.feature_names = list(feature_names)
        self._lgb_booster: Any = None
        self._hgb_model: Any = None
        self._calibrator: Any = None
        self.is_fitted: bool = False

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> EnsembleMetalabeler:
        """Fit ensemble model on feature matrix X and target labels y."""
        if not HAVE_ML:
            raise RuntimeError(
                "lightgbm and scikit-learn are required for EnsembleMetalabeler"
            )

        X_mat = X[self.feature_names].astype(float).to_numpy()
        y_arr = np.asarray(y, dtype=int)

        if len(np.unique(y_arr)) < 2:
            raise ValueError(
                "Training labels y must contain at least two classes (0 and 1)"
            )

        # 1. Train LightGBM Booster
        dtrain = lgb.Dataset(X_mat, label=y_arr)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.03,
            "num_leaves": 15,
            "max_depth": 4,
            "min_child_samples": 10,
            "feature_fraction": 0.8,
            "verbose": -1,
        }
        self._lgb_booster = lgb.train(params, dtrain, num_boost_round=100)

        # 2. Train HistGradientBoosting
        self._hgb_model = HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.03,
            max_leaf_nodes=15,
            max_depth=4,
            min_samples_leaf=10,
            random_state=42,
        )
        self._hgb_model.fit(X_mat, y_arr)

        # 3. Fit Calibrator on ensemble probabilities
        p_lgb = self._lgb_booster.predict(X_mat)
        p_hgb = self._hgb_model.predict_proba(X_mat)[:, 1]
        p_ens = 0.5 * p_lgb + 0.5 * p_hgb

        self._calibrator = IsotonicRegression(out_of_bounds="clip")
        self._calibrator.fit(p_ens, y_arr)
        self.is_fitted = True
        return self

    def predict_probability(self, features: pd.DataFrame | dict[str, Any]) -> float:
        """Predict calibrated probability p in [0, 1] for one feature row or DataFrame."""
        if not self.is_fitted:
            return 0.5

        if isinstance(features, dict):
            row = [float(features.get(n, 0.0)) for n in self.feature_names]
            X_mat = np.asarray([row], dtype=float)
        elif isinstance(features, pd.DataFrame):
            X_mat = features[self.feature_names].astype(float).to_numpy()
        else:
            raise TypeError("features must be dict or DataFrame")

        p_lgb = self._lgb_booster.predict(X_mat)
        p_hgb = self._hgb_model.predict_proba(X_mat)[:, 1]
        p_raw = 0.5 * p_lgb + 0.5 * p_hgb

        if self._calibrator is not None:
            p_cal = self._calibrator.predict(p_raw)
        else:
            p_cal = p_raw

        return float(np.clip(p_cal[0] if len(p_cal) == 1 else p_cal.mean(), 0.0, 1.0))

    def compute_conviction_size_multiplier(
        self,
        features: pd.DataFrame | dict[str, Any],
        min_p: float = 0.50,
        scaling_exponent: float = 2.0,
    ) -> float:
        """Calculate dynamic conviction sizing multiplier in [0.0, 3.0].

        Returns 0.0 if p < min_p (filtered).
        Expands quadratically for p > min_p.
        """
        p = self.predict_probability(features)
        if p < min_p:
            return 0.0

        # Quadratic scaling above min_p threshold
        excess = (p - min_p) / max(1.0 - min_p, 1e-4)
        mult = 1.0 + 2.0 * math.pow(excess, scaling_exponent)
        return float(np.clip(mult, 0.0, 3.0))
