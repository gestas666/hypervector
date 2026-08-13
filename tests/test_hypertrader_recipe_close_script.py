"""Command contract for pinned Hypertrader B/C close-only replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.hypertrader_source_adapter import (
    LEGACY_HYPERTRADER_REVISION,
)


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_close_replay.py")
    spec = importlib.util.spec_from_file_location("hypertrader_close_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader close replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_close_replay_command_preserves_source_and_serialized_variants() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--bars",
            "old.parquet",
            "--bars",
            "fresh.parquet",
            "--creator-rows",
            "creator.csv",
            "--out",
            "result.json",
        ]
    )
    contract = module._experiment_contract()

    assert args.bars == [Path("old.parquet"), Path("fresh.parquet")]
    assert contract["variants"] == ["source_independent", "one_position_serialized"]
    assert contract["target"] == "first close at 20bps OR 130 BTC points"
    assert contract["fee_bps_round_trip"] == 8.0
    assert contract["runtime_strategy_changed"] is False


def test_close_replay_accepts_report_only_trend_aligned_variant() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--bars",
            "bars.parquet",
            "--creator-rows",
            "creator.csv",
            "--candidate-family",
            "trend-aligned",
            "--out",
            "result.json",
        ]
    )

    contract = module._experiment_contract("trend-aligned")

    assert args.candidate_family == "trend-aligned"
    assert contract["candidate_family"] == "trend-aligned"
    assert contract["runtime_strategy_changed"] is False


def test_close_replay_accepts_all_day_source_follow_variant() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--labels",
            "labels.parquet",
            "--labels-metadata",
            "labels.json",
            "--bars",
            "bars.parquet",
            "--creator-rows",
            "creator.csv",
            "--candidate-family",
            "source-follow-all-day",
            "--maximum-signal-range-bps",
            "40",
            "--out",
            "result.json",
        ]
    )
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_DOWN"],
            "secondary_code": [None, None],
            "confidence": [0.5, 0.8],
        },
        index=pd.to_datetime(
            ["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"], utc=True
        ),
    )

    events = module._candidate_events(labels, args.candidate_family)

    assert args.candidate_family == "source-follow-all-day"
    assert args.maximum_signal_range_bps == 40.0
    assert events["recipe_id"].tolist() == ["follow_td_all_day"]
    assert events["side"].tolist() == ["short"]


def test_close_replay_range_ceiling_retains_only_eligible_events() -> None:
    module = _load_script()
    times = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"], utc=True)
    events = pd.DataFrame({"label_time_utc": times, "recipe_id": ["a", "a"]})
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.2, 100.5],
            "low": [99.9, 99.9],
        },
        index=times,
    )

    eligible = module._range_eligible_events(events, bars, maximum_bps=40.0)

    assert len(eligible) == 1
    assert eligible["signal_range_bps"].iloc[0] == pytest.approx(30.0)
    assert eligible["entry_eligible"].all()


def test_close_replay_contract_records_the_evaluated_source_revision() -> None:
    module = _load_script()

    contract = module._experiment_contract(
        "source-fade", upstream_revision=LEGACY_HYPERTRADER_REVISION
    )

    assert contract["upstream_revision"] == LEGACY_HYPERTRADER_REVISION


def test_close_replay_reports_deterministic_ninety_day_slices() -> None:
    module = _load_script()
    trades = pd.DataFrame(
        {
            "label_time_utc": pd.to_datetime(
                [
                    "2025-07-28T00:00:00Z",
                    "2025-10-26T00:00:00Z",
                    "2026-07-23T00:00:00Z",
                ],
                utc=True,
            ),
            "admission": ["accepted", "accepted", "accepted"],
            "exit_reason": ["tp", "timeout", "tp"],
            "net_bps": [12.0, -8.0, 12.0],
            "recipe_id": ["a", "a", "a"],
        }
    )

    slices = module._fixed_duration_slices(
        trades,
        start=pd.Timestamp("2025-07-28T00:00:00Z"),
        end=pd.Timestamp("2026-07-28T00:00:00Z"),
    )

    assert len(slices) == 5
    assert slices[0]["window_start_utc"] == "2025-07-28T00:00:00+00:00"
    assert slices[0]["window_end_utc"] == "2025-10-26T00:00:00+00:00"
    assert slices[0]["summary"]["tp"] == 1
    assert slices[1]["summary"]["timeout"] == 1
    assert slices[-1]["window_end_utc"] == "2026-07-28T00:00:00+00:00"
    assert slices[-1]["summary"]["tp"] == 1
