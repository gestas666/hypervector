"""Canonical all-time live execution-friction extraction for cohort research."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path

import duckdb


Record = Mapping[str, object]
_HIP3_INDEX_PROVIDERS = frozenset(
    {
        "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
    }
)
_ADVERSE_EXITS = frozenset({"protective_stop", "reduce_only_close"})


def collect_execution_friction(
    database: Path,
    checkpoint: Path,
    *,
    symbols: Sequence[str] = ("BTC", "HYPE", "xyz:SP500"),
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    """Extract canonical all-time live slippage with checkpoint reconciliation."""
    source_execution = _source_execution(checkpoint)
    rows = _fill_rows(database)
    expected = _integer(source_execution.get("fill_events"), "source fill events")
    if len(rows) != expected:
        raise ValueError(
            f"execution fill count differs: database={len(rows)} checkpoint={expected}"
        )
    friction = {
        symbol: (
            _sp500_friction(rows)
            if symbol == "xyz:SP500"
            else _symbol_friction(rows, symbol, "exact_symbol")
        )
        for symbol in symbols
    }
    return friction, {
        "canonical_fill_rows": len(rows),
        "canonical_rows_sha256": _rows_sha256(rows),
        "checkpoint_source_execution_sha256": _sha256_text(
            source_execution.get("sha256"), "source execution sha256"
        ),
        "database_path": str(database),
        "checkpoint_path": str(checkpoint),
    }


def _fill_rows(database: Path) -> tuple[dict[str, object], ...]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        result = connection.execute(
            """
            select trade_id, symbol, strategy_id, operation, slippage_bps,
                   acknowledgement_latency_ms
            from cohort_live_attributed_fills
            order by trade_id, symbol, operation
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(_fill_row(row) for row in result)


def _fill_row(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "trade_id": row[0],
        "symbol": row[1],
        "strategy_id": row[2],
        "operation": row[3],
        "slippage_bps": row[4],
        "acknowledgement_latency_ms": row[5],
    }


def _symbol_friction(
    rows: Sequence[Record], symbol: str, scope: str
) -> dict[str, object]:
    exact = tuple(row for row in rows if row.get("symbol") == symbol)
    return {
        "entry": _quantile_record(exact, frozenset({"entry"})),
        "adverse_exit": _quantile_record(exact, _ADVERSE_EXITS),
        "target_exit": _quantile_record(exact, frozenset({"target"})),
        "exit_evidence_scope": scope,
    }


def _sp500_friction(rows: Sequence[Record]) -> dict[str, object]:
    exact = tuple(row for row in rows if row.get("symbol") == "xyz:SP500")
    proxy = tuple(
        row
        for row in rows
        if row.get("symbol") in {"xyz:SP500", "xyz:SPCX"}
        and row.get("strategy_id") in _HIP3_INDEX_PROVIDERS
    )
    return {
        "entry": _quantile_record(exact, frozenset({"entry"})),
        "adverse_exit": _quantile_record(proxy, _ADVERSE_EXITS),
        "target_exit": _quantile_record(exact, frozenset({"target"})),
        "exit_evidence_scope": "same_provider_xyz_spcx_proxy",
    }


def _quantile_record(
    rows: Sequence[Record], operations: frozenset[str]
) -> dict[str, object]:
    values = sorted(
        max(_number(row.get("slippage_bps"), "slippage"), 0.0)
        for row in rows
        if row.get("operation") in operations and row.get("slippage_bps") is not None
    )
    return {
        "sample_count": len(values),
        "p99_bps": None if not values else _quantile(values, 0.99),
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile values must be non-empty")
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _source_execution(checkpoint: Path) -> Record:
    document = _mapping(json.loads(checkpoint.read_text()), "checkpoint")
    audit = _mapping(document.get("audit"), "checkpoint audit")
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    return _mapping(archive.get("source_execution"), "source execution")


def _rows_sha256(rows: Sequence[Record]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _sha256_text(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{label} must be a 64-character string")
    return value
