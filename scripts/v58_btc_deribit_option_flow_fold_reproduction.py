#!/usr/bin/env python3
"""Publish exact development-fold trades for the frozen BTC option-flow result."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_json,
)
from hypervector.research.btc_option_directional_flow import (
    build_causal_flow_signals,
)
from hypervector.research.btc_option_flow_experiment import (
    OptionFlowPartition,
    execution_window,
)
from hypervector.research.btc_option_flow_replay import (
    evaluate_btc_option_flow_replay,
)
from hypervector.research.btc_option_flow_result_reproduction import (
    reconcile_development_fold_summaries,
    reproduce_btc_option_flow_result,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from v58_btc_deribit_option_flow_experiment import (
    experiment_partitions,
    load_option_flow_market,
    load_registered_hourly_source,
    load_validated_preregistration,
    load_validated_protocol,
)


_REGISTERED = Path("data/cache/research/v58_btc_deribit_option_flow_source_20260822_v2")
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-long-preregistration-20260822-v4.json"
)
_PROTOCOL = Path(
    "docs/research-journal/"
    "v58-btc-deribit-option-flow-experiment-protocol-20260822-v1.json"
)
_EXPERIMENT = Path(
    "data/logs/research/v58_btc_deribit_option_flow_experiment_20260822_v1"
)
_OUTPUT = Path(
    "data/logs/research/v58_btc_deribit_option_flow_fold_reproduction_20260822_v1"
)


def build_parser() -> argparse.ArgumentParser:
    """Return the exact fold-reproduction command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registered-source", type=Path, default=_REGISTERED)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--experiment-protocol", type=Path, default=_PROTOCOL)
    parser.add_argument("--experiment", type=Path, default=_EXPERIMENT)
    parser.add_argument("--output", type=Path, default=_OUTPUT)
    parser.add_argument("--recorded-at-utc", required=True)
    return parser


def run_command(args: argparse.Namespace) -> Path:
    """Reproduce every frozen fold and atomically publish complete trades."""
    project = Path.cwd().resolve()
    dependencies = source_dependency_identity(
        project,
        loaded_project_source_paths(project, Path(__file__)),
    )
    preregistration = load_validated_preregistration(args.preregistration)
    protocol = load_validated_protocol(args.experiment_protocol)
    hourly, registered = load_registered_hourly_source(
        args.registered_source,
        args.preregistration,
        args.experiment_protocol,
    )
    market, market_evidence, market_files = load_option_flow_market(
        project, preregistration
    )
    _, folds = experiment_partitions(preregistration, protocol)
    primary = reproduce_btc_option_flow_result(args.experiment)
    expected = _development_rows(args.experiment / "report.json")
    signals = build_causal_flow_signals(hourly)
    rows, routing = replay_fold_trades(market.execution_bars, signals, folds)
    trades = pd.DataFrame.from_records(rows)
    if trades.empty:
        trades = pd.DataFrame(columns=("fold_id", "net_pnl_usd"))
    reconcile_development_fold_summaries(expected, trades)
    tracked = _tracked_inputs(args, registered, market_files, primary)
    _require_unchanged(project, dependencies, tracked)
    report = _report(
        args,
        dependencies,
        primary.to_dict(),
        market_evidence,
        expected,
        routing,
    )
    return _publish(args.output, report, trades)


def replay_fold_trades(
    execution: pd.DataFrame,
    signals: pd.DataFrame,
    folds: Sequence[OptionFlowPartition],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Replay nominal economics and return complete fold trades and routing."""
    rows: list[dict[str, object]] = []
    routing: list[dict[str, object]] = []
    for fold_id, fold in enumerate(folds):
        replay = evaluate_btc_option_flow_replay(
            execution_window(execution, fold),
            signals,
            slippage_bps_per_market_side=2.0,
            entry_start_utc=fold.start,
            entry_end_utc=fold.end,
        )
        rows.extend(
            {"fold_id": fold_id, **asdict(trade)} for trade in replay.report.trades
        )
        routing.append(
            {
                "fold_id": fold_id,
                "scheduled_long_signals": replay.long_signal_count,
                "scheduled_opposing_signals": replay.opposing_signal_count,
                "displaced_signals": replay.displaced_signal_count,
            }
        )
    return rows, routing


def _development_rows(path: Path) -> list[dict[str, object]]:
    primary = _load_mapping(path)
    rows = primary.get("development_fold_rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("option-flow primary report lacks development folds")
    return rows


def _tracked_inputs(
    args: argparse.Namespace,
    registered: Mapping[str, object],
    market_files: Sequence[tuple[Path, dict[str, object]]],
    primary: object,
) -> tuple[tuple[Path, dict[str, object]], ...]:
    values = [
        (args.preregistration, file_evidence(args.preregistration)),
        (args.experiment_protocol, file_evidence(args.experiment_protocol)),
        (
            args.registered_source / "manifest.json",
            _mapping(registered, "manifest"),
        ),
        (
            args.registered_source / "hourly_flow.parquet",
            _mapping(registered, "hourly_flow"),
        ),
    ]
    values.extend(market_files)
    for name, filename in (
        ("report", "report.json"),
        ("trades", "trades.parquet"),
        ("signals", "signals.parquet"),
    ):
        evidence = getattr(primary, name, None)
        if not isinstance(evidence, dict):
            raise ValueError(f"option-flow primary reproduction lacks {name} evidence")
        values.append((args.experiment / filename, evidence))
    return tuple(values)


def _require_unchanged(
    project: Path,
    dependencies: dict[str, object],
    tracked: Sequence[tuple[Path, dict[str, object]]],
) -> None:
    require_unchanged_dependencies(dependencies, project)
    for path, evidence in tracked:
        require_unchanged_file(path, evidence)


def _report(
    args: argparse.Namespace,
    dependencies: dict[str, object],
    primary: dict[str, object],
    market: dict[str, object],
    expected: list[dict[str, object]],
    routing: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_deribit_option_flow_fold_reproduction_v1",
        "hypothesis_id": "V58_BTC_DERIBIT_OTM_DIRECTIONAL_FLOW_LONG_V1",
        "recorded_at_utc": _utc_text(args.recorded_at_utc),
        "status": "exact_development_fold_trade_reproduction_complete",
        "authority": {
            "report_only": True,
            "execution_authority": "none",
            "live_configuration_changed": False,
            "live_change_authorized": False,
        },
        "primary_result_reproduction": primary,
        "market_source_evidence": market,
        "development_fold_rows": expected,
        "routing": routing,
        "full_trade_level_reproduction": True,
        "source_dependency_identity": dependencies,
    }


def _publish(output: Path, report: dict[str, object], trades: pd.DataFrame) -> Path:
    def writer(staging: Path) -> None:
        path = staging / "fold_trades.parquet"
        trades.to_parquet(path, index=False)
        report["files"] = {"fold_trades.parquet": file_evidence(path)}
        write_json(staging / "report.json", report)

    publish_immutable_directory(output, writer)
    return output


def _load_mapping(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"option-flow input must be an object: {path}")
    return value


def _mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise ValueError(f"option-flow input lacks object: {key}")
    return nested


def _utc_text(value: str) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise ValueError("option-flow recorded_at_utc must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def main() -> int:
    """Publish the exact fold reproduction and print its path."""
    print(run_command(build_parser().parse_args()).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
