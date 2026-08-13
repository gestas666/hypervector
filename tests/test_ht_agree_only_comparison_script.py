"""Command tests for the immutable HT agree-only comparison."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts" / "ht_agree_only_comparison.py"


def test_command_publishes_authority_none_artifact(tmp_path: Path) -> None:
    module = _load_module()
    bars = tmp_path / "bars.parquet"
    funding = tmp_path / "funding.parquet"
    bars.write_bytes(b"bars")
    funding.write_bytes(b"funding")
    output = tmp_path / "result.json"
    args = argparse.Namespace(
        symbol="BTC",
        bars=bars,
        funding=funding,
        holdout_days=1,
        out=output,
    )

    report = module.run_report(args, market_loader=_markets)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["contract"]["execution_authority"] == "none"
    assert report["evidence"]["bars"]["sha256"]
    assert report["evidence"]["funding"]["sha256"]
    assert report["generator_identity"]["files"]


def _markets(
    _bars: Path,
    _funding: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    index = pd.date_range("2026-01-01", periods=5_000, freq="1min", tz="UTC")
    base = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_1m": "TREND_UP",
            "state_5m": "BREAKOUT",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    structural = base.copy()
    breakout = base.copy()
    structural.loc[index[100], "entry_side"] = "long"
    breakout.loc[index[100], "entry_side"] = "long"
    return structural, breakout, {"fixture": "exact"}


def _load_module() -> ModuleType:
    spec = spec_from_file_location("ht_agree_only_comparison_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
