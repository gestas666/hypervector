"""Append-only DuckDB journal for complete Hulk Smash tuning trials."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from hypervector.research.hulk_smash_autotune import (
    HulkAutotuneResult,
    HulkAutotuneSummary,
    HulkTuneParameters,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hulk_autotune_runs (
    run_id VARCHAR PRIMARY KEY,
    surface VARCHAR NOT NULL,
    source_identity_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    report_only BOOLEAN NOT NULL CHECK (report_only),
    execution_authority VARCHAR NOT NULL CHECK (execution_authority = 'none')
);
CREATE TABLE IF NOT EXISTS hulk_autotune_trials (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    rank INTEGER NOT NULL,
    parameters_json JSON NOT NULL,
    positive_cells INTEGER NOT NULL,
    total_cells INTEGER NOT NULL,
    worst_net_pnl_usd DOUBLE NOT NULL,
    total_net_pnl_usd DOUBLE NOT NULL,
    minimum_profit_factor DOUBLE,
    maximum_drawdown_pct DOUBLE NOT NULL,
    total_trades INTEGER NOT NULL,
    liquidations INTEGER NOT NULL,
    PRIMARY KEY (run_id, trial_id)
);
CREATE TABLE IF NOT EXISTS hulk_autotune_results (
    run_id VARCHAR NOT NULL,
    trial_id VARCHAR NOT NULL,
    fold VARCHAR NOT NULL,
    scenario VARCHAR NOT NULL,
    signal_count INTEGER NOT NULL,
    completed_trades INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    net_pnl_usd DOUBLE NOT NULL,
    profit_factor DOUBLE,
    maximum_drawdown_pct DOUBLE NOT NULL,
    fees_usd DOUBLE NOT NULL,
    funding_cashflow_usd DOUBLE NOT NULL,
    liquidations INTEGER NOT NULL,
    rejections INTEGER NOT NULL,
    PRIMARY KEY (run_id, trial_id, fold, scenario)
);
"""


class HulkAutotuneJournal:
    """Persist complete immutable Hulk tuning matrices in DuckDB."""

    def __init__(self, path: Path) -> None:
        """Initialize the journal schema without replacing existing evidence."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.path)) as connection:
            connection.execute(_SCHEMA)

    def write_run(
        self,
        *,
        run_id: str,
        surface: str,
        source_identity: dict[str, object],
        parameters: tuple[HulkTuneParameters, ...],
        results: tuple[HulkAutotuneResult, ...],
        summaries: tuple[HulkAutotuneSummary, ...],
    ) -> None:
        """Atomically append one complete run or reject duplicate identity."""
        _validate_run(run_id, surface, parameters, results, summaries)
        with duckdb.connect(str(self.path)) as connection:
            if _run_exists(connection, run_id):
                raise ValueError(f"Hulk autotune run already exists: {run_id}")
            connection.begin()
            self._insert_run(connection, run_id, surface, source_identity)
            self._insert_trials(connection, run_id, parameters, summaries)
            self._insert_results(connection, run_id, results)
            connection.commit()

    @staticmethod
    def _insert_run(
        connection: duckdb.DuckDBPyConnection,
        run_id: str,
        surface: str,
        source_identity: dict[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO hulk_autotune_runs VALUES (?, ?, ?, ?, TRUE, 'none')",
            [
                run_id,
                surface,
                json.dumps(source_identity, sort_keys=True, default=str),
                datetime.now(UTC),
            ],
        )

    @staticmethod
    def _insert_trials(
        connection: duckdb.DuckDBPyConnection,
        run_id: str,
        parameters: tuple[HulkTuneParameters, ...],
        summaries: tuple[HulkAutotuneSummary, ...],
    ) -> None:
        by_id = {value.trial_id: value for value in parameters}
        rows = [
            _trial_row(run_id, by_id[summary.trial_id], summary)
            for summary in summaries
        ]
        connection.executemany(
            "INSERT INTO hulk_autotune_trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    @staticmethod
    def _insert_results(
        connection: duckdb.DuckDBPyConnection,
        run_id: str,
        results: tuple[HulkAutotuneResult, ...],
    ) -> None:
        connection.executemany(
            "INSERT INTO hulk_autotune_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(run_id, *asdict(result).values()) for result in results],
        )


def _trial_row(
    run_id: str,
    parameters: HulkTuneParameters,
    summary: HulkAutotuneSummary,
) -> tuple[object, ...]:
    return (
        run_id,
        summary.trial_id,
        summary.rank,
        json.dumps(asdict(parameters), sort_keys=True),
        summary.positive_cells,
        summary.total_cells,
        summary.worst_net_pnl_usd,
        summary.total_net_pnl_usd,
        summary.minimum_profit_factor,
        summary.maximum_drawdown_pct,
        summary.total_trades,
        summary.liquidations,
    )


def _run_exists(connection: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM hulk_autotune_runs WHERE run_id = ?", [run_id]
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid Hulk autotune run count")
    return int(row[0]) > 0


def _validate_run(
    run_id: str,
    surface: str,
    parameters: tuple[HulkTuneParameters, ...],
    results: tuple[HulkAutotuneResult, ...],
    summaries: tuple[HulkAutotuneSummary, ...],
) -> None:
    if not run_id.strip() or not surface.strip():
        raise ValueError("Hulk autotune run and surface identities are required")
    parameter_ids = {value.trial_id for value in parameters}
    result_ids = {value.trial_id for value in results}
    summary_ids = {value.trial_id for value in summaries}
    if not parameters or parameter_ids != result_ids or parameter_ids != summary_ids:
        raise ValueError("Hulk autotune journal requires a complete trial matrix")
