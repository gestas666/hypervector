#!/usr/bin/env python3
"""Run an immutable, execution-incapable HIP-3 breakout-pressure transfer screen."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hip3_breakout_pressure_reporting import (
    breakout_transfer_report,
    breakout_transfer_trades,
)
from hypervector.research.hip3_breakout_pressure_transfer import (
    run_hip3_breakout_pressure_transfer,
)
from hypervector.research.hip3_midpoint_bars import build_hip3_midpoint_bars
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
)
from hypervector.research.hip3_transfer_sources import attach_official_funding

_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_DEFAULT_DATABASE = Path("data/research/hip3_market.duckdb")
_DEFAULT_SOURCE_REPORT = Path(
    "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json"
)
_DEFAULT_SOURCE_SIDECAR = Path(
    "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.sources.parquet"
)
_DEFAULT_QUALIFICATION = Path(
    "data/logs/research/xyz_sp500_spcx_qualification_20260806T1451Z.json"
)
_DEFAULT_OUTPUT = Path(
    "data/logs/research/hip3_breakout_pressure_transfer_sp500_spcx_v1.json"
)
_DEFAULT_TRADES = Path(
    "data/logs/research/hip3_breakout_pressure_transfer_sp500_spcx_v1.trades.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the read-only transfer-screen command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=_DEFAULT_DATABASE)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--source-report", type=Path, default=_DEFAULT_SOURCE_REPORT)
    parser.add_argument("--source-sidecar", type=Path, default=_DEFAULT_SOURCE_SIDECAR)
    parser.add_argument(
        "--qualification-report", type=Path, default=_DEFAULT_QUALIFICATION
    )
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Run the sealed protocol and publish deterministic new evidence files."""
    _require_inputs(args)
    symbols = tuple(args.symbols or _DEFAULT_SYMBOLS)
    source_report = _load_json(args.source_report)
    qualification = _load_json(args.qualification_report)
    sidecar = pd.read_parquet(args.source_sidecar)
    assets, frictions, attachments = _prepare_assets(
        args.database,
        symbols,
        source_report,
        qualification,
        sidecar,
    )
    result = run_hip3_breakout_pressure_transfer(assets, frictions)
    trades = breakout_transfer_trades(result)
    write_immutable_parquet(args.trades_output, trades)
    evidence = _source_evidence(args, source_report, attachments)
    report = breakout_transfer_report(result, source_evidence=evidence)
    report["generated_at_utc"] = datetime.now(UTC).isoformat()
    report["symbols"] = list(symbols)
    report["selected_trade_sidecar"] = {
        "path": str(args.trades_output.resolve()),
        "rows": len(trades),
        **file_evidence(args.trades_output),
    }
    write_immutable_json(args.output, report)
    return report


def _prepare_assets(
    database: Path,
    symbols: tuple[str, ...],
    source_report: Mapping[str, object],
    qualification: Mapping[str, object],
    sidecar: pd.DataFrame,
) -> tuple[
    tuple[Hip3TransferAsset, ...],
    dict[str, Hip3ExecutionFriction],
    dict[str, object],
]:
    leverages = _leverages(qualification, symbols)
    inherited = _inherited_evidence(source_report, symbols)
    assets: list[Hip3TransferAsset] = []
    frictions: dict[str, Hip3ExecutionFriction] = {}
    attachments: dict[str, object] = {}
    for symbol in symbols:
        midpoint = build_hip3_midpoint_bars(database, symbol=symbol)
        funding = _funding_rows(sidecar, symbol)
        bars, funding_evidence = attach_official_funding(midpoint.bars, funding)
        assets.append(Hip3TransferAsset(symbol, leverages[symbol], bars))
        raw_friction = _mapping(inherited[symbol].get("friction"), "friction")
        frictions[symbol] = Hip3ExecutionFriction(**raw_friction)
        attachments[symbol] = {
            "midpoint_archive": {
                "start_utc": midpoint.archive_start_utc.isoformat(),
                "end_utc": midpoint.archive_end_utc.isoformat(),
                "bundles": midpoint.archive_bundles,
                "book_rows": midpoint.archive_book_rows,
                "bars": len(midpoint.bars),
                "missing_bars": midpoint.missing_bar_count,
            },
            "funding": asdict(funding_evidence),
            "inherited_verified_evidence": inherited[symbol],
        }
    return tuple(assets), frictions, attachments


def _funding_rows(sidecar: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = {"symbol", "record_type", "timestamp", "funding_rate", "source"}
    missing = required.difference(sidecar.columns)
    if missing:
        raise ValueError(f"source sidecar missing columns: {sorted(missing)}")
    selected = sidecar["symbol"].eq(symbol)
    selected &= sidecar["record_type"].eq("official_funding")
    output = sidecar.loc[selected, ["timestamp", "funding_rate", "source"]].copy()
    if output.empty:
        raise ValueError(f"{symbol} source sidecar has no official funding")
    return output


def _leverages(
    report: Mapping[str, object],
    symbols: tuple[str, ...],
) -> dict[str, float]:
    rows = _sequence(report.get("markets"), "qualification markets")
    values = {
        str(row["symbol"]): float(row["max_leverage"])
        for raw in rows
        for row in [_mapping(raw, "qualification market")]
        if row.get("symbol") in symbols
    }
    if set(values) != set(symbols):
        raise ValueError("qualification report does not match requested symbols")
    return values


def _inherited_evidence(
    report: Mapping[str, object],
    symbols: tuple[str, ...],
) -> dict[str, Mapping[str, object]]:
    if report.get("execution_authority") != "none":
        raise ValueError("source report must be execution-incapable")
    rows = _sequence(report.get("source_evidence"), "source evidence")
    values = {
        str(row["symbol"]): row
        for raw in rows
        for row in [_mapping(raw, "source evidence row")]
        if row.get("symbol") in symbols
    }
    if set(values) != set(symbols):
        raise ValueError("source evidence does not match requested symbols")
    return values


def _source_evidence(
    args: argparse.Namespace,
    source_report: Mapping[str, object],
    attachments: Mapping[str, object],
) -> dict[str, object]:
    return {
        "database_path": str(args.database.resolve()),
        "source_report": _file_reference(args.source_report),
        "source_sidecar": _file_reference(args.source_sidecar),
        "qualification_report": _file_reference(args.qualification_report),
        "source_report_schema": source_report.get("schema_version"),
        "assets": dict(attachments),
        "network_calls": False,
        "execution_client_constructed": False,
    }


def _require_inputs(args: argparse.Namespace) -> None:
    for path in (
        args.database,
        args.source_report,
        args.source_sidecar,
        args.qualification_report,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"required HIP-3 input is missing: {path}")
    for path in (args.output, args.trades_output):
        if path.exists():
            raise FileExistsError(f"immutable HIP-3 output exists: {path}")


def _load_json(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, str(path))


def _file_reference(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), **file_evidence(path)}


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def main() -> int:
    """Execute the report-only command and print a path-safe summary."""
    args = build_parser().parse_args()
    report = run_command(args)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "searched_trial_count": report["searched_trial_count"],
                "selected_config": report["selected_config"],
                "execution_authority": report["execution_authority"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
