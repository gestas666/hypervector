"""Append-only DuckDB journal for four-Pine parameter tuning."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from hypervector.research.low_tf_multi_asset_contract import SegmentName
from hypervector.research.pine_stack_tuning import (
    PineStackTuningResult,
    PineStackTuningSummary,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pine_stack_tuning_runs (
    run_id VARCHAR PRIMARY KEY,
    segment VARCHAR NOT NULL,
    source_identity_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    report_only BOOLEAN NOT NULL CHECK (report_only),
    execution_authority VARCHAR NOT NULL CHECK (execution_authority = 'none')
);
CREATE TABLE IF NOT EXISTS pine_stack_tuning_trials (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    rank INTEGER NOT NULL,
    parameters_json JSON NOT NULL,
    metrics_json JSON NOT NULL,
    net_pnl_usd DOUBLE NOT NULL,
    profit_factor DOUBLE,
    maximum_drawdown_pct DOUBLE NOT NULL,
    completed_trades INTEGER NOT NULL,
    liquidations INTEGER NOT NULL,
    PRIMARY KEY (run_id, trial_id)
);
CREATE TABLE IF NOT EXISTS pine_stack_tuning_trades (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    trade_index INTEGER NOT NULL,
    trade_json JSON NOT NULL,
    PRIMARY KEY (run_id, trial_id, trade_index)
);
"""


class PineStackTuningJournal:
    """Persist complete immutable tuning surfaces and their trade ledgers."""

    def __init__(self, path: Path) -> None:
        """Initialize the append-only schema without replacing evidence."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(_SCHEMA)

    def write_run(
        self,
        *,
        run_id: str,
        segment: SegmentName,
        source_identity: dict[str, object],
        results: tuple[PineStackTuningResult, ...],
        summaries: tuple[PineStackTuningSummary, ...],
    ) -> None:
        """Atomically append one complete tuning run or reject duplicates."""
        _validate_run(run_id, segment, results, summaries)
        with duckdb.connect(str(self.path)) as connection:
            if _run_exists(connection, run_id):
                raise ValueError(f"Pine tuning run already exists: {run_id}")
            connection.begin()
            _insert_run(connection, run_id, segment, source_identity)
            _insert_trials(connection, run_id, results, summaries)
            _insert_trades(connection, run_id, results)
            connection.commit()


def _insert_run(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    segment: SegmentName,
    source_identity: dict[str, object],
) -> None:
    connection.execute(
        "INSERT INTO pine_stack_tuning_runs VALUES (?, ?, ?, ?, TRUE, 'none')",
        [
            run_id,
            segment,
            json.dumps(source_identity, sort_keys=True, default=str),
            datetime.now(UTC),
        ],
    )


def _insert_trials(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    results: tuple[PineStackTuningResult, ...],
    summaries: tuple[PineStackTuningSummary, ...],
) -> None:
    summary_by_id = {summary.trial_id: summary for summary in summaries}
    rows = [
        _trial_row(run_id, result, summary_by_id[result.config.trial_id])
        for result in results
    ]
    connection.executemany(
        "INSERT INTO pine_stack_tuning_trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def _trial_row(
    run_id: str,
    result: PineStackTuningResult,
    summary: PineStackTuningSummary,
) -> tuple[object, ...]:
    metrics = asdict(result)
    metrics.pop("trade_records")
    metrics.pop("config")
    return (
        run_id,
        result.config.trial_id,
        summary.rank,
        json.dumps(asdict(result.config), sort_keys=True),
        json.dumps(metrics, sort_keys=True, default=str),
        result.net_pnl_usd,
        result.profit_factor,
        result.maximum_drawdown_pct,
        result.completed_trades,
        result.liquidations,
    )


def _insert_trades(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    results: tuple[PineStackTuningResult, ...],
) -> None:
    rows = [
        (
            run_id,
            result.config.trial_id,
            index,
            json.dumps(trade, sort_keys=True, default=str),
        )
        for result in results
        for index, trade in enumerate(result.trade_records)
    ]
    if rows:
        connection.executemany(
            "INSERT INTO pine_stack_tuning_trades VALUES (?, ?, ?, ?)", rows
        )


def _run_exists(connection: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM pine_stack_tuning_runs WHERE run_id = ?", [run_id]
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid Pine tuning run count")
    return int(row[0]) > 0


def _validate_run(
    run_id: str,
    segment: SegmentName,
    results: tuple[PineStackTuningResult, ...],
    summaries: tuple[PineStackTuningSummary, ...],
) -> None:
    if not run_id.strip() or segment not in {
        "development",
        "validation",
        "pseudo_holdout",
    }:
        raise ValueError("Pine tuning requires a declared segment and run identity")
    result_ids = {result.config.trial_id for result in results}
    summary_ids = {summary.trial_id for summary in summaries}
    if not results or result_ids != summary_ids or len(result_ids) != len(results):
        raise ValueError("Pine tuning journal requires one summary per unique trial")
    if any(result.execution_authority != "none" for result in results):
        raise ValueError("Pine tuning results must have no execution authority")
