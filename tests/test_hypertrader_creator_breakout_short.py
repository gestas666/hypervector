"""Contracts for the creator's report-only BK_DOWN short challenger."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.research.hypertrader_creator_breakout_short import (
    CREATOR_RECIPE_REVISION,
    creator_breakout_short_leverage_configs,
    extract_creator_breakout_short_events,
)
from hypervector.research.maker_replay_contract import (
    maker_replay_contract,
    target_price_for_entry,
)


def _load_replay_script() -> ModuleType:
    path = Path("scripts/hypervelocity_hypertrader_maker_replay.py")
    spec = importlib.util.spec_from_file_location("creator_short_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load maker replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creator_short_extracts_only_qualified_breakout_down_onsets() -> None:
    index = pd.date_range("2026-07-29T00:00:00Z", periods=8, freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": [
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
                "RANGE",
                "BREAKOUT",
                "RANGE",
                "BREAKOUT",
                "BREAKOUT",
            ],
            "secondary_code": [
                None,
                "BK_DOWNWARD",
                "BK_DOWNWARD",
                None,
                "BK_UPWARD",
                None,
                "BK_DOWNWARD",
                "BK_DOWNWARD",
            ],
            "confidence": [0.5, 0.70, 0.90, 0.5, 0.95, 0.5, 0.69, 0.90],
        },
        index=index,
    )

    events = extract_creator_breakout_short_events(labels)

    assert events["label_time_utc"].tolist() == [index[1]]
    assert events["decision_time_utc"].tolist() == [index[1] + pd.Timedelta(minutes=5)]
    assert events["recipe_id"].tolist() == ["creator_bk_down_short_conf70"]
    assert events["side"].tolist() == ["short"]
    assert events["maximum_hold_seconds"].tolist() == [86_400.0]
    assert events["confidence"].tolist() == [0.70]


def test_creator_short_replay_contract_matches_upstream_paper_recipe() -> None:
    module = _load_replay_script()
    family = "creator-breakout-down-confidence-70"
    args = module._parser().parse_args(
        [
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
            "--candidate-family",
            family,
            "--out",
            "maker.json",
        ]
    )

    contract = module._experiment_contract(family)
    config = module._creator_breakout_short_config(60.0, "trade-through")

    assert args.candidate_family == family
    assert contract["creator_recipe_revision"] == CREATOR_RECIPE_REVISION
    assert contract["allocation_fraction"] == 0.10
    assert contract["leverage"] == 40.0
    assert contract["gross_margin_target_pct"] == 8.0
    assert contract["maximum_hold_seconds"] == 86_400.0
    assert contract["stop_policy"] == "none"
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert config.margin_fraction == 0.10
    assert config.leverage == 40.0
    assert config.target_margin_pct == 8.0
    assert config.target_price_points == 130.0
    assert config.same_direction_reentry_policy == "regime_reset"

    target = target_price_for_entry(
        maker_replay_contract(config),
        entry_price=100_000.0,
        direction="short",
        target_price_points=config.target_price_points,
    )
    assert target == 99_870.0


def test_creator_short_leverage_surface_changes_only_leverage() -> None:
    configs = creator_breakout_short_leverage_configs(
        initial_equity=15_000.0,
        entry_eligibility_seconds=60.0,
        fill_rule="trade-through",
    )

    assert tuple(configs) == (
        "lev20",
        "lev25",
        "lev30",
        "lev35",
        "lev40_source_control",
    )
    assert [config.leverage for config in configs.values()] == [
        20.0,
        25.0,
        30.0,
        35.0,
        40.0,
    ]
    assert all(config.initial_equity == 15_000.0 for config in configs.values())
    assert all(config.margin_fraction == 0.10 for config in configs.values())
    assert all(config.target_margin_pct == 8.0 for config in configs.values())
    assert all(config.target_price_points == 130.0 for config in configs.values())
    assert all(config.fixed_margin_stop_pct is None for config in configs.values())


def test_creator_short_leverage_surface_is_report_only_cli_family() -> None:
    module = _load_replay_script()
    family = "creator-breakout-down-leverage-surface"
    args = module._parser().parse_args(
        [
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
            "--candidate-family",
            family,
            "--out",
            "maker.json",
        ]
    )

    contract = module._experiment_contract(args.candidate_family)

    assert contract["leverage_surface"] == [20.0, 25.0, 30.0, 35.0, 40.0]
    assert contract["report_only"] is True
    assert contract["runtime_strategy_changed"] is False
    assert contract["selection_is_promotion"] is False
