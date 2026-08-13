from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

_SCRIPT = Path("scripts/low_tf_asset_tuning.py")


def _module() -> ModuleType:
    spec = spec_from_file_location("low_tf_asset_tuning_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load tuning script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_defaults_to_both_assets_and_report_only_paths() -> None:
    script = _module()
    args = script.build_parser().parse_args([])

    assert args.symbol == ["ETH", "SOL"]
    assert args.selected_per_group == 3
    assert args.workers == 4
    assert args.reuse_development_run_id is None
    assert args.output == Path(
        "data/logs/research/eth_sol_bidirectional_5m15m_tuning_v1_20260805.json"
    )
    assert args.journal == Path("data/research/strategy_trials.duckdb")


def test_default_inputs_pin_year_matched_hyperliquid_sources() -> None:
    script = _module()
    inputs = script.default_asset_inputs(Path("data"), ("ETH", "SOL"))

    assert [value.symbol for value in inputs] == ["ETH", "SOL"]
    assert [value.venue_max_leverage for value in inputs] == [25.0, 20.0]
    assert all("365d" in value.bars_path.name for value in inputs)
    assert all(
        "20250728T000000000000Z_20260728T000000000000Z" in str(value.funding_path)
        for value in inputs
    )


def test_window_slicers_support_datetime_index_comparisons() -> None:
    script = _module()
    window = script.TuningWindow(
        "test",
        pd.Timestamp("2026-01-01T00:05:00Z"),
        pd.Timestamp("2026-01-01T00:15:00Z"),
    )
    five = pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=4, freq="5min", tz="UTC"
            ),
            "close": [1.0] * 4,
        }
    )
    minutes = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="1min", tz="UTC"),
            "close": [1.0] * 20,
        }
    )

    assert len(script._scored_five_minute_bars(five, window)) == 2
    assert len(script._scored_features(five, window)) == 2
    assert len(script._scored_minutes(minutes, window)) == 10
