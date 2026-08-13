"""Contracts for the Hypervelocity entry-filter factorial."""

from __future__ import annotations

from dataclasses import asdict
import importlib
import importlib.util
import math
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.maker_replay_models import (
    MakerReplayLifecycle,
    MakerReplayReport,
)

_MODULE = "hypervector.research.hypervelocity_entry_filter_factorial"


def _module() -> object:
    return importlib.import_module(_MODULE)


def _script() -> ModuleType:
    path = Path("scripts/hypervelocity_entry_filter_factorial.py")
    spec = importlib.util.spec_from_file_location("entry_filter_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load entry-filter script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decision_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range("2026-01-01", periods=7, freq="1min", tz="UTC")
    canonical = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP"] * 7,
            "state_5m": ["TREND_UP"] * 7,
            "structural_direction": ["long"] * 7,
            "entry_direction": ["long"] * 7,
            "reason": ["5m_primary_trend"] * 7,
            "bbwp_percentile": [10.0] + [30.0] * 6,
        },
        index=index,
    )
    context = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP"] * 7,
            "bbwp_percentile": [30.0, 30.0, 30.0, 10.0, 30.0, 30.0, 30.0],
        },
        index=index,
    )
    return canonical, context


def test_factorial_decisions_are_exact_and_independent() -> None:
    module = _module()
    canonical, context = _decision_frames()

    grid = module.entry_filter_decision_grid(
        canonical,
        context,
        compression_threshold=25.0,
        recovery_age_bars=6,
    )

    assert list(grid) == [
        "canonical_control",
        "hard_bbwp_only",
        "recovery6_only",
        "hard_bbwp_recovery6",
    ]
    assert grid["canonical_control"]["entry_direction"].notna().sum() == 7
    assert grid["hard_bbwp_only"]["entry_direction"].notna().sum() == 6
    assert grid["recovery6_only"]["entry_direction"].notna().sum() == 1
    assert grid["hard_bbwp_recovery6"]["entry_direction"].notna().sum() == 1
    assert canonical["entry_direction"].notna().all()


def test_minimum_entry_strength_is_research_only_entry_mask() -> None:
    module = _module()
    canonical, _ = _decision_frames()
    canonical["regime_strength_percentile"] = [49.0, 50.0, 75.0, 10.0, 80.0, 1.0, 99.0]

    result = module.apply_minimum_entry_strength(canonical, minimum=50.0)

    assert result["entry_direction"].tolist() == [
        None,
        "long",
        "long",
        None,
        "long",
        None,
        "long",
    ]
    assert result["structural_direction"].eq("long").all()
    assert result["minimum_entry_strength_wait"].tolist() == [
        True,
        False,
        False,
        True,
        False,
        True,
        False,
    ]
    assert canonical["entry_direction"].notna().all()


@pytest.mark.parametrize("minimum", [-1.0, 101.0, math.nan])
def test_minimum_entry_strength_rejects_invalid_threshold(minimum: float) -> None:
    module = _module()
    canonical, _ = _decision_frames()
    canonical["regime_strength_percentile"] = 50.0

    with pytest.raises(ValueError, match="within"):
        module.apply_minimum_entry_strength(canonical, minimum=minimum)


def test_factorial_configs_are_execution_identical() -> None:
    module = _module()

    configs = module.entry_filter_candidate_configs()

    assert list(configs) == list(module.ENTRY_FILTER_CANDIDATES)
    first = asdict(next(iter(configs.values())))
    assert all(asdict(config) == first for config in configs.values())
    assert first["initial_equity"] == 10_000.0
    assert first["fill_rule"] == "trade-through"
    assert first["entry_ttl_seconds"] == 300.0
    assert first["reentry_cooldown_seconds"] == 300.0


def test_source_attribution_reports_match_opposite_and_filter_reason() -> None:
    module = _module()
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    positions = pd.DataFrame(
        {
            "open_time_utc": [
                "2026-01-01T00:01:30Z",
                "2026-01-01T00:02:30Z",
            ],
            "side": ["long", "short"],
        }
    )
    decisions = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP", "RANGE"],
            "state_5m": ["TREND_UP", "RANGE"],
            "structural_direction": ["long", "short"],
            "entry_direction": ["long", None],
            "reason": ["5m_primary_trend", "5m_bbwp_compression_range"],
            "bbwp_5m_hard_range": [False, True],
            "bbwp_1m_recovery_wait": [False, False],
        },
        index=index,
    )

    result = module.source_entry_attribution(
        positions,
        {"candidate": decisions},
    )["candidate"]

    assert result["source_entries"] == 2
    assert result["direction_matches"] == 1
    assert result["direction_match_basis"] == "entry_direction"
    assert result["structural_direction_matches"] == 2
    assert result["structural_opposite_directions"] == 0
    assert result["structural_no_direction"] == 0
    assert result["opposite_directions"] == 0
    assert result["no_candidate"] == 1
    assert result["no_candidate_reasons"] == {"hard_bbwp_range": 1}


def _report_with_fills() -> MakerReplayReport:
    lifecycles = (
        MakerReplayLifecycle(
            0,
            "long",
            "2026-01-01T00:01:00+00:00",
            "2026-01-01T00:01:01+00:00",
            "2026-01-01T00:01:20+00:00",
            None,
            "open",
            100.0,
            None,
            28.0,
            None,
            None,
        ),
        MakerReplayLifecycle(
            1,
            "short",
            "2026-01-01T00:20:00+00:00",
            "2026-01-01T00:20:01+00:00",
            "2026-01-01T00:20:20+00:00",
            None,
            "open",
            100.0,
            None,
            28.0,
            None,
            None,
        ),
    )
    return MakerReplayReport(
        "touch",
        2,
        0,
        2,
        2,
        0,
        0,
        0,
        0,
        2,
        100.0,
        100.0,
        tuple(row.submitted_time_utc for row in lifecycles),
        (),
        lifecycles,
        (),
    )


def test_source_fill_proximity_is_one_to_one_by_direction() -> None:
    module = _module()
    positions = pd.DataFrame(
        {
            "open_time_utc": [
                "2026-01-01T00:01:30Z",
                "2026-01-01T00:02:00Z",
                "2026-01-01T00:25:00Z",
            ],
            "side": ["long", "long", "short"],
        }
    )

    result = module.source_fill_proximity(positions, _report_with_fills())

    assert result == {"5m": 2, "10m": 2, "30m": 2}


def test_source_fill_proximity_maximizes_one_to_one_matches() -> None:
    module = _module()
    source = pd.DataFrame(
        {
            "event_time": pd.to_datetime(
                ["2026-01-01T00:04:00Z", "2026-01-01T00:06:00Z"],
                utc=True,
            ),
            "side": ["long", "long"],
        }
    )
    fills = [
        (pd.Timestamp("2026-01-01T00:00:00Z"), "long"),
        (pd.Timestamp("2026-01-01T00:05:00Z"), "long"),
    ]

    result = module._proximity_matches(
        source,
        fills,
        pd.Timedelta(minutes=5),
    )

    assert result == 2


def test_script_contract_keeps_runtime_and_ml_read_only() -> None:
    module = _script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "configs/hypervelocity_faithful.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--out",
            "report.json",
        ]
    )

    assert module._experiment_contract(args)["report_only"] is True
    assert module._experiment_contract(args)["runtime_strategy_changed"] is False
    assert module._metalabel_policy(args.config) == {
        "mode": "observe",
        "may_filter": False,
        "may_scale": False,
    }


def test_script_strength_followup_contract_is_exact_pair() -> None:
    module = _script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "configs/hypervelocity_faithful.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--minimum-entry-strength",
            "50",
            "--out",
            "report.json",
        ]
    )

    contract = module._experiment_contract(
        args,
        module.STRENGTH_FOLLOWUP_CANDIDATES,
    )

    assert contract["candidate_order"] == [
        "hard_bbwp_recovery6_control",
        "hard_bbwp_recovery6_strength50",
    ]
    assert contract["minimum_entry_strength"] == 50.0
    assert contract["runtime_strategy_changed"] is False
