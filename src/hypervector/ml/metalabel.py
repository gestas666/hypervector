"""Reusable metalabel inference process (any asset / interval / bundle).

The process is fixed; **bundles** are versioned instances:

  features (schema from metadata)
    → LightGBM (+ optional calibrator)
    → probability p ∈ [0, 1]
    → caller maps p → skip floor / conviction / risk (policy elsewhere)

No training, no asset-specific classes. Point ``from_root`` / env at any
compatible bundle (impulse BTC 1m, ETH short, HAZEMA 15m, future crown
metalabel, …). Spin a new version by training a new bundle directory —
do not fork this module unless the *process* changes.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Primary env: any metalabel bundle root (dir with metalabel_lgbm.txt or models/).
ENV_ROOT = "HYPERVECTOR_METALABEL_ROOT"
# Legacy alias kept so existing shells keep working until callers migrate.
ENV_ROOT_LEGACY = "HYPERVECTOR_IMPULSE_BTC_ROOT"

# Project-local layout under --data-root (I2): data/models/metalabel/
REL_BUNDLE_UNDER_DATA = Path("models") / "metalabel"

# Discovery defaults only — not identity. Prefer env / data-root in production.
# Order after env + data_root: cwd data layout, then known sibling checkouts.
_DEFAULT_DISCOVERY: tuple[Path, ...] = (Path("data") / "models" / "metalabel",)

_MODEL_NAME = "metalabel_lgbm.txt"
_CALIBRATOR_NAME = "metalabel_calibrator.joblib"
_METADATA_NAME = "metalabel_metadata.json"


class MetalabelError(RuntimeError):
    """Bundle missing, unloadable, feature mismatch, or predict failure."""


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
    try:
        with path.open(encoding="utf-8", errors="ignore") as stream:
            head = stream.read(80)
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


def resolve_metalabel_root(
    env: Mapping[str, str] | None = None,
    *,
    data_root: Path | str | None = None,
) -> Path:
    """Resolve metalabel bundle directory from env, data root, or discovery.

    Order:
      1. ``HYPERVECTOR_METALABEL_ROOT``
      2. ``HYPERVECTOR_IMPULSE_BTC_ROOT`` (legacy)
      3. ``{data_root}/models/metalabel`` when ``data_root`` is set
      4. known local discovery paths (first usable real model file)
    """
    environ = env if env is not None else os.environ
    for key in (ENV_ROOT, ENV_ROOT_LEGACY):
        raw = environ.get(key)
        if not raw:
            continue
        root = _normalize_bundle_root(Path(raw))
        if root is not None:
            return root
        p = Path(raw).expanduser()
        if (p / "models").is_dir():
            return (p / "models").resolve()
        return p.resolve()

    if data_root is not None:
        under = _normalize_bundle_root(Path(data_root) / REL_BUNDLE_UNDER_DATA)
        if under is not None:
            return under
        raise MetalabelError(f"metalabel bundle not found under selected data root: {data_root}")

    for candidate in _DEFAULT_DISCOVERY:
        root = _normalize_bundle_root(candidate)
        if root is not None:
            return root

    raise MetalabelError(
        "metalabel bundle not found: set "
        f"{ENV_ROOT} (or legacy {ENV_ROOT_LEGACY}) to a directory containing "
        f"{_MODEL_NAME} (or place bundle at data/models/metalabel/)"
    )


def probe_metalabel(
    env: Mapping[str, str] | None = None,
    *,
    data_root: Path | str | None = None,
) -> dict[str, Any]:
    """Readiness probe for 'paper check' and status (no secret values).

    Does not enable metalabel; reports whether a bundle can load when
    ``paper run --metalabel-mode`` is used.
    """
    out: dict[str, Any] = {
        "env_root_set": bool((env if env is not None else os.environ).get(ENV_ROOT)),
        "legacy_env_set": bool(
            (env if env is not None else os.environ).get(ENV_ROOT_LEGACY)
        ),
        "bundle_resolved": False,
        "bundle_root": None,
        "model_present": False,
        "calibrator_present": False,
        "metadata_present": False,
        "loadable": False,
        "n_features": None,
        "error": None,
    }
    try:
        root = resolve_metalabel_root(env, data_root=data_root)
    except MetalabelError as exc:
        out["error"] = str(exc)
        return out

    out["bundle_resolved"] = True
    out["bundle_root"] = str(root)
    model_path = root / _MODEL_NAME
    out["model_present"] = _is_usable_model_file(model_path)
    out["calibrator_present"] = (root / _CALIBRATOR_NAME).is_file()
    out["metadata_present"] = (root / _METADATA_NAME).is_file()
    if not out["model_present"]:
        out["error"] = f"{_MODEL_NAME} missing or unloadable at {root}"
        return out
    try:
        ml = Metalabeler.from_root(root)
        out["loadable"] = True
        out["n_features"] = len(ml.feature_names)
    except MetalabelError as exc:
        out["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — probe must not raise
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _load_booster(model_path: Path) -> Any:
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise MetalabelError(
            "lightgbm is required to load metalabel models "
            "(install with: uv sync --extra ml / pip install lightgbm)"
        ) from exc
    if not model_path.is_file():
        raise MetalabelError(f"metalabel model missing or unloadable: {model_path}")
    try:
        head = model_path.read_text(encoding="utf-8", errors="ignore")[:80]
        if head.startswith("version https://git-lfs.github.com"):
            raise MetalabelError(
                f"metalabel model is a git-lfs pointer (not fetched): {model_path}"
            )
    except MetalabelError:
        raise
    except OSError:
        pass
    try:
        return lgb.Booster(model_file=str(model_path))
    except Exception as exc:
        raise MetalabelError(
            f"failed to load LightGBM metalabel model from {model_path}: {exc}"
        ) from exc


def _load_calibrator(cal_path: Path) -> Any | None:
    if not cal_path.is_file():
        return None
    try:
        import joblib
        from sklearn.exceptions import InconsistentVersionWarning
    except ImportError as exc:
        raise MetalabelError(
            "joblib and scikit-learn are required to load metalabel calibrator"
        ) from exc
    try:
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", InconsistentVersionWarning)
            calibrator = joblib.load(cal_path)
        mismatch = next(
            (
                warning
                for warning in caught
                if issubclass(warning.category, InconsistentVersionWarning)
            ),
            None,
        )
        if mismatch is not None:
            raise MetalabelError(
                "metalabel calibrator scikit-learn version mismatch: "
                f"{mismatch.message}; retrain the bundle in this runtime"
            )
        return calibrator
    except MetalabelError:
        raise
    except Exception as exc:
        raise MetalabelError(
            f"failed to load calibrator from {cal_path}: {exc}"
        ) from exc


def _load_feature_names(root: Path, booster: Any) -> list[str]:
    meta_path = root / _METADATA_NAME
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MetalabelError(
                f"failed to read {_METADATA_NAME} at {meta_path}: {exc}"
            ) from exc
        names = meta.get("feature_names")
        if isinstance(names, list) and names and all(isinstance(n, str) for n in names):
            return list(names)
    try:
        fn = list(booster.feature_name())
        if fn and fn != [f"Column_{i}" for i in range(len(fn))]:
            return fn
    except Exception:
        pass
    raise MetalabelError(
        f"feature_names unavailable: provide {_METADATA_NAME} with feature_names "
        f"in {root}"
    )


class Metalabeler:
    """Inference-only metalabel process over one bundle directory.

    Bundle layout (stable contract for any asset/interval version)::

        <root>/
          metalabel_lgbm.txt
          metalabel_calibrator.joblib   # optional
          metalabel_metadata.json       # feature_names required when booster
                                        # has no meaningful names
    """

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
    def from_root(cls, root: Path | str) -> Metalabeler:
        """Load booster (+ optional calibrator/metadata) from a bundle directory."""
        path = Path(root).expanduser().resolve()
        model_path = path / _MODEL_NAME
        if not model_path.is_file() and (path / "models" / _MODEL_NAME).is_file():
            path = (path / "models").resolve()
            model_path = path / _MODEL_NAME
        if not model_path.is_file():
            raise MetalabelError(f"{_MODEL_NAME} missing under {path}")

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
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        data_root: Path | str | None = None,
    ) -> Metalabeler:
        """Resolve root via env / data_root / discovery and load the bundle."""
        root = resolve_metalabel_root(env, data_root=data_root)
        model_path = root / _MODEL_NAME
        if not model_path.is_file():
            raise MetalabelError(f"metalabel bundle missing {_MODEL_NAME} at {root}")
        return cls.from_root(root)

    def _features_to_matrix(
        self, features: pd.DataFrame | Mapping[str, Any]
    ) -> np.ndarray:
        if isinstance(features, pd.DataFrame):
            if features.empty:
                raise MetalabelError("features DataFrame is empty")
            row = features.iloc[-1]
            missing = [n for n in self.feature_names if n not in row.index]
            if missing:
                raise MetalabelError(
                    f"missing features for metalabel predict: {missing}"
                )
            values = [float(row[n]) for n in self.feature_names]
        elif isinstance(features, Mapping):
            missing = [n for n in self.feature_names if n not in features]
            if missing:
                raise MetalabelError(
                    f"missing features for metalabel predict: {missing}"
                )
            values = [float(features[n]) for n in self.feature_names]
        else:
            raise MetalabelError("features must be a Mapping or pandas DataFrame")
        return np.asarray([values], dtype=float)

    def predict_probability(self, features: pd.DataFrame | Mapping[str, Any]) -> float:
        """Calibrated metalabel probability in ``[0, 1]`` for one feature row."""
        X = self._features_to_matrix(features)
        try:
            raw = self._booster.predict(X, num_iteration=self._booster.best_iteration)[
                0
            ]
            if self._calibrator is not None:
                p = float(self._calibrator.predict([raw])[0])
            else:
                p = float(raw)
        except MetalabelError:
            raise
        except Exception as exc:
            raise MetalabelError(f"metalabel predict failed: {exc}") from exc
        return float(np.clip(p, 0.0, 1.0))

    def predict_conviction(self, features: pd.DataFrame | Mapping[str, Any]) -> float:
        """Alias of :meth:`predict_probability` for hypervector risk sizing."""
        return self.predict_probability(features)
