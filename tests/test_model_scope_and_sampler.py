"""Explicit dependency and data-root choices must not silently fall back."""

from __future__ import annotations

from pathlib import Path

import pytest

from hypervector.ml.metalabel import MetalabelError, resolve_metalabel_root
from hypervector.sweep import autotune


def test_explicit_data_root_never_discovers_another_projects_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty isolated root stays unavailable even if cwd has a valid bundle."""
    monkeypatch.chdir(tmp_path)
    local = tmp_path / "data/models/metalabel"
    local.mkdir(parents=True)
    (local / "metalabel_lgbm.txt").write_text("x" * 300)
    with pytest.raises(MetalabelError, match="not found"):
        resolve_metalabel_root(env={}, data_root=tmp_path / "isolated")


def test_explicit_optuna_requires_its_dependency_before_loading_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A named TPE run must not silently execute a different search algorithm."""
    monkeypatch.setattr(autotune, "HAVE_OPTUNA", False)
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: pytest.fail("history read before dependency check"))
    with pytest.raises(RuntimeError, match="Optuna.*install"):
        autotune.run_autotune(data_root=tmp_path, sampler="optuna")


def test_unknown_sampler_is_rejected_before_loading_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Python API and CLI enforce the same explicit sampler vocabulary."""
    monkeypatch.setattr(autotune, "load_research_history", lambda *_a, **_k: pytest.fail("history read before sampler check"))
    with pytest.raises(ValueError, match="sampler"):
        autotune.run_autotune(data_root=tmp_path, sampler="typo")
