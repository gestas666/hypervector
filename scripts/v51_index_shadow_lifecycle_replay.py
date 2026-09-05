#!/usr/bin/env python3
"""Publish one immutable report-only v51 index lifecycle replay."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
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
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.hip3_shadow_command_sources import (
    CandleFetcher,
    FundingFetcher,
    bounded_books,
    bounded_decisions,
    completed_candles,
    funding_snapshot,
)
from hypervector.research.hip3_shadow_lifecycle_sources import (
    FrozenHip3MarkArchive,
    Hip3MarkSourceProtocol,
)
from hypervector.research.v51_index_lifecycle_contract import (
    V51IndexLifecycleContract,
    load_v51_index_lifecycle_contract,
)
from hypervector.research.v51_index_shadow_lifecycle import (
    build_v51_index_shadow_lifecycle,
)

Record = dict[str, object]
_INTERVAL_15M_MS = 15 * 60_000
_INTERVAL_1M_MS = 60_000
_DEFAULT_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_six_asset_profit_lock_candidate_v51.toml"
)
_DEFAULT_STRESS = Path(
    "data/logs/research/bidirectional_cohort/v51_growth_sizing_stress_20260813_v1.json"
)


@dataclass(frozen=True)
class _CommandInputs:
    paths: dict[str, Path]
    exact: dict[str, dict[str, object]]
    contract: V51IndexLifecycleContract
    decisions: tuple[Record, ...]
    books: tuple[Record, ...]
    journal_evidence: dict[str, object]
    book_evidence: dict[str, object]
    observed_at: int
    candles_15m: pd.DataFrame
    candles_1m: pd.DataFrame
    funding: pd.DataFrame
    mark_source: Hip3MarkSourceProtocol
    marks: tuple[Record, ...]
    mark_evidence: dict[str, object]
    generator: dict[str, object]


@dataclass(frozen=True)
class _AcquiredMarket:
    decisions: tuple[Record, ...]
    books: tuple[Record, ...]
    journal_evidence: dict[str, object]
    book_evidence: dict[str, object]
    observed_at: int
    candles_15m: pd.DataFrame
    candles_1m: pd.DataFrame
    funding: pd.DataFrame
    mark_source: Hip3MarkSourceProtocol
    marks: tuple[Record, ...]
    mark_evidence: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    """Build the execution-incapable v51 replay parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", choices=("xyz:SP500", "xyz:SPCX"), required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--stress-evidence", type=Path, default=_DEFAULT_STRESS)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--book-ledger", type=Path, required=True)
    parser.add_argument("--observed-at-ms", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    candle_fetcher: CandleFetcher = fetch_hl_ohlcv_snapshot,
    funding_fetcher: FundingFetcher = fetch_hl_funding_history,
    mark_source: Hip3MarkSourceProtocol | None = None,
) -> dict[str, object]:
    """Acquire, verify, replay, and atomically publish one v51 route."""
    output = Path(args.output)
    _require_new_output(output)
    inputs = _prepare(args, output, candle_fetcher, funding_fetcher, mark_source)
    report = build_v51_index_shadow_lifecycle(
        config_path=inputs.paths["config"],
        stress_path=inputs.paths["stress"],
        symbol=inputs.contract.symbol,
        decision_rows=inputs.decisions,
        book_rows=inputs.books,
        candles_15m=inputs.candles_15m,
        candles_1m=inputs.candles_1m,
        mark_rows=inputs.marks,
        funding_rows=inputs.funding,
    )
    _finalize(report, inputs)
    write_immutable_json(output, report)
    return report


def _prepare(
    args: argparse.Namespace,
    output: Path,
    candle_fetcher: CandleFetcher,
    funding_fetcher: FundingFetcher,
    mark_source: Hip3MarkSourceProtocol | None,
) -> _CommandInputs:
    paths = _paths(args)
    _require_distinct((*paths.values(), output))
    exact = {
        name: file_evidence(path)
        for name, path in paths.items()
        if name in {"config", "stress"}
    }
    contract = load_v51_index_lifecycle_contract(
        paths["config"], paths["stress"], str(args.symbol)
    )
    acquired = _acquire_market(
        args, paths, contract, candle_fetcher, funding_fetcher, mark_source
    )
    return _CommandInputs(
        paths,
        exact,
        contract,
        acquired.decisions,
        acquired.books,
        acquired.journal_evidence,
        acquired.book_evidence,
        acquired.observed_at,
        acquired.candles_15m,
        acquired.candles_1m,
        acquired.funding,
        acquired.mark_source,
        acquired.marks,
        acquired.mark_evidence,
        _generator_identity(),
    )


def _acquire_market(
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    contract: V51IndexLifecycleContract,
    candle_fetcher: CandleFetcher,
    funding_fetcher: FundingFetcher,
    mark_source: Hip3MarkSourceProtocol | None,
) -> _AcquiredMarket:
    decisions, journal_evidence = read_jsonl_prefix(
        paths["journal"], "decision journal"
    )
    books, book_evidence = read_jsonl_prefix(paths["book_ledger"], "book ledger")
    observed_at = _positive_integer(args.observed_at_ms, "observed-at-ms")
    bounded_decision_rows, start = bounded_decisions(
        decisions, observed_at, _INTERVAL_15M_MS
    )
    bounded_book_rows = bounded_books(books, observed_at)
    candles_15m, candles_1m, funding = _public_frames(
        contract, candle_fetcher, funding_fetcher, start, observed_at
    )
    source = mark_source or FrozenHip3MarkArchive()
    marks, mark_evidence = source.load(
        data_root=Path(args.data_root),
        symbol=contract.symbol,
        start_ms=start,
        end_ms=observed_at,
    )
    return _AcquiredMarket(
        bounded_decision_rows,
        bounded_book_rows,
        journal_evidence,
        book_evidence,
        observed_at,
        candles_15m,
        candles_1m,
        funding,
        source,
        marks,
        mark_evidence,
    )


def _public_frames(
    contract: V51IndexLifecycleContract,
    candle_fetcher: CandleFetcher,
    funding_fetcher: FundingFetcher,
    start: int,
    observed_at: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signal_start = _signal_warmup_start(contract, start)
    candles_15m = completed_candles(
        candle_fetcher,
        contract.symbol,
        "15m",
        _INTERVAL_15M_MS,
        signal_start,
        observed_at,
    )
    candles_1m = completed_candles(
        candle_fetcher,
        contract.symbol,
        "1m",
        _INTERVAL_1M_MS,
        start,
        observed_at,
    )
    funding = funding_snapshot(
        funding_fetcher, contract.symbol, candles_15m, observed_at
    )
    return candles_15m, candles_1m, funding


def _signal_warmup_start(
    contract: V51IndexLifecycleContract, lifecycle_start: int
) -> int:
    """Return the earliest bar needed for exact breakout and EMA state."""
    signal = contract.replay_config.signal_config
    required = max(signal.breakout_lookback_bars, signal.slow_ema) + 2
    start = lifecycle_start - (required - 1) * _INTERVAL_15M_MS
    if start <= 0:
        raise ValueError("v51 index lifecycle signal warmup precedes the epoch")
    return start


def _finalize(report: dict[str, object], inputs: _CommandInputs) -> None:
    _require_report_contract(report, inputs.contract)
    _revalidate(inputs)
    report["input_evidence"] = _input_evidence(inputs)
    report["source_snapshots"] = {
        "candles_15m": _frame_records(inputs.candles_15m),
        "candles_1m": _frame_records(inputs.candles_1m),
        "funding": _frame_records(inputs.funding),
    }
    report["generator_identity"] = inputs.generator
    report["observed_at_ms"] = inputs.observed_at


def _revalidate(inputs: _CommandInputs) -> None:
    for name, expected in inputs.exact.items():
        if file_evidence(inputs.paths[name]) != expected:
            raise ValueError(f"v51 index lifecycle exact input changed: {name}")
    require_jsonl_prefix_unchanged(
        inputs.paths["journal"], inputs.journal_evidence, "decision journal"
    )
    require_jsonl_prefix_unchanged(
        inputs.paths["book_ledger"], inputs.book_evidence, "book ledger"
    )
    inputs.mark_source.require_unchanged(inputs.mark_evidence)
    if _generator_identity() != inputs.generator:
        raise ValueError("v51 index lifecycle generator changed during evaluation")


def _input_evidence(inputs: _CommandInputs) -> dict[str, object]:
    return {
        "config": _path_evidence(inputs.paths["config"], inputs.exact["config"]),
        "stress": _path_evidence(inputs.paths["stress"], inputs.exact["stress"]),
        "journal_prefix": inputs.journal_evidence,
        "book_ledger_prefix": inputs.book_evidence,
        "mark_archive": inputs.mark_evidence,
        "candles_15m": _frame_evidence(inputs.candles_15m),
        "candles_1m": _frame_evidence(inputs.candles_1m),
        "funding": _frame_evidence(inputs.funding),
    }


def _require_report_contract(
    report: Mapping[str, object], contract: V51IndexLifecycleContract
) -> None:
    safe = (
        report.get("symbol") == contract.symbol
        and report.get("provider_id") == contract.provider_id
        and report.get("runtime_profile_id") == contract.profile_id
        and report.get("runtime_profile_fingerprint") == contract.profile_fingerprint
        and report.get("execution_authority") == "none"
        and report.get("automatic_promotion") is False
        and report.get("runtime_strategy_changed") is False
    )
    if not safe:
        raise ValueError("v51 index lifecycle report identity or authority is invalid")


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "config": Path(args.config),
        "stress": Path(args.stress_evidence),
        "journal": Path(args.journal),
        "book_ledger": Path(args.book_ledger),
    }


def _generator_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parents[1]
    relative = (
        "scripts/v51_index_shadow_lifecycle_replay.py",
        "src/hypervector/cohort_profit_lock_policy.py",
        "src/hypervector/data/jsonl_prefix.py",
        "src/hypervector/data/hip3_mark_snapshot_recorder.py",
        "src/hypervector/research/hip3_shadow_command_sources.py",
        "src/hypervector/research/hip3_shadow_execution_contract.py",
        "src/hypervector/research/hip3_shadow_lifecycle_exits.py",
        "src/hypervector/research/hip3_shadow_lifecycle_inputs.py",
        "src/hypervector/research/hip3_shadow_lifecycle_models.py",
        "src/hypervector/research/hip3_shadow_lifecycle_replay.py",
        "src/hypervector/research/hip3_shadow_lifecycle_reporting.py",
        "src/hypervector/research/hip3_shadow_lifecycle_sources.py",
        "src/hypervector/research/v51_index_lifecycle_contract.py",
        "src/hypervector/research/v51_index_shadow_lifecycle.py",
        "src/hypervector/live/hip3_breakout_shadow_specs.py",
        "src/hypervector/live/cohort_execution_plan.py",
        "src/hypervector/live/multi_asset_live_config.py",
        "pyproject.toml",
        "uv.lock",
    )
    return {name: file_evidence(root / name) for name in relative}


def _frame_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    rendered = frame.copy()
    for column in rendered.columns:
        if pd.api.types.is_datetime64_any_dtype(rendered[column]):
            rendered[column] = pd.to_datetime(rendered[column], utc=True).map(
                lambda value: value.isoformat()
            )
    return cast(list[dict[str, object]], rendered.to_dict(orient="records"))


def _frame_evidence(frame: pd.DataFrame) -> dict[str, object]:
    content = frame.to_csv(index=False, lineterminator="\n").encode()
    return {
        "rows": len(frame),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _path_evidence(path: Path, evidence: Mapping[str, object]) -> dict[str, object]:
    return {"path": str(path.resolve()), **dict(evidence)}


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"v51 index lifecycle {label} must be a positive integer")
    return value


def _require_distinct(paths: Sequence[Path]) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("v51 index lifecycle input and output paths must be distinct")


def _require_new_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"immutable JSON output exists: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the report-only command and print a compact technical result."""
    args = build_parser().parse_args(argv)
    report = run_command(args)
    nominal = cast(Mapping[str, object], report["nominal"])
    print(
        json.dumps(
            {
                "symbol": report["symbol"],
                "completed_lifecycles": nominal.get("completed_lifecycles"),
                "censored_lifecycles": nominal.get("censored_lifecycles"),
                "execution_authority": "none",
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
