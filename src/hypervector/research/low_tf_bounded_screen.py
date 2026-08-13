"""Immutable evidence schema for bounded development-only challengers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class BoundedCellResult:
    """One asset, family, side, and friction development result."""

    partition: str
    symbol: str
    family: str
    side: str
    friction: str
    signal_count: int
    completed_trades: int
    wins: int
    losses: int
    net_pnl_usd: float
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    rejections: int
    net_without_largest_winner_usd: float


def build_bounded_frozen_artifact(
    *,
    run_id: str,
    start_utc: str,
    end_utc: str,
    cells: tuple[BoundedCellResult, ...],
    source_identity: dict[str, object],
) -> dict[str, object]:
    """Return all frozen partitions with no tuning or execution authority."""
    if not run_id.strip() or not cells or not source_identity:
        raise ValueError("bounded artifact requires run, cells, and source identity")
    _require_friction_pairs(cells)
    partitions = ["development", "validation", "pseudo_holdout"]
    if {cell.partition for cell in cells} != set(partitions):
        raise ValueError("bounded artifact requires all frozen partitions")
    return {
        "schema_version": "low_tf_bounded_frozen_replay_v1",
        "run_id": run_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "development_start_utc": start_utc,
        "development_end_utc": end_utc,
        "evaluated_partitions": partitions,
        "parameter_updates_after_development": False,
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "source_identity": source_identity,
        "cells": [asdict(cell) for cell in cells],
    }


def _require_friction_pairs(cells: tuple[BoundedCellResult, ...]) -> None:
    """Require both frozen friction scenarios for every strategy cell."""
    expected = {"nominal_13bps", "stress_20bps"}
    grouped: dict[tuple[str, str, str], set[str]] = {}
    for cell in cells:
        identity = (cell.partition, cell.symbol, cell.family, cell.side)
        grouped.setdefault(identity, set()).add(cell.friction)
    incomplete = [
        identity for identity, values in grouped.items() if values != expected
    ]
    if incomplete:
        raise ValueError(
            f"bounded cells require nominal and stress pairs: {incomplete}"
        )
