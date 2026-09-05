"""Immutable local-command tests for HIP-3 REST response-lag evidence."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_mark_response_lag.py"


def test_command_publishes_two_symbol_authority_none_lag_report(
    tmp_path: Path,
) -> None:
    """Frozen local parquet parts produce one immutable causal report."""
    _write_sources(tmp_path, "xyz:SP500", stale=False)
    _write_sources(tmp_path, "xyz:SPCX", stale=True)
    output = tmp_path / "report.json"

    report = _module().run_command(_args(tmp_path, output))

    assert report["status"] == "resolved_rest_receipt_not_exact"
    assert report["execution_authority"] == "none"
    assert report["automatic_live_change"] is False
    assert report["reports"]["xyz:SP500"]["stale_context_rows"] == 0
    assert report["reports"]["xyz:SPCX"]["stale_context_rows"] == 2
    assert report["input_evidence"]["xyz:SP500"]["file_count"] == 1
    assert json.loads(output.read_text()) == report


def test_command_preserves_insufficient_overlap_without_success_shaping(
    tmp_path: Path,
) -> None:
    """One response per symbol cannot satisfy a two-response declaration."""
    _write_sources(tmp_path, "xyz:SP500", stale=False, pairs=1)
    _write_sources(tmp_path, "xyz:SPCX", stale=False, pairs=1)

    report = _module().run_command(_args(tmp_path, tmp_path / "report.json"))

    assert report["status"] == "insufficient_overlap"
    assert report["disposition"] == "collect_more_overlap"


def test_command_refuses_to_overwrite_an_existing_artifact(tmp_path: Path) -> None:
    """A published lag report remains immutable."""
    output = tmp_path / "report.json"
    output.write_text("{}")

    with pytest.raises(FileExistsError):
        _module().run_command(_args(tmp_path, output))


def _args(root: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        symbols=["xyz:SP500", "xyz:SPCX"],
        data_root=root,
        date="2026-08-14",
        minimum_rest_rows=2,
        output=output,
    )


def _write_sources(root: Path, symbol: str, *, stale: bool, pairs: int = 2) -> None:
    directory = (
        root / "cache/events/hyperliquid" / symbol / "2026-08-14/asset_context.parquet"
    )
    directory.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for index in range(pairs):
        base = 1_000 + index * 5_000
        rows.append(_row(symbol, "hyperliquid_ws_activeAssetCtx", base, 100.0, 5.0))
        if stale:
            rows.append(
                _row(symbol, "hyperliquid_ws_activeAssetCtx", base + 800, 101.0, 6.0)
            )
        rows.append(
            _row(symbol, "hyperliquid_info_metaAndAssetCtxs", base + 1_000, 100.0, 5.0)
        )
    pd.DataFrame(rows).to_parquet(directory / "part-test.parquet", index=False)


def _row(
    symbol: str, source: str, milliseconds: int, mark: float, open_interest: float
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "received_ts_ns": milliseconds * 1_000_000,
        "mark_price": mark,
        "oracle_price": mark + 1.0,
        "funding_rate_hourly": 0.0001,
        "open_interest": open_interest,
        "mid_price": mark + 0.01,
        "source": source,
    }


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_mark_response_lag_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
