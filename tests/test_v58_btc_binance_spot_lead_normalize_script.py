"""Tests for the outcome-blind Binance spot normalization command."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def test_binance_spot_normalization_script_exists() -> None:
    """The normalization boundary must have a reproducible command."""
    assert Path("scripts/v58_btc_binance_spot_lead_normalize.py").is_file()


def test_command_uses_fixed_default_bundle_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper must pass only the frozen source and new immutable output."""
    module = _load_module()
    assert hasattr(module, "build_parser")
    assert hasattr(module, "run_command")
    captured: list[tuple[Path, Path]] = []

    def publish(source: Path, output: Path) -> Path:
        captured.append((source, output))
        return output

    monkeypatch.setattr(module, "publish_normalized_binance_spot_bundle", publish)
    args = module.build_parser().parse_args([])

    assert module.run_command(args) == args.output
    assert captured == [(args.source, args.output)]
    assert args.source.name.endswith("spot_1m_v58_lead_v1")
    assert args.output.name.endswith("spot_1m_v58_lead_v1_normalized")


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_binance_spot_lead_normalize.py")
    spec = importlib.util.spec_from_file_location("btc_binance_normalize_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
