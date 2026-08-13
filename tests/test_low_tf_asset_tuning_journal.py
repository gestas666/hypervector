from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from hypervector.research.low_tf_asset_tuning_journal import LowTfTuningJournal
from hypervector.research.low_tf_asset_tuning_models import (
    LowTfAssetTrial,
    TrendEntryShape,
    TrendExitShape,
    TuningTrialResult,
)


def _trial() -> LowTfAssetTrial:
    return LowTfAssetTrial(
        "SOL",
        "short",
        TrendEntryShape(48, 13, 34, 20.0, 8.0),
        TrendExitShape(80.0, 2.0, 24),
    )


def _result(trial: LowTfAssetTrial) -> TuningTrialResult:
    return TuningTrialResult(
        trial.trial_id,
        trial.symbol,
        trial.side,
        "development",
        "nominal",
        1,
        1,
        1,
        0,
        5.0,
        None,
        0.2,
        0.1,
        0.0,
        0,
        0,
        (("2025-08", 5.0),),
        ({"exit_time_utc": "2025-08-01T00:05:00+00:00", "net_pnl_usd": 5.0},),
    )


def test_journal_appends_trials_results_and_trades_atomically(tmp_path: Path) -> None:
    trial = _trial()
    result = _result(trial)
    path = tmp_path / "trials.duckdb"
    journal = LowTfTuningJournal(path)

    journal.write_run(
        run_id="eth_sol_tuning_test_v1",
        source_identity={"SOL": {"bars_sha256": "abc"}},
        trials=(trial,),
        development_results=(result,),
        selected_trial_ids=(trial.trial_id,),
        replay_results=(),
    )

    with duckdb.connect(str(path), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM low_tf_tuning_runs"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM low_tf_tuning_trials"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM low_tf_tuning_results"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM low_tf_tuning_trades"
        ).fetchone() == (1,)
    with pytest.raises(ValueError, match="already exists"):
        journal.write_run(
            run_id="eth_sol_tuning_test_v1",
            source_identity={"SOL": {"bars_sha256": "abc"}},
            trials=(trial,),
            development_results=(result,),
            selected_trial_ids=(trial.trial_id,),
            replay_results=(),
        )


def test_journal_reloads_development_metrics_without_embedded_trades(
    tmp_path: Path,
) -> None:
    trial = _trial()
    result = _result(trial)
    journal = LowTfTuningJournal(tmp_path / "trials.duckdb")
    journal.write_run(
        run_id="source_development_v1",
        source_identity={"SOL": {"bars_sha256": "abc"}},
        trials=(trial,),
        development_results=(result,),
        selected_trial_ids=(),
        replay_results=(),
    )

    source, trials, results = journal.load_development_run("source_development_v1")

    assert source == {"SOL": {"bars_sha256": "abc"}}
    assert trials == (trial,)
    assert results[0].trial_id == trial.trial_id
    assert results[0].net_pnl_usd == result.net_pnl_usd
    assert results[0].trade_records == ()
