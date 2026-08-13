"""Command-contract tests for selective BTC Recipe B/C research."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_selective_recipe.py")
    spec = importlib.util.spec_from_file_location("selective_recipe_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load selective recipe script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_requires_all_frozen_evidence_inputs() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--supplemental-bars",
            "fresh.parquet",
            "--source-rows",
            "creator.csv",
            "--live-rows",
            "live.csv",
            "--config",
            "config.toml",
            "--archive-audit",
            "audit.json",
            "--out",
            "report.json",
        ]
    )

    assert args.bars == Path("bars.parquet")
    assert args.supplemental_bars == Path("fresh.parquet")
    assert args.archive_audit == Path("audit.json")
    assert args.out == Path("report.json")


def test_experiment_contract_is_report_only_and_finite() -> None:
    module = _load_script()
    args = argparse.Namespace()

    contract = module._experiment_contract(args)

    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["model_authority"] == {
        "mode": "observe",
        "may_filter": False,
        "may_scale": False,
    }
    assert contract["session_windows_utc"] == {
        "bk_up_asia_conf06": "00:00-08:00",
        "fade_td_eu": "07:00-16:00",
    }
    assert contract["maker_ttl_seconds"] == 300.0
    assert contract["candidate_order"] == [
        "b_confirmed_5m_breakout_up_onset",
        "b_raw_1m_breakout_up_onset_in_5m_long",
        "b_1m_trend_up_onset_in_5m_long",
        "c_5m_trend_down_onset",
        "c_1m_trend_up_recovery_in_5m_down",
    ]


def _bars(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="1min")
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
        }
    )


def test_merge_bars_requires_exact_nonoverlapping_cadence(tmp_path: Path) -> None:
    module = _load_script()
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    _bars("2026-01-01T00:00:00Z", 2).to_parquet(first, index=False)
    _bars("2026-01-01T00:02:00Z", 2).to_parquet(second, index=False)

    merged = module._merged_bars(first, second)

    assert len(merged) == 4
    assert merged.index[0] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert merged.index[-1] == pd.Timestamp("2026-01-01T00:03:00Z")

    _bars("2026-01-01T00:03:00Z", 2).to_parquet(second, index=False)
    with pytest.raises(ValueError, match="uninterrupted"):
        module._merged_bars(first, second)


def test_source_rows_preserve_inferred_and_displayed_utc_modes(tmp_path: Path) -> None:
    module = _load_script()
    path = tmp_path / "creator.csv"
    pd.DataFrame(
        {
            "evidence_id": ["row1"],
            "recipe_id": ["bk_up_asia_conf06"],
            "side": ["long"],
            "entry_time_displayed": ["2026-07-21 01:35 AM"],
            "entry_time_utc_inferred": ["2026-07-21T06:35:00Z"],
        }
    ).to_csv(path, index=False)

    inferred = module._source_rows(path, displayed_as_utc=False)
    displayed = module._source_rows(path, displayed_as_utc=True)

    assert inferred.iloc[0]["entry_time_utc_inferred"] == pd.Timestamp(
        "2026-07-21T06:35:00Z"
    )
    assert displayed.iloc[0]["entry_time_utc_inferred"] == pd.Timestamp(
        "2026-07-21T01:35:00Z"
    )
