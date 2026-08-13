"""CLI boundary tests for the standalone MU report-only observer."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_SCRIPT = Path("scripts/mu_hip3_breakout_shadow_observe.py")


def _module() -> object:
    spec = importlib.util.spec_from_file_location("mu_shadow_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_command_is_isolated_report_only_mu_capture() -> None:
    module = _module()

    config = module.config_from_args(module.build_parser().parse_args([]))

    assert str(config.paths.asset_ledger).startswith("data/live/research/")
    assert "xyz:mu" in config.paths.asset_ledger.name.lower()
    assert str(config.paths.cursor).startswith("data/runtime/research/")
    assert config.poll_seconds == 5.0
    assert config.max_polls is None
    assert config.execution_authority == "none"
    assert config.report_only is True
    assert not hasattr(config, "wallet")
    assert not hasattr(config, "private_key")
