"""Tests for immutable SP500 exact-mark profit-lock evidence."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.oxa_prices import (
    OxaPriceFetch,
    OxaPriceRequest,
    OxaPriceSnapshot,
    store_price_history,
)

_SCRIPT = Path(__file__).parents[1] / "scripts" / "sp500_profit_lock_exact_mark.py"


def test_command_replays_only_archive_bounded_lifecycles(tmp_path: Path) -> None:
    assert _SCRIPT.is_file()
    module = _module()
    start = datetime(2026, 6, 8, 8, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    trades = tmp_path / "trades.parquet"
    acquisition = tmp_path / "acquisition.json"
    output = tmp_path / "report.json"
    _trades(trades, start)
    row_count = _prices(tmp_path, start, end)
    _acquisition(acquisition, start, end, row_count)
    args = Namespace(
        trades=trades,
        data_root=tmp_path,
        acquisition=acquisition,
        output=output,
    )

    assert module.run_command(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "cohort_profit_lock_exact_exchange_mark_v1"
    assert report["path_source"] == "exact_exchange_mark"
    assert report["selection"]["selected_lifecycles"] == 2
    assert report["sources"]["price_archive"]["partition_count"] == 1
    assert report["sources"]["price_archive"]["selected_bars_sha256"]
    assert report["sources"]["acquisition"]["sha256"]

    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.run_command(args)


def test_command_rejects_archive_that_disagrees_with_acquisition_audit(
    tmp_path: Path,
) -> None:
    module = _module()
    start = datetime(2026, 6, 8, 8, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    trades = tmp_path / "trades.parquet"
    acquisition = tmp_path / "acquisition.json"
    _trades(trades, start)
    row_count = _prices(tmp_path, start, end)
    _acquisition(acquisition, start, end, row_count + 1)
    args = Namespace(
        trades=trades,
        data_root=tmp_path,
        acquisition=acquisition,
        output=tmp_path / "report.json",
    )

    with pytest.raises(ValueError, match="does not match its acquisition audit"):
        module.run_command(args)


def _module() -> object:
    spec = spec_from_file_location("sp500_profit_lock_exact_mark_script", _SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trades(path: Path, start: datetime) -> None:
    row = {
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "symbol": "xyz:SP500",
        "phase": "development",
        "friction": "stress",
        "direction": "long",
        "entry_time_utc": (start + timedelta(seconds=1)).isoformat(),
        "exit_time_utc": (start + timedelta(minutes=4)).isoformat(),
        "entry_price": 100.0,
        "exit_price": 100.2,
        "quantity": 1.0,
        "gross_pnl_usd": 0.2,
        "fees_usd": 0.09,
    }
    validation = {**row, "phase": "validation"}
    outside = {
        **row,
        "entry_time_utc": (start - timedelta(minutes=4)).isoformat(),
        "exit_time_utc": (start - timedelta(minutes=1)).isoformat(),
    }
    pd.DataFrame((row, validation, outside)).to_parquet(path, index=False)


def _prices(root: Path, start: datetime, end: datetime) -> int:
    timestamps = range(_ms(start), _ms(end), 3_000)
    snapshots = tuple(
        OxaPriceSnapshot(
            datetime.fromtimestamp(timestamp / 1_000, tz=UTC).isoformat(),
            timestamp,
            str(100.0 + ((timestamp // 30_000) % 3) * 0.3),
            "100.0",
            "100.0",
        )
        for timestamp in timestamps
    )
    request = OxaPriceRequest("xyz:SP500", start, end, market_family="hip3")
    store_price_history(root, request, OxaPriceFetch((), snapshots, True, None))
    return len(snapshots)


def _acquisition(path: Path, start: datetime, end: datetime, row_count: int) -> None:
    payload = {
        "schema_version": 1,
        "status": "accepted_for_report_only_development_replay",
        "execution_authority": "none",
        "bounds": {
            "start_inclusive_utc": start.isoformat(),
            "end_exclusive_utc": end.isoformat(),
        },
        "symbols": {
            "xyz:SP500": {
                "price_audit": {
                    "partition_count": 1,
                    "row_count": row_count,
                    "mark_rows": row_count,
                    "missing_mark_rows": 0,
                    "empty_partitions": 0,
                }
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)
