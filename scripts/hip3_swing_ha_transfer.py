#!/usr/bin/env python3
"""Run a bounded report-only Swing/HA transfer screen on HIP-3 markets."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from hypervector.data.hl import fetch_hl_funding_history, fetch_hl_ohlcv
from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.hip3_midpoint_bars import (
    Hip3MidpointBars,
    build_hip3_midpoint_bars,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3SwingTransferResult,
    Hip3TransferAsset,
    run_hip3_swing_transfer,
)
from hypervector.research.hip3_transfer_sources import (
    attach_official_funding,
    compare_midpoint_proxy_to_official,
)
from hypervector.research.swing_ha_experiment import evaluation_summaries
from hypervector.research.swing_ha_screen import SwingHaScreenCell
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_DEFAULT_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_DEFAULT_DATABASE = Path("data/research/hip3_market.duckdb")
_DEFAULT_QUALIFICATION = Path(
    "data/logs/research/xyz_sp500_spcx_qualification_20260806T1451Z.json"
)
_DEFAULT_OUTPUT = Path("data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json")
_DEFAULT_TRADES = Path(
    "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.trades.parquet"
)
_DEFAULT_SOURCES = Path(
    "data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.sources.parquet"
)
_DEFAULT_AUDITS = {
    "xyz:SP500": Path("data/logs/research/xyz_sp500_l2_archive_audit_20260806.json"),
    "xyz:SPCX": Path("data/logs/research/xyz_spcx_l2_archive_audit_20260806.json"),
}
_DEFAULT_LIQUIDITY = {
    "xyz:SP500": Path(
        "data/logs/research/xyz_sp500_liquidity_profile_fee_sensitivity_20260806.json"
    ),
    "xyz:SPCX": Path(
        "data/logs/research/xyz_spcx_liquidity_profile_fee_sensitivity_20260806.json"
    ),
}


class FundingFetcher(Protocol):
    """Read-only official funding fetch boundary."""

    def __call__(
        self,
        symbol: str,
        *,
        start_time: pd.Timestamp,
        end_time: pd.Timestamp,
    ) -> pd.DataFrame:
        """Return exact official hourly funding rows."""
        ...


class CandleFetcher(Protocol):
    """Read-only official candle fetch boundary."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: int,
        *,
        end_ms: int,
    ) -> pd.DataFrame:
        """Return the retained official candle window."""
        ...


@dataclass(frozen=True)
class _PreparedAsset:
    asset: Hip3TransferAsset
    friction: Hip3ExecutionFriction
    source_rows: pd.DataFrame
    evidence: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Return the execution-incapable transfer-screen parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=_DEFAULT_DATABASE)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--audit-report", action="append", default=[])
    parser.add_argument("--liquidity-report", action="append", default=[])
    parser.add_argument(
        "--qualification-report", type=Path, default=_DEFAULT_QUALIFICATION
    )
    parser.add_argument("--nominal-latency-bps-per-side", type=float, default=1.0)
    parser.add_argument("--stress-latency-bps-per-side", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--trades-output", type=Path, default=_DEFAULT_TRADES)
    parser.add_argument("--sources-output", type=Path, default=_DEFAULT_SOURCES)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    funding_fetcher: FundingFetcher = fetch_hl_funding_history,
    candle_fetcher: CandleFetcher = fetch_hl_ohlcv,
    base_configs: tuple[SwingHaSignalConfig, ...] | None = None,
    order_block_configs: tuple[SwingHaSignalConfig, ...] | None = None,
) -> dict[str, object]:
    """Run once and publish immutable, execution-incapable evidence."""
    _require_new_outputs(args.output, args.trades_output, args.sources_output)
    symbols = tuple(args.symbols or _DEFAULT_SYMBOLS)
    audits = _path_map(args.audit_report, symbols, _DEFAULT_AUDITS, "audit")
    liquidity = _path_map(
        args.liquidity_report, symbols, _DEFAULT_LIQUIDITY, "liquidity"
    )
    leverages = _qualification_leverages(args.qualification_report, symbols)
    prepared = tuple(
        _prepare_asset(
            args,
            symbol,
            audits[symbol],
            liquidity[symbol],
            leverages[symbol],
            funding_fetcher,
            candle_fetcher,
        )
        for symbol in symbols
    )
    result = run_hip3_swing_transfer(
        tuple(item.asset for item in prepared),
        {item.asset.symbol: item.friction for item in prepared},
        base_configs=base_configs,
        order_block_configs=order_block_configs,
    )
    trades = _trade_frame(result)
    sources = pd.concat([item.source_rows for item in prepared], ignore_index=True)
    write_immutable_parquet(args.trades_output, trades)
    write_immutable_parquet(args.sources_output, sources)
    report = _report(args, symbols, prepared, result)
    report["trade_sidecar"] = _file_reference(args.trades_output, len(trades))
    report["source_sidecar"] = _file_reference(args.sources_output, len(sources))
    json.dumps(report, sort_keys=True)
    write_immutable_json(args.output, report)
    return report


def _prepare_asset(
    args: argparse.Namespace,
    symbol: str,
    audit_path: Path,
    liquidity_path: Path,
    max_leverage: float,
    funding_fetcher: FundingFetcher,
    candle_fetcher: CandleFetcher,
) -> _PreparedAsset:
    midpoint = build_hip3_midpoint_bars(args.database, symbol=symbol)
    funding = funding_fetcher(
        symbol,
        start_time=midpoint.archive_start_utc,
        end_time=midpoint.archive_end_utc,
    )
    bars, funding_evidence = attach_official_funding(midpoint.bars, funding)
    official = candle_fetcher(
        symbol,
        "15m",
        6,
        end_ms=int(midpoint.archive_end_utc.timestamp() * 1_000),
    )
    proxy = compare_midpoint_proxy_to_official(bars, official)
    friction = _friction(
        liquidity_path,
        args.nominal_latency_bps_per_side,
        args.stress_latency_bps_per_side,
    )
    evidence = {
        "symbol": symbol,
        "audit_report": _file_reference(audit_path),
        "liquidity_report": _file_reference(liquidity_path),
        "archive": _archive_evidence(midpoint),
        "funding": asdict(funding_evidence),
        "midpoint_proxy_validation": asdict(proxy),
        "friction": asdict(friction),
    }
    return _PreparedAsset(
        Hip3TransferAsset(symbol, max_leverage, bars),
        friction,
        _source_rows(symbol, funding, official),
        evidence,
    )


def _report(
    args: argparse.Namespace,
    symbols: tuple[str, ...],
    prepared: tuple[_PreparedAsset, ...],
    result: Hip3SwingTransferResult,
) -> dict[str, object]:
    return {
        "schema_version": "hip3_swing_ha_transfer_v2",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "place_attempted": False,
        "automatic_promotion": False,
        "symbols": list(symbols),
        "database_path": str(args.database.resolve()),
        "qualification_report": _file_reference(args.qualification_report),
        "source_evidence": [item.evidence for item in prepared],
        "windows": _windows(result),
        "searched_trial_count": result.searched_trial_count,
        "base_trial_count": len(result.base_evaluations),
        "base_trials": evaluation_summaries(result.base_evaluations),
        "selected_base_config": asdict(result.selected_base),
        "order_block_trial_count": len(result.order_block_evaluations),
        "order_block_trials": evaluation_summaries(result.order_block_evaluations),
        "selected_frozen_config": asdict(result.selected_frozen),
        "literal_control_config": asdict(result.literal_control),
        "validation": {
            "nominal": [_compact_cell(cell) for cell in result.validation_nominal],
            "stress": [_compact_cell(cell) for cell in result.validation_stress],
            "literal_9x21_control_nominal": [
                _compact_cell(cell) for cell in result.literal_control_nominal
            ],
            "literal_9x21_control_stress": [
                _compact_cell(cell) for cell in result.literal_control_stress
            ],
        },
        "holdout": {
            "status": result.holdout_status,
            "start_utc": result.windows.validation_end_utc.isoformat(),
            "end_utc": result.windows.holdout_end_utc.isoformat(),
            "metrics_accessed": False,
        },
        "promotion": None,
        "limitations": _limitations(),
        "generator_identity": _generator_identity(),
    }


def _friction(
    path: Path,
    nominal_latency: float,
    stress_latency: float,
) -> Hip3ExecutionFriction:
    profile = _mapping(_load_json(path).get("profile"), "liquidity profile")
    fees = _mapping(profile.get("fees"), "liquidity fees")
    rows = _sequence(profile.get("notionals"), "liquidity notionals")
    matches = [
        _mapping(row, "liquidity notional")
        for row in rows
        if _number(
            _mapping(row, "liquidity notional").get("notional_usd"), "notional_usd"
        )
        == 75.0
    ]
    if len(matches) != 1:
        raise ValueError("liquidity report requires exactly one `$75` notional row")
    visible = _mapping(
        matches[0].get("round_trip_visible_cost_bps"), "visible cost distribution"
    )
    return Hip3ExecutionFriction(
        75.0,
        _number(fees.get("effective_taker_rate"), "effective_taker_rate"),
        _number(visible.get("p90"), "visible p90"),
        float(nominal_latency),
        _number(visible.get("p99"), "visible p99"),
        float(stress_latency),
    )


def _qualification_leverages(path: Path, symbols: tuple[str, ...]) -> dict[str, float]:
    rows = _sequence(_load_json(path).get("markets"), "qualification markets")
    output: dict[str, float] = {}
    for raw in rows:
        row = _mapping(raw, "qualification market")
        symbol = str(row.get("symbol") or "")
        if symbol in symbols:
            output[symbol] = _number(row.get("max_leverage"), "max_leverage")
    if set(output) != set(symbols):
        raise ValueError(
            "qualification leverage scope does not match requested symbols"
        )
    return output


def _source_rows(
    symbol: str,
    funding: pd.DataFrame,
    official: pd.DataFrame,
) -> pd.DataFrame:
    funding_rows = funding.copy()
    funding_rows.insert(0, "symbol", symbol)
    funding_rows.insert(1, "record_type", "official_funding")
    candle_rows = official.copy()
    candle_rows.insert(0, "symbol", symbol)
    candle_rows.insert(1, "record_type", "official_candle_15m")
    columns = [
        "symbol",
        "record_type",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "funding_rate",
        "source",
    ]
    return pd.concat([funding_rows, candle_rows], ignore_index=True).reindex(
        columns=columns
    )


def _trade_frame(result: Hip3SwingTransferResult) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario, cells in (
        ("validation_nominal", result.validation_nominal),
        ("validation_stress", result.validation_stress),
        ("literal_9x21_control_nominal", result.literal_control_nominal),
        ("literal_9x21_control_stress", result.literal_control_stress),
    ):
        for cell in cells:
            for trade in cell.trade_records:
                rows.append({"scenario": scenario, "symbol": cell.symbol, **trade})
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["scenario", "symbol", "direction", "net_pnl_usd"])


def _windows(result: Hip3SwingTransferResult) -> dict[str, object]:
    value = result.windows
    return {
        "development_start_utc": value.development_start_utc.isoformat(),
        "development_end_utc": value.development_end_utc.isoformat(),
        "validation_end_utc": value.validation_end_utc.isoformat(),
        "holdout_end_utc": value.holdout_end_utc.isoformat(),
        "development_folds": [
            {"start_utc": start.isoformat(), "end_utc": end.isoformat()}
            for start, end in value.development_folds
        ],
    }


def _archive_evidence(midpoint: Hip3MidpointBars) -> dict[str, object]:
    return {
        "start_utc": midpoint.archive_start_utc.isoformat(),
        "end_utc": midpoint.archive_end_utc.isoformat(),
        "bundles": midpoint.archive_bundles,
        "book_rows": midpoint.archive_book_rows,
        "observed_15m_bars": len(midpoint.bars),
        "expected_15m_bars": midpoint.expected_bar_count,
        "missing_15m_bars": midpoint.missing_bar_count,
    }


def _compact_cell(cell: SwingHaScreenCell) -> dict[str, object]:
    values = asdict(cell)
    values.pop("trade_records")
    return values


def _path_map(
    values: list[str],
    symbols: tuple[str, ...],
    defaults: dict[str, Path],
    label: str,
) -> dict[str, Path]:
    output = {symbol: defaults[symbol] for symbol in symbols if symbol in defaults}
    for raw in values:
        symbol, separator, raw_path = raw.partition("=")
        if not separator or not symbol or not raw_path:
            raise ValueError(f"{label} mapping must use SYMBOL=PATH")
        output[symbol] = Path(raw_path)
    if set(output) != set(symbols) or any(
        not path.is_file() for path in output.values()
    ):
        raise ValueError(f"{label} report scope is incomplete or missing")
    return output


def _file_reference(path: Path, rows: int | None = None) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"evidence file does not exist: {path}")
    output = {"path": str(path.resolve()), **file_evidence(path)}
    if rows is not None:
        output["rows"] = rows
    return output


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_midpoint_bars.py",
        root / "src/hypervector/research/hip3_transfer_sources.py",
        root / "src/hypervector/research/hip3_swing_signals.py",
        root / "src/hypervector/research/hip3_swing_transfer.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _limitations() -> list[str]:
    return [
        "L2 midpoint OHLC is a validated price-path proxy, not public-trade OHLC",
        "official candle comparison is limited by the venue's retained recent window",
        "current account fee inputs are a sensitivity, not historical fee truth",
        "latency allowances are explicit assumptions pending HIP-3 live fills",
        "development selection uses independent asset accounts, not shared capital",
        "queue position and passive fill probability are not inferred from snapshots",
        "the final chronological holdout remains sealed",
    ]


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"JSON evidence does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, f"JSON evidence {path}")


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _require_new_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable HIP-3 outputs already exist: {existing}")


def main() -> int:
    """Run the bounded screen and print its immutable report path."""
    args = build_parser().parse_args()
    run_command(args)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
