"""Command-surface tests for the immutable residual development runner."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest


_SCRIPT = Path("scripts/cross_asset_residual_development.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("cross_asset_residual_development", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load residual script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_one_development_run_without_live_flags() -> None:
    """The runner exposes evidence paths but no execution authority."""
    args = _module().build_parser().parse_args([])

    assert args.data_root == Path("data")
    assert args.run_id == "cross_asset_residual_development_v2"
    assert args.output.name == "cross_asset_residual_development_v2.json"
    assert args.trades_output.name.endswith(".trades.parquet")


def test_immutable_parquet_refuses_to_replace_evidence(tmp_path: Path) -> None:
    """A rerun cannot overwrite a favorable or unfavorable prior result."""
    module = _module()
    path = tmp_path / "trades.parquet"
    path.write_bytes(b"existing")

    with pytest.raises(FileExistsError, match="immutable parquet"):
        module.write_immutable_parquet(path, pd.DataFrame({"value": [1]}))


def test_command_surface_contains_no_live_execution_vocabulary() -> None:
    """The development command must not contain venue-order controls."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
    assert "build_residual_generator_identity" in source
