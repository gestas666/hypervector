"""Append-only DuckDB journal for ETH/SOL low-timeframe tuning."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from hypervector.research.low_tf_asset_tuning_models import (
    LowTfAssetTrial,
    TrendEntryShape,
    TrendExitShape,
    TuningTrialResult,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS low_tf_tuning_runs (
    run_id VARCHAR PRIMARY KEY,
    source_identity_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    report_only BOOLEAN NOT NULL CHECK (report_only),
    execution_authority VARCHAR NOT NULL CHECK (execution_authority = 'none')
);
CREATE TABLE IF NOT EXISTS low_tf_tuning_trials (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    side VARCHAR NOT NULL,
    selected BOOLEAN NOT NULL,
    trial_json JSON NOT NULL,
    PRIMARY KEY (run_id, trial_id)
);
CREATE TABLE IF NOT EXISTS low_tf_tuning_results (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    segment VARCHAR NOT NULL,
    scenario VARCHAR NOT NULL,
    evaluation_stage VARCHAR NOT NULL,
    result_json JSON NOT NULL,
    PRIMARY KEY (run_id, trial_id, segment, scenario, evaluation_stage)
);
CREATE TABLE IF NOT EXISTS low_tf_tuning_trades (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    segment VARCHAR NOT NULL,
    scenario VARCHAR NOT NULL,
    evaluation_stage VARCHAR NOT NULL,
    trade_index INTEGER NOT NULL,
    trade_json JSON NOT NULL,
    PRIMARY KEY (
        run_id, trial_id, segment, scenario, evaluation_stage, trade_index
    )
);
"""


class LowTfTuningJournal:
    """Persist complete tuning trials, results, and trades without overwrite."""

    def __init__(self, path: Path) -> None:
        """Create the tuning schema while preserving all existing evidence."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(path)) as connection:
            connection.execute(_SCHEMA)

    def write_run(
        self,
        *,
        run_id: str,
        source_identity: dict[str, object],
        trials: tuple[LowTfAssetTrial, ...],
        development_results: tuple[TuningTrialResult, ...],
        selected_trial_ids: tuple[str, ...],
        replay_results: tuple[TuningTrialResult, ...],
    ) -> None:
        """Atomically append one report-only tuning experiment."""
        _validate_run(
            run_id,
            source_identity,
            trials,
            development_results,
            selected_trial_ids,
            replay_results,
        )
        with duckdb.connect(str(self.path)) as connection:
            if _run_exists(connection, run_id):
                raise ValueError(f"low-timeframe tuning run already exists: {run_id}")
            connection.begin()
            connection.execute(
                "INSERT INTO low_tf_tuning_runs VALUES (?, ?, ?, TRUE, 'none')",
                [
                    run_id,
                    json.dumps(source_identity, sort_keys=True, default=str),
                    datetime.now(UTC),
                ],
            )
            connection.executemany(
                "INSERT INTO low_tf_tuning_trials VALUES (?, ?, ?, ?, ?, ?)",
                _trial_rows(run_id, trials, set(selected_trial_ids)),
            )
            result_rows = (
                *_result_rows(run_id, development_results, "broad_screen"),
                *_result_rows(run_id, replay_results, "minute_replay"),
            )
            if result_rows:
                connection.executemany(
                    "INSERT INTO low_tf_tuning_results VALUES (?, ?, ?, ?, ?, ?)",
                    result_rows,
                )
            trade_rows = (
                *_trade_rows(run_id, development_results, "broad_screen"),
                *_trade_rows(run_id, replay_results, "minute_replay"),
            )
            if trade_rows:
                connection.executemany(
                    "INSERT INTO low_tf_tuning_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                    trade_rows,
                )
            connection.commit()

    def load_development_run(
        self,
        run_id: str,
    ) -> tuple[
        dict[str, object],
        tuple[LowTfAssetTrial, ...],
        tuple[TuningTrialResult, ...],
    ]:
        """Reload immutable broad-screen metrics for corrected selection."""
        with duckdb.connect(str(self.path), read_only=True) as connection:
            run_row = connection.execute(
                "SELECT source_identity_json FROM low_tf_tuning_runs WHERE run_id = ?",
                [run_id],
            ).fetchone()
            if run_row is None:
                raise ValueError(f"low-timeframe tuning run does not exist: {run_id}")
            trial_rows = connection.execute(
                "SELECT trial_json FROM low_tf_tuning_trials WHERE run_id = ? ORDER BY symbol, side, trial_id",
                [run_id],
            ).fetchall()
            result_rows = connection.execute(
                "SELECT result_json FROM low_tf_tuning_results "
                "WHERE run_id = ? AND evaluation_stage = 'broad_screen' "
                "ORDER BY trial_id",
                [run_id],
            ).fetchall()
        source = _json_object(run_row[0])
        trials = tuple(_trial_from_json(row[0]) for row in trial_rows)
        results = tuple(_result_from_json(row[0]) for row in result_rows)
        _validate_reloaded_development(trials, results)
        return source, trials, results


def _run_exists(connection: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM low_tf_tuning_runs WHERE run_id = ?", [run_id]
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid low-timeframe tuning run count")
    return int(row[0]) > 0


def _trial_rows(
    run_id: str,
    trials: tuple[LowTfAssetTrial, ...],
    selected: set[str],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            run_id,
            trial.trial_id,
            trial.symbol,
            trial.side,
            trial.trial_id in selected,
            json.dumps(asdict(trial), sort_keys=True),
        )
        for trial in trials
    )


def _result_rows(
    run_id: str,
    results: tuple[TuningTrialResult, ...],
    stage: str,
) -> tuple[tuple[object, ...], ...]:
    rows: list[tuple[object, ...]] = []
    for result in results:
        payload = asdict(result)
        payload.pop("trade_records")
        rows.append(
            (
                run_id,
                result.trial_id,
                result.segment,
                result.scenario,
                stage,
                json.dumps(payload, sort_keys=True, default=str),
            )
        )
    return tuple(rows)


def _trade_rows(
    run_id: str,
    results: tuple[TuningTrialResult, ...],
    stage: str,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            run_id,
            result.trial_id,
            result.segment,
            result.scenario,
            stage,
            index,
            json.dumps(trade, sort_keys=True, default=str),
        )
        for result in results
        for index, trade in enumerate(result.trade_records)
    )


def _validate_run(
    run_id: str,
    source_identity: dict[str, object],
    trials: tuple[LowTfAssetTrial, ...],
    development: tuple[TuningTrialResult, ...],
    selected_ids: tuple[str, ...],
    replay: tuple[TuningTrialResult, ...],
) -> None:
    if not run_id.strip() or not source_identity or not trials:
        raise ValueError("tuning journal requires run, source, and trial identities")
    trial_ids = {trial.trial_id for trial in trials}
    if len(trial_ids) != len(trials):
        raise ValueError("tuning journal trials contain duplicate identities")
    if {result.trial_id for result in development} != trial_ids:
        raise ValueError("tuning journal must retain every development result")
    selected = set(selected_ids)
    if len(selected) != len(selected_ids) or not selected.issubset(trial_ids):
        raise ValueError("tuning journal selected identities are invalid")
    if any(result.trial_id not in selected for result in replay):
        raise ValueError("tuning replay result is not selected")
    keys = [(result.trial_id, result.segment, result.scenario) for result in replay]
    if len(set(keys)) != len(keys):
        raise ValueError("tuning replay results contain duplicate identities")


def _json_object(value: object) -> dict[str, object]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("tuning journal JSON payload must be an object")
    return payload


def _trial_from_json(value: object) -> LowTfAssetTrial:
    payload = _json_object(value)
    entry = payload.get("entry")
    exit_shape = payload.get("exit")
    if not isinstance(entry, dict) or not isinstance(exit_shape, dict):
        raise ValueError("tuning trial JSON is missing entry or exit shape")
    return LowTfAssetTrial(
        symbol=str(payload.get("symbol")),
        side=str(payload.get("side")),  # type: ignore[arg-type]
        entry=TrendEntryShape(**entry),
        exit=TrendExitShape(**exit_shape),
    )


def _result_from_json(value: object) -> TuningTrialResult:
    payload = _json_object(value)
    monthly = payload.get("monthly_net_pnl_usd")
    if not isinstance(monthly, list):
        raise ValueError("tuning result JSON is missing monthly metrics")
    payload["monthly_net_pnl_usd"] = tuple(
        (str(month), float(net)) for month, net in monthly
    )
    payload["trade_records"] = ()
    return TuningTrialResult(**payload)  # type: ignore[arg-type]


def _validate_reloaded_development(
    trials: tuple[LowTfAssetTrial, ...],
    results: tuple[TuningTrialResult, ...],
) -> None:
    trial_ids = {trial.trial_id for trial in trials}
    result_ids = {result.trial_id for result in results}
    if not trial_ids or len(trial_ids) != len(trials) or trial_ids != result_ids:
        raise ValueError("reloaded development matrix is incomplete or duplicated")
    if any(
        result.segment != "development" or result.scenario != "nominal"
        for result in results
    ):
        raise ValueError("reloaded development matrix has an unexpected segment")
