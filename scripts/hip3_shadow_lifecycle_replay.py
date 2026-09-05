#!/usr/bin/env python3
"""Publish one immutable report-only HIP-3 prospective lifecycle replay."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import cast

import pandas as pd

from hypervector.data.hl import fetch_hl_funding_history, fetch_hl_ohlcv_snapshot
from hypervector.data.jsonl_prefix import (
    read_jsonl_prefix,
    require_jsonl_prefix_unchanged,
)
from hypervector.data.oxa_api import validate_market_symbol
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.hip3_breakout_shadow_specs import (
    HIP3_SHADOW_SPECS,
    Hip3BreakoutShadowSpec,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_lifecycle_inputs import INTERVAL_MS
from hypervector.research.hip3_shadow_lifecycle_command_inputs import (
    Hip3ShadowMarketInputs,
    load_shadow_market_inputs,
)
from hypervector.research.hip3_shadow_execution_contract import (
    LIVE_BOUND_HIP3_SYMBOLS,
    bind_live_execution_contract,
)
from hypervector.research.hip3_shadow_command_sources import (
    CandleFetcher,
    FundingFetcher,
    bounded_books,
    bounded_decisions,
)
from hypervector.research.hip3_shadow_lifecycle_replay import (
    build_hip3_shadow_lifecycle_replay,
)
from hypervector.research.hip3_close_only_opposite_exit import (
    build_close_only_opposite_exit_comparison,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    Hip3MarkSourceProtocol,
)
from hypervector.research.hip3_shadow_lifecycle_archive_marks import (
    configured_archive_mark_source,
)
from hypervector.research.hip3_shadow_route_friction import shadow_route_friction
from hypervector.research.hip3_shadow_report_frames import (
    frame_evidence,
    frame_records,
)
from hypervector.research.hip3_shadow_frozen_candles import (
    configured_frozen_candle_fetcher,
)

Record = dict[str, object]


@dataclass(frozen=True)
class _CommandInputs:
    spec: Hip3BreakoutShadowSpec
    paths: dict[str, Path]
    exact: dict[str, dict[str, object]]
    ledgers: _BoundedLedgers
    market: Hip3ShadowMarketInputs
    config: Hip3ShadowLifecycleConfig
    generator: dict[str, object]


@dataclass(frozen=True)
class _BoundedLedgers:
    decisions: tuple[Record, ...]
    books: tuple[Record, ...]
    journal_evidence: dict[str, object]
    book_evidence: dict[str, object]
    observed_at_ms: int
    start_ms: int


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable lifecycle command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--book-ledger", type=Path, required=True)
    parser.add_argument("--development-diagnostic", type=Path, required=True)
    parser.add_argument("--fee-evidence", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path)
    parser.add_argument("--observed-at-ms", type=int, required=True)
    parser.add_argument("--decision-start-ms", type=int)
    parser.add_argument("--signal-start-ms", type=int)
    parser.add_argument("--signal-candle-ledger", type=Path)
    parser.add_argument("--profit-lock-candle-ledger", type=Path)
    parser.add_argument("--notional-usd", type=float, default=5_000.0)
    parser.add_argument("--stress-extra-bps-per-side", type=float, default=2.0)
    parser.add_argument("--maximum-book-lateness-ms", type=int, default=15_000)
    parser.add_argument("--maximum-mark-gap-ms", type=int, default=5_000)
    parser.add_argument("--archive-mark-repair-audit", type=Path)
    parser.add_argument("--close-only-opposite-comparison", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    candle_fetcher: CandleFetcher = fetch_hl_ohlcv_snapshot,
    funding_fetcher: FundingFetcher = fetch_hl_funding_history,
    mark_source: Hip3MarkSourceProtocol | None = None,
) -> dict[str, object]:
    """Reconstruct, verify, and atomically publish one no-authority replay."""
    output = Path(args.output)
    _require_new_output(output)
    inputs = _prepare_command(
        args, output, candle_fetcher, funding_fetcher, mark_source
    )
    report = _build_report(inputs, bool(args.close_only_opposite_comparison))
    _finalize_report(
        report,
        inputs.spec,
        inputs.paths,
        inputs.exact,
        inputs.ledgers,
        inputs.market,
        inputs.generator,
    )
    write_immutable_json(output, report)
    return report


def _build_report(
    inputs: _CommandInputs, close_only_comparison: bool
) -> dict[str, object]:
    builder = (
        build_close_only_opposite_exit_comparison
        if close_only_comparison
        else build_hip3_shadow_lifecycle_replay
    )
    return builder(
        decision_rows=inputs.ledgers.decisions,
        book_rows=inputs.ledgers.books,
        candles=inputs.market.candles,
        mark_rows=inputs.market.marks,
        funding_rows=inputs.market.funding,
        config=inputs.config,
        profit_lock_bars=inputs.market.profit_lock_bars,
    )


def _prepare_command(
    args: argparse.Namespace,
    output: Path,
    candle_fetcher: CandleFetcher,
    funding_fetcher: FundingFetcher,
    mark_source: Hip3MarkSourceProtocol | None,
) -> _CommandInputs:
    spec = _spec(str(args.symbol))
    candle_fetcher = configured_frozen_candle_fetcher(
        spec.symbol,
        getattr(args, "signal_candle_ledger", None),
        getattr(args, "profit_lock_candle_ledger", None),
        output,
        candle_fetcher,
        required=spec.symbol in LIVE_BOUND_HIP3_SYMBOLS
        and candle_fetcher is fetch_hl_ohlcv_snapshot,
    )
    paths = _paths(args)
    _require_distinct((*paths.values(), output))
    exact = {
        name: file_evidence(path)
        for name, path in paths.items()
        if name not in {"journal", "book_ledger"}
    }
    diagnostic = _json_object(paths["development_diagnostic"], "diagnostic")
    fee_report = _json_object(paths["fee_evidence"], "fee evidence")
    fee, latency = shadow_route_friction(diagnostic, fee_report, spec)
    config = _config(args, spec, fee, latency)
    ledgers = _bounded_ledgers(args, paths)
    source = _configured_mark_source(args, mark_source)
    market = load_shadow_market_inputs(
        candle_fetcher=candle_fetcher,
        funding_fetcher=funding_fetcher,
        mark_source=source,
        data_root=Path(args.data_root),
        spec=spec,
        config=config,
        start_ms=ledgers.start_ms,
        observed_at_ms=ledgers.observed_at_ms,
        signal_start_ms=getattr(args, "signal_start_ms", None),
    )
    return _CommandInputs(
        spec,
        paths,
        exact,
        ledgers,
        market,
        config,
        _generator_identity(),
    )


def _bounded_ledgers(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
) -> _BoundedLedgers:
    decisions, journal = read_jsonl_prefix(paths["journal"], "decision journal")
    books, book_evidence = read_jsonl_prefix(paths["book_ledger"], "book ledger")
    observed_at = _positive_integer(args.observed_at_ms, "observed-at-ms")
    bounded_decision_rows, start_ms = bounded_decisions(
        decisions,
        observed_at,
        INTERVAL_MS,
        getattr(args, "decision_start_ms", None),
    )
    return _BoundedLedgers(
        bounded_decision_rows,
        bounded_books(books, observed_at),
        journal,
        book_evidence,
        observed_at,
        start_ms,
    )


def _finalize_report(
    report: dict[str, object],
    spec: Hip3BreakoutShadowSpec,
    paths: Mapping[str, Path],
    exact: Mapping[str, Mapping[str, object]],
    ledgers: _BoundedLedgers,
    market: Hip3ShadowMarketInputs,
    generator: Mapping[str, object],
) -> None:
    _require_report_contract(report, spec)
    if report.get("schema_version") == "hip3_close_only_opposite_exit_comparison_v1":
        _require_report_contract(_mapping(report.get("control"), "control"), spec)
        _require_report_contract(_mapping(report.get("challenger"), "challenger"), spec)
    _revalidate(
        paths,
        exact,
        ledgers.journal_evidence,
        ledgers.book_evidence,
        market.mark_source,
        market.mark_evidence,
    )
    _require_generator_unchanged(generator)
    report["input_evidence"] = _input_evidence(
        paths,
        exact,
        ledgers.journal_evidence,
        ledgers.book_evidence,
        market.mark_evidence,
        market.candles,
        market.profit_lock_bars,
        market.funding,
    )
    report["source_snapshots"] = {
        "candles": frame_records(market.candles),
        "profit_lock_candles": []
        if market.profit_lock_bars is None
        else frame_records(market.profit_lock_bars),
        "funding": frame_records(market.funding),
    }
    report["generator_identity"] = dict(generator)
    report["observed_at_ms"] = ledgers.observed_at_ms


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {
        "journal": Path(args.journal),
        "book_ledger": Path(args.book_ledger),
        "development_diagnostic": Path(args.development_diagnostic),
        "fee_evidence": Path(args.fee_evidence),
    }
    execution = getattr(args, "execution_config", None)
    if execution is not None:
        paths["execution_config"] = Path(execution)
    return paths


def _configured_mark_source(
    args: argparse.Namespace, base: Hip3MarkSourceProtocol | None
) -> Hip3MarkSourceProtocol | None:
    return configured_archive_mark_source(
        getattr(args, "archive_mark_repair_audit", None),
        Path(args.data_root),
        str(args.symbol),
        int(args.maximum_mark_gap_ms),
        base,
    )


def _spec(value: str) -> Hip3BreakoutShadowSpec:
    dex, separator, asset = value.strip().partition(":")
    if not separator:
        raise ValueError("HIP-3 lifecycle requires an exact xyz symbol")
    symbol = f"{dex.lower()}:{asset.upper()}"
    validate_market_symbol(symbol, "hip3")
    matches = [
        candidate for candidate in HIP3_SHADOW_SPECS if candidate.symbol == symbol
    ]
    if len(matches) != 1:
        raise ValueError(f"HIP-3 lifecycle has no frozen shadow spec for {symbol}")
    return matches[0]


def _config(
    args: argparse.Namespace,
    spec: Hip3BreakoutShadowSpec,
    fee: float,
    latency: float,
) -> Hip3ShadowLifecycleConfig:
    base = Hip3ShadowLifecycleConfig(
        spec.symbol,
        spec.provider_id,
        spec.profile_id,
        spec.ledger_profile_id,
        spec.config,
        fee,
        latency,
        float(args.stress_extra_bps_per_side),
        float(args.notional_usd),
        int(args.maximum_book_lateness_ms),
        int(args.maximum_mark_gap_ms),
        1_440,
        "development-diagnostic+fee-evidence",
    )
    source = getattr(args, "execution_config", None)
    if source is None:
        if spec.symbol in LIVE_BOUND_HIP3_SYMBOLS:
            raise ValueError("live-bound HIP-3 lifecycle requires --execution-config")
        return base
    return bind_live_execution_contract(base, Path(source))


def _revalidate(
    paths: Mapping[str, Path],
    exact: Mapping[str, Mapping[str, object]],
    journal: Mapping[str, object],
    books: Mapping[str, object],
    mark_source: Hip3MarkSourceProtocol,
    marks: Mapping[str, object],
) -> None:
    for name, expected in exact.items():
        if file_evidence(paths[name]) != dict(expected):
            raise ValueError(f"HIP-3 lifecycle exact input changed: {paths[name]}")
    require_jsonl_prefix_unchanged(paths["journal"], journal, "decision journal")
    require_jsonl_prefix_unchanged(paths["book_ledger"], books, "book ledger")
    mark_source.require_unchanged(marks)


def _require_report_contract(
    report: Mapping[str, object], spec: Hip3BreakoutShadowSpec
) -> None:
    safe = (
        report.get("symbol") == spec.symbol
        and report.get("provider_id") == spec.provider_id
        and report.get("profile_id") == spec.profile_id
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("HIP-3 lifecycle report authority or identity is invalid")


def _input_evidence(
    paths: Mapping[str, Path],
    exact: Mapping[str, Mapping[str, object]],
    journal: Mapping[str, object],
    books: Mapping[str, object],
    marks: Mapping[str, object],
    candles: pd.DataFrame,
    profit_lock_bars: pd.DataFrame | None,
    funding: pd.DataFrame,
) -> dict[str, object]:
    return {
        "journal_prefix": dict(journal),
        "book_ledger_prefix": dict(books),
        "development_diagnostic": _path_evidence(
            paths["development_diagnostic"], exact["development_diagnostic"]
        ),
        "fee_evidence": _path_evidence(paths["fee_evidence"], exact["fee_evidence"]),
        "execution_config": None
        if "execution_config" not in paths
        else _path_evidence(paths["execution_config"], exact["execution_config"]),
        "mark_archive": dict(marks),
        "candles": frame_evidence(candles),
        "profit_lock_candles": None
        if profit_lock_bars is None
        else frame_evidence(profit_lock_bars),
        "funding": frame_evidence(funding),
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    relative = (
        "scripts/hip3_shadow_lifecycle_replay.py",
        "src/hypervector/data/jsonl_prefix.py",
        "src/hypervector/research/hip3_shadow_lifecycle_models.py",
        "src/hypervector/research/hip3_shadow_execution_contract.py",
        "src/hypervector/research/hip3_shadow_lifecycle_command_inputs.py",
        "src/hypervector/research/hip3_shadow_lifecycle_inputs.py",
        "src/hypervector/research/hip3_shadow_lifecycle_exits.py",
        "src/hypervector/research/hip3_shadow_lifecycle_replay.py",
        "src/hypervector/research/hip3_close_only_opposite_exit.py",
        "src/hypervector/research/hip3_shadow_lifecycle_reporting.py",
        "src/hypervector/research/hip3_shadow_lifecycle_sources.py",
        "src/hypervector/research/hip3_shadow_lifecycle_archive_marks.py",
        "src/hypervector/data/oxa_price_archive.py",
        "src/hypervector/data/oxa_prices.py",
        "src/hypervector/research/hip3_shadow_route_friction.py",
        "src/hypervector/research/hip3_shadow_frozen_candles.py",
        "src/hypervector/research/hip3_shadow_report_frames.py",
        "src/hypervector/live/hip3_shadow_candle_contracts.py",
        "src/hypervector/research/hip3_shadow_signal_markouts.py",
        "src/hypervector/research/hip3_breakout_pressure_signals.py",
        "src/hypervector/research/hip3_transfer_sources.py",
        "src/hypervector/research/hip3_prospective_path_audit.py",
        "src/hypervector/live/hip3_breakout_shadow_specs.py",
        "src/hypervector/live/cohort_execution_plan.py",
        "src/hypervector/live/multi_asset_live_config.py",
        "src/hypervector/cohort_profit_lock_policy.py",
        "pyproject.toml",
        "uv.lock",
    )
    return {name: file_evidence(root / name) for name in relative}


def _require_generator_unchanged(expected: Mapping[str, object]) -> None:
    current = _generator_identity()
    if current != dict(expected):
        raise ValueError("HIP-3 lifecycle generator changed during evaluation")


def _path_evidence(path: Path, evidence: Mapping[str, object]) -> dict[str, object]:
    return {"path": str(path.resolve()), **dict(evidence)}


def _json_object(path: Path, label: str) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"HIP-3 lifecycle {label} must be an object")
    return cast(Record, value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"HIP-3 lifecycle {label} must be an object")
    return cast(Record, value)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"HIP-3 lifecycle {label} must be a positive integer")
    return value


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("HIP-3 lifecycle input and output paths must be distinct")


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable JSON output exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only command and print a compact technical summary."""
    args = build_parser().parse_args(argv)
    report = run_command(args)
    result = (
        _mapping(report.get("challenger"), "challenger result")
        if args.close_only_opposite_comparison
        else report
    )
    nominal = _mapping(result.get("nominal"), "nominal result")
    print(
        json.dumps(
            {
                "symbol": report["symbol"],
                "completed_lifecycles": nominal.get("completed_lifecycles"),
                "censored_lifecycles": nominal.get("censored_lifecycles"),
                "execution_authority": "none",
                "comparison": bool(args.close_only_opposite_comparison),
                "output": str(Path(args.output)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
