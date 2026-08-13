"""Tests for the observe-only source-long monitor command."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


SCRIPT = Path("scripts/source_long_forward_monitor.py")
BIDIRECTIONAL_PROFILE = Path(
    "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc35_shadow.toml"
)


def _load_module() -> ModuleType:
    """Load the command module without executing its CLI entry point."""
    spec = importlib.util.spec_from_file_location("source_long_forward_monitor", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_profile_matches_bidirectional_live_strategy() -> None:
    """Keep observer provenance aligned with its bidirectional source ledger."""
    args = _load_module().build_parser().parse_args([])

    assert args.profile == BIDIRECTIONAL_PROFILE
