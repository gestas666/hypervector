"""Deterministic JSON Ridge bundle for report-only HYPE L2 scoring."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math
from typing import Mapping, cast

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES

_RIDGE_ALPHA = 10.0
_BUNDLE_MODE = "hype_l2_ridge_observe_bundle_v1"
_EVIDENCE_KEYS = (
    "development_report_sha256",
    "feature_artifact_sha256",
    "model_plan_sha256",
)


@dataclass(frozen=True)
class HypeL2RidgeBundle:
    """Frozen scaler and Ridge coefficients with no execution authority."""

    feature_names: tuple[str, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training_scores_sorted: tuple[float, ...]
    training_rows: int
    training_start_utc: str
    training_end_utc: str
    evidence: tuple[tuple[str, str], ...]
    alpha: float = _RIDGE_ALPHA

    def __post_init__(self) -> None:
        """Validate exact dimensions, identities, and finite parameters."""
        if self.feature_names != HYPE_ENTRY_L2_FEATURES:
            raise ValueError("HYPE L2 bundle feature identity differs from frozen set")
        dimensions = (
            len(self.scaler_mean),
            len(self.scaler_scale),
            len(self.coefficients),
        )
        if set(dimensions) != {len(self.feature_names)}:
            raise ValueError("HYPE L2 bundle parameter dimensions do not match")
        numeric = (
            *self.scaler_mean,
            *self.scaler_scale,
            *self.coefficients,
            self.intercept,
            *self.training_scores_sorted,
        )
        if not numeric or not all(math.isfinite(value) for value in numeric):
            raise ValueError("HYPE L2 bundle parameters must be finite")
        if min(self.scaler_scale) <= 0.0 or self.alpha != _RIDGE_ALPHA:
            raise ValueError("HYPE L2 bundle scaler or alpha is invalid")
        if self.training_rows != len(self.training_scores_sorted):
            raise ValueError("HYPE L2 bundle training score count differs from rows")
        if tuple(sorted(self.training_scores_sorted)) != self.training_scores_sorted:
            raise ValueError("HYPE L2 bundle training scores must be sorted")
        _validate_evidence(dict(self.evidence))

    @property
    def execution_authority(self) -> str:
        """Return the immutable no-submit authority contract."""
        return "none"

    def score(self, features: Mapping[str, object]) -> float:
        """Score one exact, finite feature mapping without imputation."""
        values = _feature_vector(features, self.feature_names)
        standardized = (
            (value - mean) / scale
            for value, mean, scale in zip(
                values,
                self.scaler_mean,
                self.scaler_scale,
                strict=True,
            )
        )
        return self.intercept + sum(
            value * coefficient
            for value, coefficient in zip(
                standardized,
                self.coefficients,
                strict=True,
            )
        )

    def score_percentile(self, features: Mapping[str, object]) -> float:
        """Locate one score in the full-fit training score distribution."""
        score = self.score(features)
        return bisect_right(self.training_scores_sorted, score) / self.training_rows

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic, pickle-free bundle representation."""
        return {
            "schema_version": 1,
            "mode": _BUNDLE_MODE,
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "runtime_strategy_changed": False,
                "automatic_promotion": False,
            },
            "model": {
                "family": "standard_scaler_ridge_regression",
                "alpha": self.alpha,
                "feature_names": list(self.feature_names),
                "scaler_mean": list(self.scaler_mean),
                "scaler_scale": list(self.scaler_scale),
                "coefficients": list(self.coefficients),
                "intercept": self.intercept,
            },
            "training": {
                "rows": self.training_rows,
                "start_utc": self.training_start_utc,
                "end_utc": self.training_end_utc,
                "target": "gross_return_bps",
                "scores_sorted": list(self.training_scores_sorted),
            },
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_payload(cls, value: object) -> HypeL2RidgeBundle:
        """Validate and load one deterministic JSON bundle payload."""
        root = _mapping(value, "bundle")
        if root.get("schema_version") != 1 or root.get("mode") != _BUNDLE_MODE:
            raise ValueError("HYPE L2 bundle schema or mode is unsupported")
        _validate_contract(_mapping(root.get("contract"), "contract"))
        model = _mapping(root.get("model"), "model")
        training = _mapping(root.get("training"), "training")
        if model.get("family") != "standard_scaler_ridge_regression":
            raise ValueError("HYPE L2 bundle model family is unsupported")
        if training.get("target") != "gross_return_bps":
            raise ValueError("HYPE L2 bundle training target is unsupported")
        return cls(
            feature_names=_texts(model.get("feature_names"), "feature_names"),
            scaler_mean=_numbers(model.get("scaler_mean"), "scaler_mean"),
            scaler_scale=_numbers(model.get("scaler_scale"), "scaler_scale"),
            coefficients=_numbers(model.get("coefficients"), "coefficients"),
            intercept=_number(model.get("intercept"), "intercept"),
            training_scores_sorted=_numbers(
                training.get("scores_sorted"), "scores_sorted"
            ),
            training_rows=_integer(training.get("rows"), "rows"),
            training_start_utc=_text(training.get("start_utc"), "start_utc"),
            training_end_utc=_text(training.get("end_utc"), "end_utc"),
            evidence=tuple(sorted(_string_mapping(root.get("evidence")).items())),
            alpha=_number(model.get("alpha"), "alpha"),
        )


def fit_hype_l2_ridge_bundle(
    rows: pd.DataFrame,
    *,
    evidence: Mapping[str, str],
) -> HypeL2RidgeBundle:
    """Fit the fixed final observer bundle on all frozen development rows."""
    _validate_training_rows(rows)
    _validate_evidence(evidence)
    features = rows.loc[:, HYPE_ENTRY_L2_FEATURES].astype(float)
    target = rows["gross_return_bps"].to_numpy(dtype=float)
    scaler = StandardScaler().fit(features)
    standardized = scaler.transform(features)
    model = Ridge(alpha=_RIDGE_ALPHA).fit(standardized, target)
    predictions = np.asarray(model.predict(standardized), dtype=float)
    timestamps = pd.to_datetime(rows["signal_time_utc"], utc=True, errors="raise")
    return HypeL2RidgeBundle(
        feature_names=HYPE_ENTRY_L2_FEATURES,
        scaler_mean=tuple(float(value) for value in scaler.mean_),
        scaler_scale=tuple(float(value) for value in scaler.scale_),
        coefficients=tuple(float(value) for value in model.coef_),
        intercept=float(model.intercept_),
        training_scores_sorted=tuple(float(value) for value in np.sort(predictions)),
        training_rows=len(rows),
        training_start_utc=timestamps.iloc[0].isoformat(),
        training_end_utc=timestamps.iloc[-1].isoformat(),
        evidence=tuple(sorted(evidence.items())),
    )


def _validate_training_rows(rows: pd.DataFrame) -> None:
    required = {*HYPE_ENTRY_L2_FEATURES, "gross_return_bps", "signal_time_utc"}
    missing = sorted(required.difference(rows.columns))
    if missing or rows.empty:
        raise ValueError(f"HYPE L2 bundle training rows are invalid: missing={missing}")
    numeric = rows.loc[:, [*HYPE_ENTRY_L2_FEATURES, "gross_return_bps"]].astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise ValueError("HYPE L2 bundle training values must be finite")
    timestamps = pd.to_datetime(rows["signal_time_utc"], utc=True, errors="raise")
    if not timestamps.is_monotonic_increasing or not timestamps.is_unique:
        raise ValueError(
            "HYPE L2 bundle training timestamps must be ordered and unique"
        )


def _feature_vector(
    features: Mapping[str, object], names: tuple[str, ...]
) -> tuple[float, ...]:
    if set(features) != set(names) or len(features) != len(names):
        raise ValueError("HYPE L2 live features must exactly match the bundle")
    values = tuple(_number(features[name], name) for name in names)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("HYPE L2 live features must be finite")
    return values


def _validate_evidence(evidence: Mapping[str, str]) -> None:
    if set(evidence) != set(_EVIDENCE_KEYS):
        raise ValueError("HYPE L2 bundle evidence keys differ from frozen contract")
    if not all(len(value) == 64 and _is_hex(value) for value in evidence.values()):
        raise ValueError("HYPE L2 bundle evidence hashes must be SHA-256 values")


def _validate_contract(value: Mapping[str, object]) -> None:
    expected = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_promotion": False,
    }
    if dict(value) != expected:
        raise ValueError("HYPE L2 bundle authority contract is invalid")


def _is_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HYPE L2 bundle {label} must be an object")
    return cast(dict[str, object], value)


def _string_mapping(value: object) -> dict[str, str]:
    mapping = _mapping(value, "evidence")
    if not all(isinstance(item, str) for item in mapping.values()):
        raise ValueError("HYPE L2 bundle evidence values must be strings")
    return {key: cast(str, item) for key, item in mapping.items()}


def _numbers(value: object, label: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"HYPE L2 bundle {label} must be a non-empty list")
    return tuple(_number(item, label) for item in value)


def _texts(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"HYPE L2 bundle {label} must be a non-empty list")
    return tuple(_text(item, label) for item in value)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"HYPE L2 bundle {label} must be numeric")
    return float(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"HYPE L2 bundle {label} must be an integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"HYPE L2 bundle {label} must be text")
    return value
