"""Append-only DuckDB journal for four-Pine strategy screens."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from hypervector.research.low_tf_multi_asset_contract import SegmentName
from hypervector.research.pine_stack_screen import PineStackScreenCell

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pine_stack_screen_runs (
    run_id VARCHAR PRIMARY KEY,
    segment VARCHAR NOT NULL,
    source_identity_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    report_only BOOLEAN NOT NULL CHECK (report_only),
    execution_authority VARCHAR NOT NULL CHECK (execution_authority = 'none')
);
CREATE TABLE IF NOT EXISTS pine_stack_screen_cells (
    run_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    bar_minutes INTEGER NOT NULL,
    candidate VARCHAR NOT NULL,
    exit_variant VARCHAR NOT NULL,
    metrics_json JSON NOT NULL,
    PRIMARY KEY (run_id, symbol, bar_minutes, candidate, exit_variant)
);
CREATE TABLE IF NOT EXISTS pine_stack_screen_trades (
    run_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    bar_minutes INTEGER NOT NULL,
    candidate VARCHAR NOT NULL,
    exit_variant VARCHAR NOT NULL,
    trade_index INTEGER NOT NULL,
    trade_json JSON NOT NULL,
    PRIMARY KEY (
        run_id, symbol, bar_minutes, candidate, exit_variant, trade_index
    )
);
"""


class PineStackScreenJournal:
    """Persist immutable four-Pine runs with trade rows stored separately."""

    def __init__(self, path: Path) -> None:
        """Create the journal schema without replacing existing evidence."""
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(path)) as connection:
            connection.execute(_SCHEMA)

    def write_run(
        self,
        *,
        run_id: str,
        segment: SegmentName,
        source_identity: tuple[dict[str, object], ...],
        cells: tuple[PineStackScreenCell, ...],
    ) -> None:
        """Atomically append one complete report-only Pine stack run."""
        _validate_run(run_id, segment, source_identity, cells)
        with duckdb.connect(str(self.path)) as connection:
            if _run_exists(connection, run_id):
                raise ValueError(f"Pine stack screen run already exists: {run_id}")
            connection.begin()
            connection.execute(
                "INSERT INTO pine_stack_screen_runs VALUES (?, ?, ?, ?, TRUE, 'none')",
                [
                    run_id,
                    segment,
                    json.dumps(source_identity, sort_keys=True, default=str),
                    datetime.now(UTC),
                ],
            )
            connection.executemany(
                "INSERT INTO pine_stack_screen_cells VALUES (?, ?, ?, ?, ?, ?)",
                [_cell_row(run_id, cell) for cell in cells],
            )
            trade_rows = [row for cell in cells for row in _trade_rows(run_id, cell)]
            if trade_rows:
                connection.executemany(
                    "INSERT INTO pine_stack_screen_trades VALUES (?, ?, ?, ?, ?, ?, ?)",
                    trade_rows,
                )
            connection.commit()


def _run_exists(connection: duckdb.DuckDBPyConnection, run_id: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM pine_stack_screen_runs WHERE run_id = ?", [run_id]
    ).fetchone()
    if row is None or not isinstance(row[0], int):
        raise RuntimeError("invalid Pine stack screen run count")
    return int(row[0]) > 0


def _cell_row(run_id: str, cell: PineStackScreenCell) -> tuple[object, ...]:
    metrics = asdict(cell)
    metrics.pop("trade_records")
    return (
        run_id,
        cell.symbol,
        cell.bar_minutes,
        cell.candidate,
        cell.exit_variant,
        json.dumps(metrics, sort_keys=True, default=str),
    )


def _trade_rows(
    run_id: str,
    cell: PineStackScreenCell,
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            run_id,
            cell.symbol,
            cell.bar_minutes,
            cell.candidate,
            cell.exit_variant,
            index,
            json.dumps(trade, sort_keys=True, default=str),
        )
        for index, trade in enumerate(cell.trade_records)
    )


def _validate_run(
    run_id: str,
    segment: SegmentName,
    source_identity: tuple[dict[str, object], ...],
    cells: tuple[PineStackScreenCell, ...],
) -> None:
    if not run_id.strip() or not source_identity or not cells:
        raise ValueError("Pine stack run identity, sources, and cells are required")
    if segment not in {"development", "validation", "pseudo_holdout"}:
        raise ValueError(f"unsupported Pine stack segment: {segment}")
    identities = {
        (cell.symbol, cell.bar_minutes, cell.candidate, cell.exit_variant)
        for cell in cells
    }
    if len(identities) != len(cells):
        raise ValueError("Pine stack cells contain duplicate identities")
    if any(cell.execution_authority != "none" for cell in cells):
        raise ValueError("Pine stack cells must have no execution authority")
