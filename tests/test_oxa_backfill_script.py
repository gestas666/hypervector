"""Tests for the resumable 0xArchive backfill command boundary."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def _load_module() -> ModuleType:
    return import_module("hypervector.operations.oxa_backfill")


def test_cli_uses_resilient_bounded_retry_default() -> None:
    """An unattended multi-month job should not use the old three-attempt budget."""
    module = _load_module()

    args = module.build_parser().parse_args(
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
