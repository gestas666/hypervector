"""Command-contract tests for creator entry-time ranking research."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_source_entry_ranking.py")
    spec = importlib.util.spec_from_file_location("source_entry_ranking_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source entry ranking script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_freezes_required_source_and_evidence_bounds() -> None:
    module = _load_script()

    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--supplemental-positions",
            "supplemental.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-07-09T04:50:00Z",
            "--end",
            "2026-07-25T18:51:00Z",
            "--out",
            "report.json",
        ]
    )

    assert args.bars == Path("bars.parquet")
    assert args.supplemental_positions == Path("supplemental.csv")
    assert args.start.isoformat() == "2026-07-09T04:50:00+00:00"
    assert args.end.isoformat() == "2026-07-25T18:51:00+00:00"


def test_assessment_requires_cross_day_association_and_shape() -> None:
    module = _load_script()
    rows: list[dict[str, object]] = []
    values = {
        "uniform": (0.50, 0.10),
        "strength_only": (0.55, 0.15),
        "logistic": (0.70, 0.40),
        "lightgbm": (0.65, 0.30),
    }
    for day in ("2026-01-02", "2026-01-03", "2026-01-04"):
        for model, (percentile, recall) in values.items():
            rows.append(
                {
                    "test_day_utc": day,
                    "model": model,
                    "test_positives": 1,
                    "positive_percentile_mean": percentile,
                    "top_10pct_recall": recall,
                }
            )

    assessment = module._assessment(pd.DataFrame(rows))

    assert assessment["correctness_screen_passed"] is True
    assert assessment["association_screen_passed"] is True
    assert assessment["shape_screen_passed"] is True
    assert assessment["advanced_to_l2_trial"] is True


def test_assessment_rejects_one_day_cluster_and_bottom_quartile_collapse() -> None:
    module = _load_script()
    rows = []
    for day in ("2026-01-02", "2026-01-03", "2026-01-04"):
        for model in ("uniform", "strength_only", "logistic", "lightgbm"):
            percentile = 0.8 if day == "2026-01-04" else 0.2
            rows.append(
                {
                    "test_day_utc": day,
                    "model": model,
                    "test_positives": 1 if day == "2026-01-04" else 0,
                    "positive_percentile_mean": percentile,
                    "top_10pct_recall": 1.0 if day == "2026-01-04" else 0.0,
                }
            )

    assessment = module._assessment(pd.DataFrame(rows))

    assert assessment["correctness_screen_passed"] is False
    assert assessment["association_screen_passed"] is False
    assert assessment["shape_screen_passed"] is False
    assert assessment["advanced_to_l2_trial"] is False
