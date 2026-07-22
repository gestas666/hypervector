"""Unit tests for reusable metalabel inference process."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.metalabel import (
    ENV_ROOT,
    Metalabeler,
    MetalabelError,
    resolve_metalabel_root,
)


def test_resolve_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("tree", encoding="utf-8")
    monkeypatch.setenv(ENV_ROOT, str(root))
    assert resolve_metalabel_root() == root.resolve()


def test_resolve_accepts_legacy_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("tree", encoding="utf-8")
    monkeypatch.delenv(ENV_ROOT, raising=False)
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(root))
    assert resolve_metalabel_root() == root.resolve()


def test_from_env_missing_root_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "does_not_exist"
    monkeypatch.setenv(ENV_ROOT, str(missing))
    with pytest.raises(MetalabelError, match="missing|not found|unloadable"):
        Metalabeler.from_env()


def test_from_env_missing_model_file_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "empty_bundle"
    empty.mkdir()
    monkeypatch.setenv(ENV_ROOT, str(empty))
    with pytest.raises(MetalabelError, match="metalabel_lgbm|missing|unloadable"):
        Metalabeler.from_env()


def test_predict_probability_dict_orders_features_and_clips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("placeholder", encoding="utf-8")
    (root / "metalabel_metadata.json").write_text(
        '{"feature_names": ["a", "b", "c"]}',
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_ROOT, str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 10
    mock_booster.predict.return_value = np.array([1.5])

    with (
        patch("hypervector.ml.metalabel._load_booster", return_value=mock_booster),
        patch("hypervector.ml.metalabel._load_calibrator", return_value=None),
    ):
        ml = Metalabeler.from_env()
        out = ml.predict_probability({"c": 3.0, "a": 1.0, "b": 2.0})
        assert ml.predict_conviction({"c": 3.0, "a": 1.0, "b": 2.0}) == out

    assert out == 1.0
    call_X = mock_booster.predict.call_args[0][0]
    assert list(call_X[0]) == [1.0, 2.0, 3.0]


def test_predict_dataframe_last_row_and_calibrator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("placeholder", encoding="utf-8")
    (root / "metalabel_metadata.json").write_text(
        '{"feature_names": ["x", "y"]}',
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_ROOT, str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 5
    mock_booster.predict.return_value = np.array([0.3])

    mock_cal = MagicMock()
    mock_cal.predict.return_value = np.array([-0.2])

    with (
        patch("hypervector.ml.metalabel._load_booster", return_value=mock_booster),
        patch("hypervector.ml.metalabel._load_calibrator", return_value=mock_cal),
    ):
        ml = Metalabeler.from_env()
        df = pd.DataFrame({"x": [0.1, 0.9], "y": [0.2, 0.8]})
        out = ml.predict_probability(df)

    assert out == 0.0
    call_X = mock_booster.predict.call_args[0][0]
    assert list(call_X[0]) == pytest.approx([0.9, 0.8])
    mock_cal.predict.assert_called_once()
    assert list(mock_cal.predict.call_args[0][0]) == pytest.approx([0.3])


def test_predict_missing_feature_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("placeholder", encoding="utf-8")
    (root / "metalabel_metadata.json").write_text(
        '{"feature_names": ["a", "b"]}',
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_ROOT, str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 1
    with (
        patch("hypervector.ml.metalabel._load_booster", return_value=mock_booster),
        patch("hypervector.ml.metalabel._load_calibrator", return_value=None),
    ):
        ml = Metalabeler.from_env()
        with pytest.raises(MetalabelError, match="feature|missing"):
            ml.predict_probability({"a": 1.0})


def test_real_bundle_smoke_optional() -> None:
    """Optional smoke: load any real local metalabel bundle if present."""
    candidates = [
        Path(
            "/Users/gestas/Prototypes/hypertrader/backend/app/backtest/"
            "impulse_metalabel/models"
        ),
        Path(
            "/Users/gestas/dev/hyper-pi/services/ml-service/models/impulse-mr"
        ),
        Path(
            "/Users/gestas/dev/hyper-pi/services/ml-service/"
            "external-strategies/impulse_1m_btc/models"
        ),
    ]
    root = next(
        (p for p in candidates if (p / "metalabel_lgbm.txt").is_file()),
        None,
    )
    if root is None:
        pytest.skip("no local metalabel bundle on disk")

    size = (root / "metalabel_lgbm.txt").stat().st_size
    if size < 1024:
        pytest.skip("model file looks like git-lfs pointer / empty")

    try:
        import lightgbm  # noqa: F401
    except ImportError:
        pytest.skip("lightgbm not installed")

    ml = Metalabeler.from_root(root)
    names = ml.feature_names
    assert names, "expected feature_names from metadata or booster"
    feats: dict[str, Any] = {n: 0.0 for n in names}
    p = ml.predict_probability(feats)
    assert 0.0 <= p <= 1.0
