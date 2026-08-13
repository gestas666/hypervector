"""CLI boundary for immutable raw-reset creator evidence."""

from __future__ import annotations

from argparse import Namespace
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd


def test_script_publishes_report_only_immutable_evidence(tmp_path: Path) -> None:
    """The audit artifact must explicitly carry no execution authority."""
    module = _load_script()
    positions = tmp_path / "positions.csv"
    labels = tmp_path / "labels.parquet"
    out = tmp_path / "result.json"
    _positions().to_csv(positions, index=False)
    _labels().to_parquet(labels, index=False)

    report = module.run(Namespace(positions=positions, labels=labels, out=out))

    persisted = json.loads(out.read_text(encoding="utf-8"))
    assert report == persisted
    assert persisted["report_only"] is True
    assert persisted["execution_authority"] == "none"
    assert persisted["runtime_strategy_changed"] is False
    assert persisted["result"]["same_side_nonoverlapping_reentries"] == 1


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_reentry_raw_reset.py")
    spec = importlib.util.spec_from_file_location("source_reentry_raw_reset", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_utc": ["2026-07-01T00:00:00Z", "2026-07-01T00:15:00Z"],
            "close_time_utc": ["2026-07-01T00:05:00Z", "2026-07-01T00:20:00Z"],
            "side": ["short", "short"],
            "entry_price": [100.0, 99.0],
            "exit_price": [99.0, 98.0],
            "status": ["closed", "closed"],
        }
    )


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2026-07-01T00:10:00Z", "2026-07-01T00:15:00Z"], utc=True
            ),
            "primary_code": ["TREND_DOWN", "TREND_DOWN"],
            "secondary_code": [None, None],
            "raw_primary_code": ["RANGE", "TREND_DOWN"],
            "raw_secondary_code": [None, None],
        }
    )
