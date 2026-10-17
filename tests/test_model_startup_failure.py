"""An explicitly selected model must not silently become an unfiltered policy."""

from pathlib import Path

import pytest

from hypervector.ml.metalabel import MetalabelError
from hypervector.paper.session import _build_conviction_provider


def test_missing_filter_model_fails_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A technical model-load failure cannot remove a configured filter."""
    monkeypatch.setenv("HYPERVECTOR_METALABEL_ROOT", str(tmp_path / "absent"))
    with pytest.raises(MetalabelError):
        _build_conviction_provider(conviction=0.5, metalabel_enabled=True,
                                   metalabeler=None, conviction_provider=None,
                                   data_root=tmp_path, metalabel_mode="filter")
