#!/usr/bin/env python3
"""Publish immutable full-roster v43 friction and stop-wave stress."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import sys

import duckdb

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.v43_portfolio_friction_stress import (
    build_v43_portfolio_friction_stress,
)

Record = Mapping[str, object]
_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_VENUE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v40_growth_sizing_stress_20260811T0200Z.json"
)
_CHECKPOINT = Path("data/runtime/bidirectional_cohort/latest_checkpoint.json")
_DATABASE = Path("data/research/market.duckdb")
_OUTPUT = Path(
    "data/logs/research/bidirectional_cohort/"
    "v43_portfolio_friction_stress_20260811_v2.json"
)
_HIP3_INDEX = "hip3_breakout_pressure_sp500_spcx_bidirectional_v1"
_ADVERSE_EXITS = frozenset({"protective_stop", "reduce_only_close"})


def build_parser() -> argparse.ArgumentParser:
    """Build a mutation-incapable report command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=_PROFILE)
    parser.add_argument("--venue-stress", type=Path, default=_VENUE)
    parser.add_argument("--checkpoint", type=Path, default=_CHECKPOINT)
    parser.add_argument("--database", type=Path, default=_DATABASE)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--schema-version", default="v43_portfolio_friction_stress_v1")
    parser.add_argument(
        "--account-values-usd", type=float, nargs="+", default=[500.0, 5_000.0]
    )
    return parser


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
            select snapshot_observed_at_utc, trade_id, symbol, strategy_id,
                   operation, slippage_bps, acknowledgement_latency_ms
            from cohort_live_attributed_fills
            order by snapshot_observed_at_utc, trade_id, symbol, operation
            """
        ).fetchall()
    finally:
        connection.close()
    return tuple(_fill_row(row) for row in result)


def _fill_row(row: tuple[object, ...]) -> dict[str, object]:
    return {
        "snapshot_observed_at_utc": str(row[0]),
        "trade_id": row[1],
        "symbol": row[2],
        "strategy_id": row[3],
        "operation": row[4],
        "slippage_bps": row[5],
        "acknowledgement_latency_ms": row[6],
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
        and row.get("strategy_id") == _HIP3_INDEX
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


def run(args: argparse.Namespace) -> int:
    """Build, reconcile, and atomically publish one immutable report."""
    config = load_multi_asset_live_config(args.profile, mode="observe")
    friction, evidence = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    report = build_v43_portfolio_friction_stress(
        args.profile,
        venue_stress_path=args.venue_stress,
        execution_friction=friction,
        account_values_usd=args.account_values_usd,
        schema_version=args.schema_version,
    )
    final_friction, final_evidence = collect_execution_friction(
        args.database, args.checkpoint, symbols=config.symbols
    )
    if (friction, evidence) != (final_friction, final_evidence):
        raise RuntimeError("v43 execution evidence changed during evaluation")
    report.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "execution_friction_evidence": friction,
            "source_execution_evidence": evidence,
            "inputs": {
                "profile": _file_identity(args.profile),
                "venue_stress": _file_identity(args.venue_stress),
                "checkpoint": _file_identity(args.checkpoint),
            },
        }
    )
    write_immutable_json(args.output, report)
    return 0


def _source_execution(checkpoint: Path) -> Record:
    document = _mapping(json.loads(checkpoint.read_text()), "checkpoint")
    audit = _mapping(document.get("audit"), "checkpoint audit")
    archive = _mapping(audit.get("portfolio_archive"), "portfolio archive")
    return _mapping(archive.get("source_execution"), "source execution")


def _rows_sha256(rows: Sequence[Record]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _file_identity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


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


def main(argv: Sequence[str] | None = None) -> int:
    """Return a bounded report failure without exposing live authority."""
    try:
        return run(build_parser().parse_args(argv))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
        duckdb.Error,
    ) as exc:
        print(f"v43 portfolio friction stress failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
