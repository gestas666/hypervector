#!/usr/bin/env python3
"""Publish immutable report-only BRENTOIL oil-shock lifecycle evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

from hypervector.data.hl_events import AssetContextEvent
from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.brentoil_oil_shock_shadow import BRENTOIL_OIL_SHOCK_SYMBOL
from hypervector.research.brentoil_oil_shock_lifecycle import (
    BrentoilOilShockLifecycleConfig,
    build_brentoil_oil_shock_lifecycle_report,
)
from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHip3MarkArchive,
    Hip3MarkSourceProtocol,
)

Record = dict[str, object]


@dataclass(frozen=True)
class _Inputs:
    paths: dict[str, Path]
    exact: dict[str, dict[str, object]]
    decisions: tuple[Record, ...]
    candles: tuple[Record, ...]
    books: tuple[Record, ...]
    prefixes: dict[str, dict[str, object]]
    marks: tuple[AssetContextEvent, ...]
    mark_evidence: dict[str, object]
    mark_source: Hip3MarkSourceProtocol
    config: BrentoilOilShockLifecycleConfig
    observed_at_ms: int
    generator: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable evidence command parser."""
    root = Path("data/live/research/brentoil_oil_shock_shadow")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, default=root / "decisions.jsonl")
    parser.add_argument("--candle-ledger", type=Path, default=root / "candles.jsonl")
    parser.add_argument("--book-ledger", type=Path, default=root / "rest_books.jsonl")
    parser.add_argument("--mark-data-root", type=Path, default=root / "ws")
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--live-canary", type=Path, required=True)
    parser.add_argument("--observed-at-ms", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    mark_source: Hip3MarkSourceProtocol | None = None,
) -> dict[str, object]:
    """Verify frozen inputs and atomically publish one no-authority report."""
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"immutable BRENTOIL lifecycle output exists: {output}")
    report = build_report(args, destination=output, mark_source=mark_source)
    write_immutable_json(output, report)
    return report


def build_report(
    args: argparse.Namespace,
    *,
    destination: Path,
    mark_source: Hip3MarkSourceProtocol | None = None,
) -> dict[str, object]:
    """Build exact report-only evidence without publishing the destination."""
    inputs = _prepare(args, destination, mark_source or FrozenHip3MarkArchive())
    report = build_brentoil_oil_shock_lifecycle_report(
        decision_rows=inputs.decisions,
        candle_rows=inputs.candles,
        book_rows=inputs.books,
        marks=inputs.marks,
        observed_at_ms=inputs.observed_at_ms,
        config=inputs.config,
    )
    _finalize(report, inputs)
    return report


def _prepare(
    args: argparse.Namespace, output: Path, mark_source: Hip3MarkSourceProtocol
) -> _Inputs:
    paths = _paths(args)
    _require_distinct((*paths.values(), output))
    exact = {
        name: file_evidence(path)
        for name, path in paths.items()
        if name in {"development", "live_canary"}
    }
    development = _json_object(paths["development"], "development")
    canary = _json_object(paths["live_canary"], "live canary")
    config = _config(development, canary)
    observed = _positive_integer(args.observed_at_ms, "observed-at-ms")
    rows, prefixes = _bounded_prefixes(paths, observed)
    start = _decision_start(rows["decisions"])
    raw_marks, mark_evidence = mark_source.load(
        data_root=paths["mark_data_root"],
        symbol=BRENTOIL_OIL_SHOCK_SYMBOL,
        start_ms=start,
        end_ms=observed,
    )
    return _Inputs(
        paths,
        exact,
        rows["decisions"],
        rows["candles"],
        rows["books"],
        prefixes,
        _mark_events(raw_marks),
        mark_evidence,
        mark_source,
        config,
        observed,
        _generator_identity(),
    )


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "journal": Path(args.journal),
        "candle_ledger": Path(args.candle_ledger),
        "book_ledger": Path(args.book_ledger),
        "mark_data_root": Path(args.mark_data_root),
        "development": Path(args.development),
        "live_canary": Path(args.live_canary),
    }


def _bounded_prefixes(
    paths: Mapping[str, Path], observed_at_ms: int
) -> tuple[dict[str, tuple[Record, ...]], dict[str, dict[str, object]]]:
    decisions, decision_evidence = read_jsonl_prefix(paths["journal"], "decisions")
    candles, candle_evidence = read_jsonl_prefix(paths["candle_ledger"], "candles")
    books, book_evidence = read_jsonl_prefix(paths["book_ledger"], "books")
    bounded_decisions = _bounded(decisions, observed_at_ms, _decision_observed)
    source_decisions, legacy = _source_contract_decisions(bounded_decisions)
    rows = {
        "decisions": source_decisions,
        "candles": _bounded(candles, observed_at_ms, _candle_observed),
        "books": _bounded(books, observed_at_ms, _book_observed),
    }
    if not rows["decisions"] or not rows["candles"]:
        raise ValueError("BRENTOIL lifecycle has no bounded decision/candle evidence")
    decision_prefix = dict(decision_evidence)
    decision_prefix["legacy_quiet_decisions_excluded"] = legacy
    prefixes = {
        "decision_prefix": decision_prefix,
        "candle_prefix": candle_evidence,
        "book_prefix": book_evidence,
    }
    return rows, prefixes


def _source_contract_decisions(
    rows: Sequence[Record],
) -> tuple[tuple[Record, ...], int]:
    output: list[Record] = []
    excluded = 0
    for row in rows:
        decision = _mapping(row.get("decision"), "decision")
        if _has_source_contract(decision):
            output.append(row)
        elif decision.get("eligible") is True:
            raise ValueError("legacy eligible BRENTOIL decision is unresolved")
        else:
            excluded += 1
    return tuple(output), excluded


def _has_source_contract(decision: Mapping[str, object]) -> bool:
    numeric = (
        "candle_open",
        "candle_high",
        "candle_low",
        "candle_close",
        "candle_volume",
    )
    digest = decision.get("signal_window_sha256")
    return (
        all(isinstance(decision.get(name), (int, float)) for name in numeric)
        and isinstance(digest, str)
        and len(digest) == 64
        and decision.get("signal_ohlc_source") == "hyperliquid_public_candleSnapshot_5m"
    )


def _bounded(
    rows: Sequence[Record],
    observed_at_ms: int,
    timestamp: Callable[[Mapping[str, object]], int],
) -> tuple[Record, ...]:
    return tuple(row for row in rows if timestamp(row) <= observed_at_ms)


def _decision_observed(row: Mapping[str, object]) -> int:
    return _positive_integer(
        _mapping(row.get("decision"), "decision").get("observed_at_ms"),
        "decision observed",
    )


def _candle_observed(row: Mapping[str, object]) -> int:
    return _positive_integer(row.get("observed_at_ms"), "candle observed")


def _book_observed(row: Mapping[str, object]) -> int:
    return _positive_integer(
        _mapping(row.get("payload"), "book payload").get("recv_ts_ms"), "book observed"
    )


def _decision_start(rows: Sequence[Record]) -> int:
    return min(
        _positive_integer(
            _mapping(row.get("decision"), "decision").get("decision_time_ms"),
            "decision time",
        )
        for row in rows
    )


def _config(
    development: Mapping[str, object], canary: Mapping[str, object]
) -> BrentoilOilShockLifecycleConfig:
    _require_artifact_contract(development, canary)
    strategy = _mapping(development.get("strategy_identity"), "strategy identity")
    raw_config = _mapping(strategy.get("config"), "strategy config")
    expected = asdict(Hip3OilShockReversionConfig())
    if raw_config != expected or strategy.get("timeframe") != "5m":
        raise ValueError("BRENTOIL lifecycle development strategy changed")
    friction = _mapping(development.get("friction_contract"), "friction")
    applied = _mapping(friction.get("applied_strategy_execution"), "execution")
    canary_stress = _canary_stress(canary)
    _require_stress_contract(friction, applied, canary_stress)
    return BrentoilOilShockLifecycleConfig(
        fee_bps_per_side=_number(friction.get("effective_taker_fee_rate"), "fee")
        * 10_000,
        nominal_residual_bps_per_side=_number(
            applied.get("nominal_slippage_bps_per_side"), "nominal slippage"
        ),
        stress_residual_bps_per_side=canary_stress,
        notional_usd=_number(friction.get("scaled_notional_usd"), "scaled notional"),
        maximum_book_lateness_ms=15_000,
        maximum_mark_gap_ms=5_000,
        target_bps=expected["target_bps"],
        stop_bps=expected["stop_bps"],
        maximum_hold_ms=expected["maximum_hold_bars"] * 300_000,
        friction_source="development-v4+exact-live-canary-v1",
    )


def _require_artifact_contract(
    development: Mapping[str, object], canary: Mapping[str, object]
) -> None:
    safe_development = (
        development.get("symbol") == BRENTOIL_OIL_SHOCK_SYMBOL
        and development.get("execution_authority") == "none"
        and development.get("report_only") is True
        and development.get("automatic_promotion") is False
    )
    conclusion = _mapping(canary.get("conclusion"), "canary conclusion")
    safe_canary = (
        canary.get("symbol") == BRENTOIL_OIL_SHOCK_SYMBOL
        and canary.get("mode") == "report_only"
        and canary.get("execution_authority") == "none"
        and canary.get("automatic_live_change") is False
        and canary.get("runtime_strategy_changed") is False
        and conclusion.get("asset_data_available") is True
    )
    if not safe_development or not safe_canary:
        raise ValueError("BRENTOIL lifecycle artifact identity is invalid")


def _canary_stress(canary: Mapping[str, object]) -> float:
    lifecycles = _records(canary.get("lifecycles"), "canary lifecycles")
    values = [
        abs(
            _finite_number(
                _mapping(row.get(section), section).get("slippage_bps"), "slippage"
            )
        )
        for row in lifecycles
        for section in ("entry", "exit")
    ]
    friction = max(values)
    coverage = _mapping(canary.get("ledger_coverage"), "canary coverage")
    if (
        len(values) != 6
        or _positive_integer(coverage.get("raw_fill_events"), "raw fills") != 7
    ):
        raise ValueError("BRENTOIL lifecycle canary execution coverage is incomplete")
    return friction


def _require_stress_contract(
    friction: Mapping[str, object], applied: Mapping[str, object], canary: float
) -> None:
    values = (
        _number(friction.get("live_stress_floor_bps_per_side"), "stress floor"),
        _number(applied.get("stress_slippage_bps_per_side"), "stress slippage"),
    )
    if any(not math.isclose(value, canary, abs_tol=1e-12) for value in values):
        raise ValueError("BRENTOIL lifecycle stress does not match live canary")
    if (
        _positive_integer(friction.get("live_slippage_observations"), "slippage count")
        != 6
    ):
        raise ValueError("BRENTOIL lifecycle stress observation count is invalid")
    signal = Hip3OilShockReversionConfig()
    fixed = (
        (_number(applied.get("target_distance_bps"), "target"), signal.target_bps),
        (_number(applied.get("stop_distance_bps"), "stop"), signal.stop_bps),
        (
            _number(applied.get("maximum_hold_seconds"), "maximum hold"),
            signal.maximum_hold_bars * 300.0,
        ),
    )
    if any(not math.isclose(actual, expected) for actual, expected in fixed):
        raise ValueError("BRENTOIL lifecycle execution contract changed")


def _mark_events(rows: Sequence[Mapping[str, object]]) -> tuple[AssetContextEvent, ...]:
    return tuple(_mark_event(row) for row in rows)


def _mark_event(row: Mapping[str, object]) -> AssetContextEvent:
    mark = _number(row.get("mark_price"), "mark price")
    return AssetContextEvent(
        symbol=_text(row.get("symbol"), "mark symbol"),
        observed_ts_ms=_positive_integer(row.get("observed_ts_ms"), "mark observed"),
        received_ts_ns=_positive_integer(row.get("received_ts_ns"), "mark receipt"),
        mark_price=mark,
        oracle_price=mark,
        funding_rate_hourly=0.0,
        open_interest=0.0,
        mid_price=mark,
        source=_text(row.get("source"), "mark source"),
    )


def _finalize(report: dict[str, object], inputs: _Inputs) -> None:
    source = _mapping(report.get("source"), "report source")
    if not isinstance(source, dict):
        raise ValueError("BRENTOIL lifecycle report source must be mutable")
    source["legacy_quiet_decisions_excluded"] = inputs.prefixes["decision_prefix"][
        "legacy_quiet_decisions_excluded"
    ]
    _require_report(report)
    _revalidate(inputs)
    report["observed_at_ms"] = inputs.observed_at_ms
    report["input_evidence"] = {
        **inputs.prefixes,
        "development": _path_evidence(
            inputs.paths["development"], inputs.exact["development"]
        ),
        "live_canary": _path_evidence(
            inputs.paths["live_canary"], inputs.exact["live_canary"]
        ),
        "mark_archive": inputs.mark_evidence,
    }
    report["generator_identity"] = inputs.generator


def _revalidate(inputs: _Inputs) -> None:
    for name, evidence in inputs.exact.items():
        if file_evidence(inputs.paths[name]) != evidence:
            raise ValueError(f"BRENTOIL lifecycle exact input changed: {name}")
    for name, label in (
        ("journal", "decision"),
        ("candle_ledger", "candle"),
        ("book_ledger", "book"),
    ):
        require_jsonl_prefix_unchanged(
            inputs.paths[name], inputs.prefixes[f"{label}_prefix"], label
        )
    inputs.mark_source.require_unchanged(inputs.mark_evidence)
    if _generator_identity() != inputs.generator:
        raise ValueError("BRENTOIL lifecycle generator changed during evaluation")


def _require_report(report: Mapping[str, object]) -> None:
    if not (
        report.get("symbol") == BRENTOIL_OIL_SHOCK_SYMBOL
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
    ):
        raise ValueError("BRENTOIL lifecycle report authority is invalid")


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    relative = (
        "scripts/brentoil_oil_shock_lifecycle.py",
        "src/hypervector/research/brentoil_oil_shock_lifecycle.py",
        "src/hypervector/research/brentoil_oil_shock_lifecycle_inputs.py",
        "src/hypervector/research/brentoil_oil_shock_lifecycle_models.py",
        "src/hypervector/research/hip3_oil_shock_reversion_signals.py",
        "src/hypervector/research/hip3_shadow_signal_markouts.py",
        "src/hypervector/research/hip3_shadow_lifecycle_sources.py",
        "src/hypervector/data/jsonl_prefix.py",
        "pyproject.toml",
        "uv.lock",
    )
    return {name: file_evidence(root / name) for name in relative}


def _path_evidence(path: Path, evidence: Mapping[str, object]) -> dict[str, object]:
    return {"path": str(path.resolve()), **dict(evidence)}


def _json_object(path: Path, label: str) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, label))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"BRENTOIL lifecycle {label} must be an object")
    return value


def _records(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"BRENTOIL lifecycle {label} must be a list")
    return tuple(_mapping(row, label) for row in value)


def _number(value: object, label: str) -> float:
    number = _finite_number(value, label)
    if number < 0.0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be nonnegative")
    return number


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"BRENTOIL lifecycle {label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"BRENTOIL lifecycle {label} must be finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"BRENTOIL lifecycle {label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"BRENTOIL lifecycle {label} must be non-empty text")
    return value


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("BRENTOIL lifecycle input and output paths must be distinct")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only command and print its technical status."""
    args = build_parser().parse_args(argv)
    report = run_command(args)
    print(json.dumps(report["technical_assessment"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
