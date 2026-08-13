"""Tests for the resumable 0xArchive backfill command boundary."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType


SCRIPT = Path(__file__).parents[1] / "scripts" / "oxa_backfill.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("oxa_backfill_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_uses_resilient_bounded_retry_default() -> None:
    """An unattended multi-month job should not use the old three-attempt budget."""
    module = _load_module()

    args = module._parser().parse_args(
        [
            "--symbol",
            "xyz:GOLD",
            "--market-family",
            "hip3",
            "--books-only",
            "--start",
            "2026-02-26T17:00:00Z",
            "--end",
            "2026-08-06T15:00:00Z",
        ]
    )

    assert args.retries == 10
