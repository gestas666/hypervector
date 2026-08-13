from __future__ import annotations

from dataclasses import asdict

from hypervector.research.low_tf_asset_tuning_models import (
    DevelopmentTrialSummary,
    LowTfAssetTrial,
    TrendEntryShape,
    TrendExitShape,
    TuningTrialResult,
)
from hypervector.research.low_tf_asset_tuning_reporting import (
    build_tuning_artifact,
    development_neighbor_sensitivity,
)


def _trial(lookback: int) -> LowTfAssetTrial:
    return LowTfAssetTrial(
        "ETH",
        "long",
        TrendEntryShape(lookback, 13, 34, 20.0, 8.0),
        TrendExitShape(80.0, 2.0, 24),
    )


def _result(trial: LowTfAssetTrial, net: float) -> TuningTrialResult:
    return TuningTrialResult(
        trial.trial_id,
        trial.symbol,
        trial.side,
        "development",
        "nominal",
        8,
        8,
        5,
        3,
        net,
        1.4 if net > 0.0 else 0.7,
        2.0,
        10.0,
        -1.0,
        0,
        0,
        (("2025-08", net),),
    )


def _summary(trial: LowTfAssetTrial, rank: int) -> DevelopmentTrialSummary:
    return DevelopmentTrialSummary(
        trial.trial_id,
        trial.symbol,
        trial.side,
        rank,
        1,
        1,
        10.0,
        10.0,
        1.4,
        2.0,
        8,
        1.3,
        0,
    )


def test_neighbor_sensitivity_counts_direct_positive_neighbors() -> None:
    left, center, right = (_trial(value) for value in (24, 48, 120))
    results = (_result(left, 5.0), _result(center, 10.0), _result(right, -2.0))

    sensitivity = development_neighbor_sensitivity(
        center, (left, center, right), results
    )

    assert sensitivity == {
        "evaluated_neighbors": 2,
        "positive_neighbors": 1,
        "positive_neighbor_fraction": 0.5,
    }


def test_artifact_is_report_only_and_retains_every_development_trial() -> None:
    first, second = _trial(24), _trial(48)
    trials = (first, second)
    development = (_result(first, 10.0), _result(second, -2.0))
    summaries = (_summary(first, 1), _summary(second, 2))

    artifact = build_tuning_artifact(
        run_id="eth_sol_test_v1",
        source_identity={"ETH": {"bars_sha256": "abc"}},
        trials=trials,
        development_results=development,
        development_summaries=summaries,
        selected_trials=(first,),
        replay_results=(),
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["report_only"] is True
    assert artifact["declared_trial_count"] == 2
    assert artifact["retained_development_result_count"] == 2
    assert artifact["selected_trial_ids"] == [first.trial_id]
    expected = [asdict(development[0]), asdict(development[1])]
    for row in expected:
        row.pop("trade_records")
    assert artifact["development_results"] == expected
    assert all("trade_records" not in row for row in artifact["development_results"])
