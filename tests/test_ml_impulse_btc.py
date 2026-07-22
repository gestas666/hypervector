"""Unit tests for optional BTC impulse metalabel conviction façade."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from hypervector.ml.impulse_btc import (
    ImpulseBtcFacade,
    ImpulseBundleError,
    resolve_impulse_btc_root,
)


def test_resolve_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("tree", encoding="utf-8")
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(root))
    assert resolve_impulse_btc_root() == root.resolve()


def test_from_env_missing_root_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(missing))
    with pytest.raises(ImpulseBundleError, match="missing|not found|unloadable"):
        ImpulseBtcFacade.from_env()


def test_from_env_missing_model_file_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "empty_bundle"
    empty.mkdir()
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(empty))
    with pytest.raises(ImpulseBundleError, match="metalabel_lgbm|missing|unloadable"):
        ImpulseBtcFacade.from_env()


def test_predict_conviction_dict_orders_features_and_clips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    model_path = root / "metalabel_lgbm.txt"
    model_path.write_text("placeholder", encoding="utf-8")
    (root / "metalabel_metadata.json").write_text(
        '{"feature_names": ["a", "b", "c"]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 10
    mock_booster.predict.return_value = np.array([1.5])  # above 1 → clip

    with (
        patch("hypervector.ml.impulse_btc._load_booster", return_value=mock_booster),
        patch("hypervector.ml.impulse_btc._load_calibrator", return_value=None),
    ):
        facade = ImpulseBtcFacade.from_env()
        out = facade.predict_conviction({"c": 3.0, "a": 1.0, "b": 2.0})

    assert out == 1.0
    call_X = mock_booster.predict.call_args[0][0]
    assert list(call_X[0]) == [1.0, 2.0, 3.0]


def test_predict_conviction_dataframe_last_row_and_calibrator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "metalabel_lgbm.txt").write_text("placeholder", encoding="utf-8")
    (root / "metalabel_metadata.json").write_text(
        '{"feature_names": ["x", "y"]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 5
    mock_booster.predict.return_value = np.array([0.3])

    mock_cal = MagicMock()
    mock_cal.predict.return_value = np.array([-0.2])  # below 0 → clip

    with (
        patch("hypervector.ml.impulse_btc._load_booster", return_value=mock_booster),
        patch("hypervector.ml.impulse_btc._load_calibrator", return_value=mock_cal),
    ):
        facade = ImpulseBtcFacade.from_env()
        df = pd.DataFrame({"x": [0.1, 0.9], "y": [0.2, 0.8]})
        out = facade.predict_conviction(df)

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
    monkeypatch.setenv("HYPERVECTOR_IMPULSE_BTC_ROOT", str(root))

    mock_booster = MagicMock()
    mock_booster.best_iteration = 1
    with (
        patch("hypervector.ml.impulse_btc._load_booster", return_value=mock_booster),
        patch("hypervector.ml.impulse_btc._load_calibrator", return_value=None),
    ):
        facade = ImpulseBtcFacade.from_env()
        with pytest.raises(ImpulseBundleError, match="feature|missing"):
            facade.predict_conviction({"a": 1.0})


def test_real_bundle_smoke_optional() -> None:
    """Optional smoke: load real hypertrader/hyper-pi models if present."""
    candidates = [
        Path(
            "/Users/gestas/Prototypes/hypertrader/backend/app/backtest/"
            "impulse_metalabel/models"
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
        pytest.skip("no local impulse metalabel bundle on disk")

    # Skip git-lfs pointer files (tiny text stubs).
    size = (root / "metalabel_lgbm.txt").stat().st_size
    if size < 1024:
        pytest.skip("model file looks like git-lfs pointer / empty")

    try:
        import lightgbm  # noqa: F401
    except ImportError:
        pytest.skip("lightgbm not installed")

    facade = ImpulseBtcFacade.from_root(root)
    names = facade.feature_names
    assert names, "expected feature_names from metadata or booster"
    feats: dict[str, Any] = {n: 0.0 for n in names}
    p = facade.predict_conviction(feats)
    assert 0.0 <= p <= 1.0
