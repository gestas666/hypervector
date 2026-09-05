"""Immutable local-command tests for HIP-3 mark transport parity."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_mark_source_parity.py"


def test_command_publishes_exact_authority_none_source_snapshot(tmp_path: Path) -> None:
    """A frozen local file set produces one immutable two-symbol report."""
    _write_sources(tmp_path, "xyz:SP500", 100.0)
    _write_sources(tmp_path, "xyz:SPCX", 142.0)
    output = tmp_path / "report.json"

    report = _module().run_command(_args(tmp_path, output))

    assert report["status"] == "resolved_pass"
    assert report["execution_authority"] == "none"
    assert report["automatic_live_change"] is False
    assert report["symbols"] == ["xyz:SP500", "xyz:SPCX"]
    assert report["input_evidence"]["xyz:SP500"]["file_count"] == 1
    assert json.loads(output.read_text()) == report


def test_command_preserves_a_failed_symbol_without_success_shaping(
    tmp_path: Path,
) -> None:
    """One transport mismatch makes the combined disposition fail closed."""
    _write_sources(tmp_path, "xyz:SP500", 100.0)
    _write_sources(tmp_path, "xyz:SPCX", 142.0, websocket_price=140.0)

    report = _module().run_command(_args(tmp_path, tmp_path / "report.json"))

    assert report["status"] == "resolved_transport_mismatch"
    assert report["parity_passed"] is False
    assert report["reports"]["xyz:SPCX"]["parity_passed"] is False


def test_command_refuses_to_overwrite_an_existing_artifact(tmp_path: Path) -> None:
    """Publication is immutable even when all source evidence is valid."""
    _write_sources(tmp_path, "xyz:SP500", 100.0)
    _write_sources(tmp_path, "xyz:SPCX", 142.0)
    output = tmp_path / "report.json"
    output.write_text("{}")

    with pytest.raises(FileExistsError):
        _module().run_command(_args(tmp_path, output))


def _args(root: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        symbols=["xyz:SP500", "xyz:SPCX"],
        data_root=root,
        date="2026-08-14",
        maximum_pair_age_ms=100,
        minimum_pairs=2,
        maximum_mark_difference_bps=1.0,
        output=output,
    )


def _write_sources(
    root: Path,
    symbol: str,
    rest_price: float,
    *,
    websocket_price: float | None = None,
) -> None:
    directory = (
        root / "cache/events/hyperliquid" / symbol / "2026-08-14/asset_context.parquet"
    )
    directory.mkdir(parents=True)
    websocket = rest_price if websocket_price is None else websocket_price
    pd.DataFrame(
        [
            _row(symbol, "hyperliquid_info_metaAndAssetCtxs", 1_000, rest_price),
            _row(symbol, "hyperliquid_ws_activeAssetCtx", 1_010, websocket),
            _row(symbol, "hyperliquid_info_metaAndAssetCtxs", 4_000, rest_price),
            _row(symbol, "hyperliquid_ws_activeAssetCtx", 4_010, websocket),
        ]
    ).to_parquet(directory / "part-test.parquet", index=False)


def _row(
    symbol: str, source: str, milliseconds: int, price: float
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "received_ts_ns": milliseconds * 1_000_000,
        "mark_price": price,
        "source": source,
    }


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_mark_source_parity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
