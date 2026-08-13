#!/usr/bin/env python3
"""Publish causal report-only BBO markouts for one HIP-3 shadow route."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.hip3_breakout_shadow_specs import (
    HIP3_SHADOW_SPECS,
    Hip3BreakoutShadowSpec,
)
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowMarkoutConfig,
    build_hip3_shadow_signal_markouts,
)

Record = Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit no-authority markout command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--book-ledger", type=Path, required=True)
    parser.add_argument("--development-diagnostic", type=Path, required=True)
    parser.add_argument("--fee-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon-minutes", type=int, nargs="+", default=[15, 60, 240])
    parser.add_argument("--maximum-book-lateness-ms", type=int, default=15_000)
    return parser


def run_command(args: argparse.Namespace) -> dict[str, object]:
    """Bind immutable inputs and publish one exact prospective report."""
    spec = _spec(str(args.symbol))
    paths = _paths(args)
    _require_distinct((*paths.values(), Path(args.output)))
    evidence = {name: file_evidence(path) for name, path in paths.items()}
    diagnostic = _json_object(paths["development_diagnostic"], "diagnostic")
    fee_report = _json_object(paths["fee_evidence"], "fee evidence")
    latency = _development_latency(diagnostic, spec)
    fee = _fee_bps(fee_report, spec)
    config = Hip3ShadowMarkoutConfig(
        spec.symbol,
        spec.provider_id,
        spec.profile_id,
        spec.ledger_profile_id,
        fee,
        latency,
        _friction_source(paths, evidence),
        tuple(args.horizon_minutes),
        args.maximum_book_lateness_ms,
    )
    report = build_hip3_shadow_signal_markouts(
        decision_rows=_jsonl(paths["journal"], "decision journal"),
        book_rows=_jsonl(paths["book_ledger"], "book ledger"),
        config=config,
    )
    _require_unchanged(paths, evidence)
    report["input_evidence"] = _input_evidence(paths, evidence)
    report["generator_identity"] = _generator_identity()
    write_immutable_json(Path(args.output), report)
    return report


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "journal": Path(args.journal),
        "book_ledger": Path(args.book_ledger),
        "development_diagnostic": Path(args.development_diagnostic),
        "fee_evidence": Path(args.fee_evidence),
    }


def _spec(value: str) -> Hip3BreakoutShadowSpec:
    dex, separator, asset = value.strip().partition(":")
    if not separator:
        raise ValueError("HIP-3 markout requires an exact xyz symbol")
    symbol = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(symbol, "hip3")
    matches = [
        candidate for candidate in HIP3_SHADOW_SPECS if candidate.symbol == symbol
    ]
    if len(matches) != 1:
        raise ValueError(f"HIP-3 markout has no frozen shadow spec for {symbol}")
    return matches[0]


def _development_latency(report: Record, spec: Hip3BreakoutShadowSpec) -> float:
    _require_diagnostic_contract(report)
    if report.get("symbol") != spec.symbol:
        raise ValueError("development diagnostic symbol is inconsistent")
    track = _selected_track(report)
    if (
        track.get("provider_id") != spec.provider_id
        or track.get("profile_id") != spec.profile_id
    ):
        raise ValueError("development diagnostic route identity is inconsistent")
    if track.get("timeframe") != "15m" or track.get("family") != "breakout_pressure":
        raise ValueError("development diagnostic track is unsupported")
    if report.get("schema_version") == "mu_development_path_threshold_diagnostic_v1":
        source = _mapping(report.get("inputs"), "diagnostic inputs")
    else:
        source = _mapping(
            _mapping(report.get("route_specific_friction"), "route friction").get(
                "15m"
            ),
            "15m route friction",
        )
    return _nonnegative_number(
        source.get("nominal_latency_bps_per_side"), "nominal latency"
    )


def _selected_track(report: Record) -> Mapping[str, object]:
    schema = report.get("schema_version")
    if schema == "hip3_development_only_diagnostic_v1":
        return _mapping(report.get("development_selected_track"), "selected track")
    if schema == "mu_development_path_threshold_diagnostic_v1":
        diagnostic = _mapping(report.get("diagnostic"), "diagnostic")
        return _mapping(diagnostic.get("track"), "selected track")
    raise ValueError("development diagnostic schema is unsupported")


def _require_diagnostic_contract(report: Record) -> None:
    schema = report.get("schema_version")
    generic = (
        schema == "hip3_development_only_diagnostic_v1"
        and report.get("report_only") is True
        and report.get("execution_authority") == "none"
    )
    mu_safe = (
        schema == "mu_development_path_threshold_diagnostic_v1"
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("validation_accessed") is False
        and report.get("holdout_accessed") is False
        and report.get("qualification_abort_preserved") is True
    )
    if not generic and not mu_safe:
        raise ValueError("development diagnostic authority contract is invalid")


def _fee_bps(report: Record, spec: Hip3BreakoutShadowSpec) -> float:
    if (
        report.get("execution_authority") != "none"
        or report.get("report_only") is not True
    ):
        raise ValueError("fee evidence authority contract is invalid")
    profile = report.get("profile")
    if isinstance(profile, dict):
        values = cast(dict[str, object], profile)
        if values.get("symbol") != spec.symbol:
            raise ValueError("fee evidence symbol is inconsistent")
        fees = _mapping(values.get("fees"), "fee evidence")
        return _nonnegative_number(fees.get("one_way_taker_fee_bps"), "taker fee")
    if report.get("symbol") != spec.symbol:
        raise ValueError("fee evidence symbol is inconsistent")
    friction = _mapping(report.get("route_specific_friction"), "route friction")
    values = _mapping(friction.get("15m"), "15m route friction")
    rate = _nonnegative_number(values.get("effective_taker_fee_rate"), "taker rate")
    return rate * 10_000.0


def _json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"HIP-3 markout {label} is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"HIP-3 markout {label} must be an object")
    return cast(dict[str, object], value)


def _jsonl(path: Path, label: str) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        raise FileNotFoundError(f"HIP-3 markout {label} is missing: {path}")
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{label} line {line_number} must be an object")
            rows.append(cast(dict[str, object], value))
    return tuple(rows)


def _friction_source(
    paths: Mapping[str, Path], evidence: Mapping[str, Mapping[str, object]]
) -> str:
    development = evidence["development_diagnostic"]["sha256"]
    fee = evidence["fee_evidence"]["sha256"]
    return (
        f"{paths['development_diagnostic']}@{development};{paths['fee_evidence']}@{fee}"
    )


def _require_unchanged(
    paths: Mapping[str, Path], evidence: Mapping[str, Mapping[str, object]]
) -> None:
    for name, path in paths.items():
        if file_evidence(path) != dict(evidence[name]):
            raise ValueError(f"HIP-3 markout {name} changed during evaluation")


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
        root / "src/hypervector/research/hip3_shadow_signal_markouts.py",
        root / "src/hypervector/live/hip3_breakout_shadow_specs.py",
    )
    return {str(path.relative_to(root)): file_evidence(path) for path in paths}


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("HIP-3 markout input and output paths must be distinct")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 markout {label} must be an object")
    return cast(dict[str, object], value)


def _nonnegative_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"HIP-3 markout {label} must be nonnegative")
    return float(value)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only diagnostic and print compact coverage."""
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
                "symbol": report["symbol"],
                "source": report["source"],
                "horizons": report["markouts"]["horizons"],
                "execution_authority": "none",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
