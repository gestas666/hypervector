"""Optional BTC 1m impulse metalabel conviction façade (inference only).

Loads external LightGBM + optional calibrator bundles from known local paths
or ``HYPERVECTOR_IMPULSE_BTC_ROOT``. Does not train or ship model weights.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ENV_ROOT = "HYPERVECTOR_IMPULSE_BTC_ROOT"

# Preferred defaults — models stay outside this repo.
_DEFAULT_HYPER_PI = Path(
    "/Users/gestas/dev/hyper-pi/services/ml-service/"
    "external-strategies/impulse_1m_btc"
)
_DEFAULT_HYPERTRADER = Path(
    "/Users/gestas/Prototypes/hypertrader/backend/app/backtest/"
    "impulse_metalabel/models"
)

_MODEL_NAME = "metalabel_lgbm.txt"
_CALIBRATOR_NAME = "metalabel_calibrator.joblib"
_METADATA_NAME = "metalabel_metadata.json"


class ImpulseBundleError(RuntimeError):
    """Model bundle missing, unloadable, or features incomplete."""


def _is_usable_model_file(path: Path) -> bool:
    """True if path looks like a real LightGBM model (not missing / LFS pointer)."""
    if not path.is_file():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < 256:
        return False
    # Git LFS pointer files start with this header and are tiny (~100–200 B).
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:80]
    except OSError:
        return False
    if head.startswith("version https://git-lfs.github.com"):
        return False
    return True


def _normalize_bundle_root(candidate: Path) -> Path | None:
    """Return directory containing metalabel_lgbm.txt, or None."""
    candidate = candidate.expanduser()
    if _is_usable_model_file(candidate / _MODEL_NAME):
        return candidate.resolve()
    nested = candidate / "models"
    if _is_usable_model_file(nested / _MODEL_NAME):
        return nested.resolve()
    return None


def resolve_impulse_btc_root(env: Mapping[str, str] | None = None) -> Path:
    """Resolve metalabel bundle directory from env or known defaults.

    Order:
      1. ``HYPERVECTOR_IMPULSE_BTC_ROOT`` (dir or parent of ``models/``)
      2. hyper-pi ``impulse_1m_btc`` (uses ``models/`` when present)
      3. hypertrader ``impulse_metalabel/models``
    """
    environ = env if env is not None else os.environ
    raw = environ.get(ENV_ROOT)
    if raw:
        root = _normalize_bundle_root(Path(raw))
        if root is not None:
            return root
        # Explicit override that is unusable still surfaces as that path for errors.
        p = Path(raw).expanduser()
        if (p / "models").is_dir():
            return (p / "models").resolve()
        return p.resolve()

    for candidate in (_DEFAULT_HYPER_PI, _DEFAULT_HYPERTRADER):
        root = _normalize_bundle_root(candidate)
        if root is not None:
            return root

    raise ImpulseBundleError(
        "impulse BTC metalabel bundle not found: set "
        f"{ENV_ROOT} or install models under {_DEFAULT_HYPER_PI / 'models'} "
        f"or {_DEFAULT_HYPERTRADER}"
    )


def _load_booster(model_path: Path) -> Any:
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImpulseBundleError(
            "lightgbm is required to load impulse metalabel models "
            "(install with: uv add lightgbm / pip install lightgbm)"
        ) from exc
    if not model_path.is_file():
        raise ImpulseBundleError(
            f"metalabel model missing or unloadable: {model_path}"
        )
    # Reject obvious git-lfs pointer stubs early (clearer than LightGBM parse error).
    try:
        head = model_path.read_text(encoding="utf-8", errors="ignore")[:80]
        if head.startswith("version https://git-lfs.github.com"):
            raise ImpulseBundleError(
                f"metalabel model is a git-lfs pointer (not fetched): {model_path}"
            )
    except ImpulseBundleError:
        raise
    except OSError:
        pass
    try:
        return lgb.Booster(model_file=str(model_path))
    except Exception as exc:  # Booster raises various OSError/LightGBMError
        raise ImpulseBundleError(
            f"failed to load LightGBM metalabel model from {model_path}: {exc}"
        ) from exc


def _load_calibrator(cal_path: Path) -> Any | None:
    if not cal_path.is_file():
        return None
    try:
        import joblib
    except ImportError as exc:
        raise ImpulseBundleError(
            "joblib is required to load metalabel calibrator"
        ) from exc
    try:
        return joblib.load(cal_path)
    except Exception as exc:
        raise ImpulseBundleError(
            f"failed to load calibrator from {cal_path}: {exc}"
        ) from exc


def _load_feature_names(root: Path, booster: Any) -> list[str]:
    meta_path = root / _METADATA_NAME
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImpulseBundleError(
                f"failed to read {_METADATA_NAME} at {meta_path}: {exc}"
            ) from exc
        names = meta.get("feature_names")
        if isinstance(names, list) and names and all(isinstance(n, str) for n in names):
            return list(names)
    # Fallback: LightGBM feature names if metadata absent.
    try:
        fn = list(booster.feature_name())
        if fn and fn != [f"Column_{i}" for i in range(len(fn))]:
            return fn
    except Exception:
        pass
    raise ImpulseBundleError(
        f"feature_names unavailable: provide {_METADATA_NAME} with feature_names "
        f"in {root}"
    )


class ImpulseBtcFacade:
    """Inference-only façade over BTC 1m impulse metalabel LightGBM + calibrator."""

    def __init__(
        self,
        root: Path,
        booster: Any,
        calibrator: Any | None,
        feature_names: list[str],
    ) -> None:
        self.root = Path(root)
        self._booster = booster
        self._calibrator = calibrator
        self.feature_names = list(feature_names)

    @classmethod
    def from_root(cls, root: Path | str) -> ImpulseBtcFacade:
        """Load booster (+ optional calibrator/metadata) from a bundle directory."""
        path = Path(root).expanduser().resolve()
        model_path = path / _MODEL_NAME
        if not model_path.is_file() and (path / "models" / _MODEL_NAME).is_file():
            path = (path / "models").resolve()
            model_path = path / _MODEL_NAME
        if not model_path.is_file():
            raise ImpulseBundleError(f"metalabel_lgbm.txt missing under {path}")

        booster = _load_booster(model_path)
        calibrator = _load_calibrator(path / _CALIBRATOR_NAME)
        feature_names = _load_feature_names(path, booster)
        return cls(
            root=path,
            booster=booster,
            calibrator=calibrator,
            feature_names=feature_names,
        )

    @classmethod
    def from_env(cls) -> ImpulseBtcFacade:
        """Resolve root via env/defaults and load the bundle."""
        root = resolve_impulse_btc_root()
        model_path = root / _MODEL_NAME
        if not model_path.is_file():
            raise ImpulseBundleError(
                f"impulse BTC metalabel bundle missing metalabel_lgbm.txt at {root}"
            )
        # Explicit env roots may point at test fixtures; content validation
        # is deferred to _load_booster. Default discovery already filters LFS stubs.
        return cls.from_root(root)

    def _features_to_matrix(self, features: pd.DataFrame | Mapping[str, Any]) -> np.ndarray:
        if isinstance(features, pd.DataFrame):
            if features.empty:
                raise ImpulseBundleError("features DataFrame is empty")
            row = features.iloc[-1]
            missing = [n for n in self.feature_names if n not in row.index]
            if missing:
                raise ImpulseBundleError(
                    f"missing features for metalabel predict: {missing}"
                )
            values = [float(row[n]) for n in self.feature_names]
        elif isinstance(features, Mapping):
            missing = [n for n in self.feature_names if n not in features]
            if missing:
                raise ImpulseBundleError(
                    f"missing features for metalabel predict: {missing}"
                )
            values = [float(features[n]) for n in self.feature_names]
        else:
            raise ImpulseBundleError(
                "features must be a Mapping or pandas DataFrame"
            )
        return np.asarray([values], dtype=float)

    def predict_conviction(
        self, features: pd.DataFrame | Mapping[str, Any]
    ) -> float:
        """Predict metalabel probability in ``[0, 1]`` for one feature row."""
        X = self._features_to_matrix(features)
        try:
            raw = self._booster.predict(
                X, num_iteration=self._booster.best_iteration
            )[0]
            if self._calibrator is not None:
                p = float(self._calibrator.predict([raw])[0])
            else:
                p = float(raw)
        except ImpulseBundleError:
            raise
        except Exception as exc:
            raise ImpulseBundleError(f"metalabel predict failed: {exc}") from exc
        return float(np.clip(p, 0.0, 1.0))
