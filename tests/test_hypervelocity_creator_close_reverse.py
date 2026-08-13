"""Creator close/reverse reconstruction contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.hypervelocity_creator_close_reverse import (
    creator_close_reverse_evidence,
)


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "position_peak_id": [51, 52, 53],
            "side": ["long", "short", "long"],
            "status": ["closed", "closed", "closed"],
            "open_time_utc": [
                "2026-01-01T00:00:10Z",
                "2026-01-01T00:01:50Z",
                "2026-01-01T00:04:00Z",
            ],
            "close_time_utc": [
                "2026-01-01T00:01:20Z",
                "2026-01-01T00:03:30Z",
                "2026-01-01T00:05:10Z",
            ],
            "entry_price": [100.0, 101.0, 99.0],
            "exit_price": [None, None, 100.0],
            "exit_reason": [
                "closed_no_trade_row",
                "closed_no_trade_row",
                "external_close",
            ],
        }
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-01T00:01:00Z", "2026-01-01T00:03:00Z"], utc=True
            ),
            "open": [99.9, 101.1],
            "high": [99.95, 101.4],
            "low": [99.8, 101.0],
            "close": [99.9, 101.2],
            "volume": [1.0, 2.0],
            "source": ["hl", "hl"],
        }
    )


def _script_module() -> ModuleType:
    path = Path("scripts/hypervelocity_creator_close_reverse.py")
    spec = importlib.util.spec_from_file_location("creator_close_reverse", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load creator close/reverse script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reconstruction_reports_side_aware_bounds_and_opposite_latency() -> None:
    report = creator_close_reverse_evidence(_positions(), _bars())

    assert report["raw_missing_exit_rows"] == 2
    assert report["estimated_outcomes"] == {"adverse": 2, "favorable": 0, "flat": 0}
    first, second = report["positions"]
    assert first["position_peak_id"] == 51
    assert first["close_minute_utc"] == "2026-01-01T00:01:00+00:00"
    assert first["estimated_close_margin_pct"] == pytest.approx(-4.0)
    assert first["estimated_minute_margin_low_pct"] == pytest.approx(-8.0)
    assert first["estimated_minute_margin_high_pct"] == pytest.approx(-2.0)
    assert first["next_position_side"] == "short"
    assert first["next_position_open_latency_seconds"] == pytest.approx(30.0)
    assert first["next_position_is_opposite"] is True
    assert second["estimated_close_margin_pct"] == pytest.approx(-7.920792)
    assert second["estimated_outcome"] == "adverse"


def test_reconstruction_rejects_a_missing_exact_close_minute() -> None:
    with pytest.raises(ValueError, match="missing exact Hyperliquid close minute"):
        creator_close_reverse_evidence(_positions(), _bars().iloc[:1])


def test_reconstruction_rejects_non_hyperliquid_or_duplicate_bars() -> None:
    duplicate = pd.concat([_bars(), _bars().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="unique timestamps"):
        creator_close_reverse_evidence(_positions(), duplicate)

    other = _bars().copy()
    other["source"] = "binance"
    with pytest.raises(ValueError, match="Hyperliquid source"):
        creator_close_reverse_evidence(_positions(), other)


def test_reconstruction_allows_unselected_explicit_gap_fill_rows() -> None:
    gap = _bars().iloc[[0]].copy()
    gap["timestamp"] = pd.Timestamp("2026-01-01T00:02:00Z")
    gap["source"] = "hl_gap_fill"
    bars = pd.concat([_bars(), gap], ignore_index=True).sort_values("timestamp")

    report = creator_close_reverse_evidence(_positions(), bars)

    assert report["raw_missing_exit_rows"] == 2


def test_script_contract_is_report_only_and_writes_immutably(tmp_path: Path) -> None:
    module = _script_module()
    positions_path = tmp_path / "positions.csv"
    bars_path = tmp_path / "bars.parquet"
    _positions().to_csv(positions_path, index=False)
    _bars().to_parquet(bars_path, index=False)
    args = module._parser().parse_args(
        [
            "--positions",
            str(positions_path),
            "--bars",
            str(bars_path),
            "--out",
            str(tmp_path / "report.json"),
        ]
    )

    assert args.positions == positions_path
    report = module._report(_positions(), _bars(), args)
    assert report["report_only"] is True
    assert report["runtime_strategy_changed"] is False
    assert report["exact_exit_fill_available"] is False
    module._write(args.out, report)
    with pytest.raises(FileExistsError, match="output exists"):
        module._write(args.out, report)
