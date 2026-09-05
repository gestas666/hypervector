#!/usr/bin/env python3
"""Audit prospective HIP-3 trade OHLC against live venue candles."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
import json
import sys
from typing import Protocol, cast

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import PublicTradeEvent
from hypervector.data.hip3_public_candles import (
    Hip3CandleSourceProtocol,
    Hip3PublicCandleSource,
)
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_prospective_candle_parity import (
    Hip3ProspectiveCandleParityConfig,
    build_hip3_prospective_candle_parity,
)


class ProspectiveTradeArchiveProtocol(Protocol):
    """Read-only trade surface required by the parity command."""

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        """Return prospectively recorded public trades."""


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit, report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--path-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    archive: ProspectiveTradeArchiveProtocol | None = None,
    candle_source: Hip3CandleSourceProtocol | None = None,
) -> dict[str, object]:
    """Bind one resolved path audit to exact trade/candle parity evidence."""
    symbol = _symbol(str(args.symbol))
    audit_path = Path(args.path_audit)
    audit_evidence = file_evidence(audit_path)
    audit = _load_path_audit(audit_path, symbol)
    config = _config(audit, symbol)
    reader = archive or EventArchive(
        data_root=Path(args.data_root),
        symbol=symbol,
        batch_size=2_000,
    )
    trades = _causal_trades(reader.replay_trades(), config)
    candles = (candle_source or Hip3PublicCandleSource()).completed_candles(
        symbol=symbol,
        start_ms=config.start_ms,
        end_ms=config.end_ms,
        observed_at_ms=config.observed_at_ms,
        timeframe_minutes=config.timeframe_minutes,
    )
    report = build_hip3_prospective_candle_parity(
        public_trades=trades,
        candles=candles,
        config=config,
    )
    _require_trade_identity(report, audit)
    _attach_risk_path_status(report, audit)
    _require_unchanged(audit_path, audit_evidence)
    report["path_audit_evidence"] = {
        "path": str(audit_path.resolve()),
        **audit_evidence,
    }
    report["generator_identity"] = _generator_identity()
    write_immutable_json(Path(args.output), report)
    return report


def _load_path_audit(path: Path, symbol: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"prospective path audit is missing: {path}")
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("prospective path audit must be a JSON object")
    audit = cast(dict[str, object], raw)
    if audit.get("schema_version") != "hip3_prospective_path_audit_v1":
        raise ValueError("prospective path audit schema is invalid")
    source = _mapping(audit, "source")
    if source.get("symbol") != symbol:
        raise ValueError("path audit symbol does not match requested symbol")
    contract = _mapping(audit, "contract")
    if (
        contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
    ):
        raise ValueError("prospective path audit authority contract is invalid")
    _risk_path_resolved(audit)
    return audit


def _attach_risk_path_status(
    report: dict[str, object], audit: Mapping[str, object]
) -> None:
    """Expose risk-path status without suppressing candle-only evidence."""
    assessment = report.get("technical_assessment")
    if not isinstance(assessment, dict):
        raise ValueError("prospective candle technical assessment is invalid")
    assessment["prospective_risk_path_coverage_resolved"] = _risk_path_resolved(audit)


def _risk_path_resolved(audit: Mapping[str, object]) -> bool:
    """Return an explicit path status while rejecting malformed evidence."""
    value = _mapping(audit, "technical_assessment").get(
        "prospective_bar_path_coverage_resolved"
    )
    if not isinstance(value, bool):
        raise ValueError("prospective path resolution status must be boolean")
    return value


def _config(
    audit: Mapping[str, object],
    symbol: str,
) -> Hip3ProspectiveCandleParityConfig:
    source = _mapping(audit, "source")
    coverage = _mapping(audit, "coverage")
    timeframe = _integer(coverage, "timeframe_minutes")
    if timeframe not in {5, 15}:
        raise ValueError("prospective candle parity requires 5m or 15m evidence")
    return Hip3ProspectiveCandleParityConfig(
        symbol=symbol,
        start_ms=_integer(coverage, "first_full_bar_open_ms"),
        end_ms=_integer(coverage, "completed_bar_end_ms"),
        observed_at_ms=_integer(source, "observed_at_ms"),
        timeframe_minutes=timeframe,
    )


def _causal_trades(
    trades: Sequence[PublicTradeEvent],
    config: Hip3ProspectiveCandleParityConfig,
) -> tuple[PublicTradeEvent, ...]:
    return tuple(
        trade
        for trade in trades
        if trade.received_ts_ns // 1_000_000 <= config.observed_at_ms
        and trade.exchange_ts_ms <= config.observed_at_ms
    )


def _require_trade_identity(
    report: Mapping[str, object],
    audit: Mapping[str, object],
) -> None:
    source = _mapping(report, "source")
    identity = _mapping(_mapping(audit, "evidence_identity"), "completed_bar_trades")
    if source.get("comparison_trade_rows") != identity.get("rows") or source.get(
        "comparison_trade_sha256"
    ) != identity.get("sha256"):
        raise ValueError("trade evidence does not match path audit")


def _require_unchanged(path: Path, expected: Mapping[str, object]) -> None:
    if file_evidence(path) != dict(expected):
        raise ValueError("prospective path audit changed during parity evaluation")


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/research/hip3_prospective_candle_parity.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise ValueError(f"prospective parity evidence missing object {key}")
    return cast(dict[str, object], selected)


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"prospective parity evidence {key} must be an integer")
    return selected


def _symbol(value: str) -> str:
    dex, separator, asset = value.strip().partition(":")
    if not separator:
        raise ValueError("prospective candle parity requires exact HIP-3 symbol")
    symbol = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(symbol, "hip3")
    return symbol


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only audit and print a compact status."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output).resolve()),
                "symbol": report["scope"]["symbol"],
                "coverage": report["coverage"],
                "technical_assessment": report["technical_assessment"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
