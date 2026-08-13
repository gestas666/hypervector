"""Contracts for the immutable BTC 15-minute maker-entry experiment."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/market_cipher_maker_screen.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("market_cipher_maker_screen", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load maker-entry screen: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _argv(output: Path) -> list[str]:
    return [
        "--database",
        "data/research/market.duckdb",
        "--baseline",
        "data/logs/research/baseline.json",
        "--funding",
        "data/cache/vendor/BTC/funding.parquet",
        "--start",
        "2025-08-23T09:00:00Z",
        "--end",
        "2026-02-01T00:00:00Z",
        "--segment",
        "development",
        "--out",
        str(output),
    ]


def test_parser_requires_explicit_baseline_window_and_segment() -> None:
    """The experiment cannot inherit ambiguous data or chronology."""
    module = _module()

    with pytest.raises(SystemExit):
        module._parser().parse_args([])

    args = module._parser().parse_args(_argv(Path("report.json")))
    assert args.segment == "development"
    assert args.entry_ttl_seconds == 300
    assert args.maximum_book_delay_ms == 1_000


def test_existing_report_or_sidecar_is_rejected_before_data_access(
    tmp_path: Path,
) -> None:
    """A later run cannot overwrite prior evidence or its sidecars."""
    output = tmp_path / "report.json"
    output.with_suffix(".entries.parquet").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="maker-entry output exists"):
        _module().main(_argv(output))


def test_command_has_no_live_execution_surface() -> None:
    """The historical screen must remain structurally unable to place orders."""
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "i-accept-live-risk" not in source
    assert "private_key" not in source
    assert "submit_order" not in source
