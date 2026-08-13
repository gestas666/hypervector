#!/usr/bin/env python3
"""Audit prospective HIP-3 signal decisions across two candle sources."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Protocol, cast

from hypervector.data.event_archive import EventArchive
from hypervector.data.hl_events import L2SnapshotEvent, PublicTradeEvent
from hypervector.data.hip3_public_candles import (
    Hip3CandleSourceProtocol,
    Hip3PublicCandleSource,
)
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_prospective_candle_parity import (
    Hip3ProspectiveCandleParityConfig,
    build_hip3_prospective_candle_frames,
    build_hip3_prospective_candle_parity,
)
from hypervector.research.hip3_prospective_signal_parity import (
    Hip3ProspectiveSignalParityConfig,
    build_hip3_prospective_signal_parity,
)


class ProspectiveSignalArchiveProtocol(Protocol):
    """Read-only prospective event surface required by this command."""

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        """Return recorded public trades."""

    def replay_l2(self) -> tuple[L2SnapshotEvent, ...]:
        """Return recorded public L2 snapshots."""


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--path-audit", type=Path, required=True)
    parser.add_argument("--candle-parity", type=Path, required=True)
    parser.add_argument("--development-diagnostic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    archive: ProspectiveSignalArchiveProtocol | None = None,
    candle_source: Hip3CandleSourceProtocol | None = None,
) -> dict[str, object]:
    """Bind frozen inputs and publish one immutable signal-source comparison."""
    symbol = _symbol(str(args.symbol))
    paths = _input_paths(args)
    evidence = {name: file_evidence(path) for name, path in paths.items()}
    path_audit = _load_path_audit(paths["path_audit"], symbol)
    candle_parity = _load_candle_parity(
        paths["candle_parity"], symbol, path_audit, evidence["path_audit"]
    )
    route = _route_config(paths["development_diagnostic"], symbol)
    candle_config = _candle_config(path_audit, symbol)
    reader = archive or EventArchive(
        data_root=Path(args.data_root), symbol=symbol, batch_size=2_000
    )
    trades, books = _completed_events(reader, candle_config)
    candles = (candle_source or Hip3PublicCandleSource()).completed_candles(
        symbol=symbol,
        start_ms=candle_config.start_ms,
        end_ms=candle_config.end_ms,
        observed_at_ms=candle_config.observed_at_ms,
    )
    current_candle_parity = build_hip3_prospective_candle_parity(
        public_trades=trades,
        candles=candles,
        config=candle_config,
    )
    _require_current_candle_identity(current_candle_parity, candle_parity)
    trade_bars, venue_bars = build_hip3_prospective_candle_frames(
        public_trades=trades, candles=candles, config=candle_config
    )
    report = build_hip3_prospective_signal_parity(
        trade_bars=trade_bars,
        venue_bars=venue_bars,
        l2_snapshots=books,
        observed_at_ms=candle_config.observed_at_ms,
        config=route,
    )
    _attach_risk_path_status(report, path_audit)
    _require_input_identities(report, path_audit, candle_parity)
    _require_unchanged(paths, evidence)
    report["input_evidence"] = _input_evidence(paths, evidence)
    report["generator_identity"] = _generator_identity()
    write_immutable_json(Path(args.output), report)
    return report


def _input_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "path_audit": Path(args.path_audit),
        "candle_parity": Path(args.candle_parity),
        "development_diagnostic": Path(args.development_diagnostic),
    }


def _load_path_audit(path: Path, symbol: str) -> dict[str, object]:
    audit = _json_object(path, "prospective path audit")
    if audit.get("schema_version") != "hip3_prospective_path_audit_v1":
        raise ValueError("prospective path audit schema is invalid")
    if _mapping(audit, "source").get("symbol") != symbol:
        raise ValueError("prospective path audit symbol is inconsistent")
    _risk_path_resolved(audit)
    _require_report_only(audit, "prospective path audit")
    return audit


def _attach_risk_path_status(
    report: dict[str, object], audit: Mapping[str, object]
) -> None:
    """Keep risk incompleteness explicit without hiding signal comparison."""
    assessment = report.get("technical_assessment")
    if not isinstance(assessment, dict):
        raise ValueError("prospective signal technical assessment is invalid")
    assessment["prospective_risk_path_coverage_resolved"] = _risk_path_resolved(audit)


def _risk_path_resolved(audit: Mapping[str, object]) -> bool:
    """Return the exact path status and reject malformed source evidence."""
    value = _mapping(audit, "technical_assessment").get(
        "prospective_bar_path_coverage_resolved"
    )
    if not isinstance(value, bool):
        raise ValueError("prospective path resolution status must be boolean")
    return value


def _load_candle_parity(
    path: Path,
    symbol: str,
    path_audit: Mapping[str, object],
    path_evidence: Mapping[str, object],
) -> dict[str, object]:
    report = _json_object(path, "prospective candle parity")
    if report.get("schema_version") != "hip3_prospective_candle_parity_v1":
        raise ValueError("prospective candle parity schema is invalid")
    if _mapping(report, "scope").get("symbol") != symbol:
        raise ValueError("prospective candle parity symbol is inconsistent")
    _require_report_only(report, "prospective candle parity")
    if _mapping(report, "path_audit_evidence").get("sha256") != path_evidence.get(
        "sha256"
    ):
        raise ValueError("candle parity does not bind the selected path audit")
    _require_complete_candle_coverage(report, path_audit)
    return report


def _require_complete_candle_coverage(
    report: Mapping[str, object], path_audit: Mapping[str, object]
) -> None:
    coverage = _mapping(report, "coverage")
    path_coverage = _mapping(path_audit, "coverage")
    expected = _integer(coverage, "expected_bars")
    if expected != _integer(path_coverage, "completed_bars") or expected <= 0:
        raise ValueError("candle parity coverage differs from path audit")
    complete = (
        _integer(coverage, "trade_bars") == expected
        and _integer(coverage, "candle_bars") == expected
        and _integer(coverage, "overlap_bars") == expected
        and _integer(coverage, "missing_trade_bars") == 0
        and _integer(coverage, "missing_candle_bars") == 0
    )
    if not complete:
        raise ValueError("candle parity is missing completed source bars")


def _route_config(path: Path, symbol: str) -> Hip3ProspectiveSignalParityConfig:
    report = _json_object(path, "development diagnostic")
    if report.get("symbol") != symbol:
        raise ValueError("selected route symbol does not match requested symbol")
    _require_diagnostic_authority(report)
    track = _selected_track(report)
    if track.get("symbol", symbol) != symbol:
        raise ValueError("selected route symbol does not match requested symbol")
    if track.get("family") != "breakout_pressure" or track.get("timeframe") != "15m":
        raise ValueError("selected route is not the frozen 15m breakout track")
    raw = _mapping(track, "config")
    breakout = Hip3BreakoutPressureConfig(
        _integer(raw, "breakout_lookback_bars"),
        _integer(raw, "fast_ema"),
        _integer(raw, "slow_ema"),
        _number(raw, "minimum_abs_imbalance"),
        _number(raw, "maximum_stop_bps"),
    )
    return Hip3ProspectiveSignalParityConfig(
        symbol,
        _text(track, "provider_id"),
        _text(track, "profile_id"),
        breakout,
    )


def _selected_track(report: Mapping[str, object]) -> Mapping[str, object]:
    schema = report.get("schema_version")
    if schema == "hip3_development_only_diagnostic_v1":
        return _mapping(report, "development_selected_track")
    if schema == "mu_development_path_threshold_diagnostic_v1":
        return _mapping(_mapping(report, "diagnostic"), "track")
    raise ValueError("development diagnostic schema is unsupported")


def _candle_config(
    audit: Mapping[str, object], symbol: str
) -> Hip3ProspectiveCandleParityConfig:
    source = _mapping(audit, "source")
    coverage = _mapping(audit, "coverage")
    if _integer(coverage, "timeframe_minutes") != 15:
        raise ValueError("prospective signal parity requires 15m path evidence")
    return Hip3ProspectiveCandleParityConfig(
        symbol,
        _integer(coverage, "first_full_bar_open_ms"),
        _integer(coverage, "completed_bar_end_ms"),
        _integer(source, "observed_at_ms"),
    )


def _completed_events(
    reader: ProspectiveSignalArchiveProtocol,
    config: Hip3ProspectiveCandleParityConfig,
) -> tuple[tuple[PublicTradeEvent, ...], tuple[L2SnapshotEvent, ...]]:
    trades = tuple(
        row
        for row in reader.replay_trades()
        if config.start_ms <= row.exchange_ts_ms < config.end_ms
        and row.received_ts_ns // 1_000_000 <= config.observed_at_ms
    )
    books = tuple(
        row
        for row in reader.replay_l2()
        if config.start_ms <= row.exchange_ts_ms < config.end_ms
        and row.received_ts_ns // 1_000_000 <= config.observed_at_ms
    )
    return trades, books


def _require_input_identities(
    report: Mapping[str, object],
    path_audit: Mapping[str, object],
    candle_parity: Mapping[str, object],
) -> None:
    identity = _mapping(path_audit, "evidence_identity")
    expected_l2 = _mapping(identity, "completed_bar_l2")
    source = _mapping(report, "source")
    if source.get("l2_snapshot_rows") != expected_l2.get("rows") or source.get(
        "l2_snapshot_sha256"
    ) != expected_l2.get("sha256"):
        raise ValueError("L2 evidence does not match path audit")
    if _mapping(candle_parity, "source").get("comparison_trade_sha256") != _mapping(
        identity, "completed_bar_trades"
    ).get("sha256"):
        raise ValueError("candle parity trade evidence differs from path audit")


def _require_current_candle_identity(
    current: Mapping[str, object], frozen: Mapping[str, object]
) -> None:
    current_source = _mapping(current, "source")
    frozen_source = _mapping(frozen, "source")
    keys = (
        "comparison_trade_rows",
        "comparison_trade_sha256",
        "comparison_candle_rows",
        "comparison_candle_sha256",
    )
    if any(current_source.get(key) != frozen_source.get(key) for key in keys):
        raise ValueError("candle evidence changed since parity audit")


def _require_report_only(value: Mapping[str, object], label: str) -> None:
    contract = _mapping(value, "contract") if "contract" in value else value
    authority = contract.get("execution_authority")
    report_only = contract.get("report_only", value.get("report_only"))
    if authority != "none" or report_only is not True:
        raise ValueError(f"{label} authority contract is invalid")


def _require_diagnostic_authority(value: Mapping[str, object]) -> None:
    if value.get("execution_authority") != "none":
        raise ValueError("development diagnostic authority contract is invalid")
    schema = value.get("schema_version")
    generic = (
        schema == "hip3_development_only_diagnostic_v1"
        and value.get("report_only") is True
    )
    mu_safe = (
        schema == "mu_development_path_threshold_diagnostic_v1"
        and value.get("automatic_promotion") is False
        and value.get("qualification_abort_preserved") is True
        and value.get("validation_accessed") is False
        and value.get("holdout_accessed") is False
    )
    if not generic and not mu_safe:
        raise ValueError("development diagnostic authority contract is invalid")


def _require_unchanged(
    paths: Mapping[str, Path], expected: Mapping[str, Mapping[str, object]]
) -> None:
    for name, path in paths.items():
        if file_evidence(path) != dict(expected[name]):
            raise ValueError(f"{name} changed during signal parity evaluation")


def _input_evidence(
    paths: Mapping[str, Path], evidence: Mapping[str, Mapping[str, object]]
) -> dict[str, object]:
    return {
        name: {"path": str(path.resolve()), **dict(evidence[name])}
        for name, path in paths.items()
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    paths = (
        Path(__file__).resolve(),
        root / "src/hypervector/data/hip3_public_candles.py",
        root / "src/hypervector/research/hip3_breakout_pressure_signals.py",
        root / "src/hypervector/research/hip3_prospective_candle_parity.py",
        root / "src/hypervector/research/hip3_prospective_signal_parity.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    selected = value.get(key)
    if not isinstance(selected, dict):
        raise ValueError(f"prospective signal evidence missing object {key}")
    return cast(dict[str, object], selected)


def _integer(value: Mapping[str, object], key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"prospective signal evidence {key} must be an integer")
    return selected


def _number(value: Mapping[str, object], key: str) -> float:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, (int, float)):
        raise ValueError(f"prospective signal evidence {key} must be numeric")
    return float(selected)


def _text(value: Mapping[str, object], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError(f"prospective signal evidence {key} must be text")
    return selected


def _symbol(value: str) -> str:
    dex, separator, asset = value.strip().partition(":")
    if not separator:
        raise ValueError("prospective signal parity requires exact HIP-3 symbol")
    symbol = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(symbol, "hip3")
    return symbol


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only comparison and print a compact status."""
    args = build_parser().parse_args(argv)
    try:
        report = run_command(args)
    except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
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
