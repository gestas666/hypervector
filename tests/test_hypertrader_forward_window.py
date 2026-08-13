"""Forward-window contract for the Hypertrader maker replay command."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pandas as pd


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("hypertrader_forward_window", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Hypertrader maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _required_arguments() -> list[str]:
    return [
        "--labels",
        "labels.parquet",
        "--development-price-context",
        "dev-prices.parquet",
        "--development-funding-context",
        "dev-funding.parquet",
        "--fresh-price-context",
        "fresh-prices.parquet",
        "--fresh-funding-context",
        "fresh-funding.parquet",
        "--out",
        "maker.json",
    ]


def test_cli_accepts_explicit_causal_replay_window() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            *_required_arguments(),
            "--data-start",
            "2026-07-28T00:00:00Z",
            "--fresh-start",
            "2026-07-28T00:00:00Z",
            "--data-end",
            "2026-07-28T22:00:00Z",
        ]
    )

    assert args.data_start == datetime(2026, 7, 28, tzinfo=UTC)
    assert args.fresh_start == datetime(2026, 7, 28, tzinfo=UTC)
    assert args.data_end == datetime(2026, 7, 28, 22, tzinfo=UTC)


def test_partition_uses_decision_time_and_requested_bounds() -> None:
    module = _load_script()
    args = module._parser().parse_args(
        [
            *_required_arguments(),
            "--data-start",
            "2026-07-28T00:00:00Z",
            "--fresh-start",
            "2026-07-28T01:00:00Z",
            "--data-end",
            "2026-07-28T02:00:00Z",
        ]
    )
    decisions = pd.to_datetime(
        [
            "2026-07-27T23:59:59Z",
            "2026-07-28T00:00:00Z",
            "2026-07-28T01:00:00Z",
            "2026-07-28T02:00:00Z",
        ],
        utc=True,
    )
    events = pd.DataFrame(
        {
            "label_time_utc": decisions - pd.Timedelta(minutes=5),
            "decision_time_utc": decisions,
            "recipe_id": ["before", "development", "fresh", "after"],
        }
    )

    development, fresh = module._partition_events(events, args)

    assert development["recipe_id"].tolist() == ["development"]
    assert fresh["recipe_id"].tolist() == ["fresh"]
