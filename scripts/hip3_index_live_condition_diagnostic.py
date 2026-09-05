#!/usr/bin/env python3
"""Publish one exact report-only v51 HIP-3 live-condition diagnostic."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import cast

from hypervector.data.hip3_public_candles import (
    Hip3CandleSourceProtocol,
    Hip3PublicCandleSource,
)
from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.hip3_index_live_condition_diagnostic import (
    Hip3IndexLiveConditionConfig,
    build_hip3_index_live_condition_diagnostic,
)

Record = dict[str, object]
_BAR_MS = 900_000


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit report-only diagnostic parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--frozen-journal", type=Path, required=True)
    parser.add_argument("--observer-journal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_command(
    args: argparse.Namespace,
    *,
    candle_source: Hip3CandleSourceProtocol | None = None,
) -> Record:
    """Build and publish one immutable current-run condition report."""
    paths = _paths(args)
    exact_evidence = {key: file_evidence(path) for key, path in paths.items()}
    cohort = load_multi_asset_live_config(paths["config"], mode="observe")
    checkpoint = _json_object(paths["checkpoint"], "checkpoint")
    frozen = _json_object(paths["frozen_journal"], "frozen journal")
    route, runtime = _route_config(cohort, checkpoint, frozen, str(args.symbol))
    rows, prefix = _read_jsonl_prefix(paths["observer_journal"])
    start_ms, end_ms, observed_at_ms = _candle_bounds(rows, route)
    candles = (candle_source or Hip3PublicCandleSource()).completed_candles(
        symbol=route.symbol,
        start_ms=start_ms,
        end_ms=end_ms,
        observed_at_ms=observed_at_ms,
    )
    report = build_hip3_index_live_condition_diagnostic(
        candles=candles,
        observer_rows=rows,
        config=route,
    )
    _attach_runtime_scope(report, runtime)
    report["input_evidence"] = _input_evidence(paths, exact_evidence, prefix)
    report["generator_identity"] = _generator_identity()
    _require_unchanged_exact(paths, exact_evidence)
    _require_prefix_unchanged(paths["observer_journal"], prefix)
    write_immutable_json(Path(args.output), report)
    return report


def _paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {
        "config": Path(args.config),
        "checkpoint": Path(args.checkpoint),
        "frozen_journal": Path(args.frozen_journal),
        "observer_journal": Path(args.observer_journal),
    }
    if len(set(paths.values())) != len(paths):
        raise ValueError("live condition diagnostic input paths must be distinct")
    return paths


def _route_config(
    cohort: MultiAssetLiveConfig,
    checkpoint: Mapping[str, object],
    frozen: Mapping[str, object],
    symbol: str,
) -> tuple[Hip3IndexLiveConditionConfig, Record]:
    runtime = _runtime_identity(cohort, checkpoint)
    raw = _frozen_contract(frozen)
    provider_id = _text(raw, "provider_id")
    provider = _provider(cohort, provider_id, symbol)
    profile_ids = _mapping(raw, "profile_ids")
    signal = Hip3BreakoutPressureConfig(
        _integer(raw, "breakout_lookback_bars"),
        _integer(raw, "fast_ema"),
        _integer(raw, "slow_ema"),
        _number(raw, "minimum_abs_imbalance"),
        _number(raw, "signal_maximum_stop_bps"),
    )
    execution_stop = provider.execution_for(symbol).stop_bps
    if execution_stop != _number(raw, "execution_stop_bps"):
        raise ValueError("frozen execution stop differs from active route")
    runtime["execution_stop_bps"] = execution_stop
    return (
        Hip3IndexLiveConditionConfig(
            symbol,
            provider_id,
            _text(profile_ids, symbol),
            _utc_ms(_text(runtime, "run_started_at_utc")),
            signal,
        ),
        runtime,
    )


def _runtime_identity(
    cohort: MultiAssetLiveConfig, checkpoint: Mapping[str, object]
) -> Record:
    contract = _mapping(checkpoint, "checkpoint_contract")
    generation = _mapping(checkpoint, "configuration_generation")
    run = _mapping(_mapping(checkpoint, "audit"), "run")
    valid_contract = (
        contract.get("report_only") is True
        and contract.get("execution_authority") == "none"
        and contract.get("runtime_strategy_changed") is False
    )
    valid_generation = (
        generation.get("state") == "current_runtime_configuration"
        and generation.get("matches_runtime") is True
        and generation.get("current_profile_fingerprint") == cohort.profile_fingerprint
        and generation.get("runtime_profile_fingerprint") == cohort.profile_fingerprint
        and Path(_text(generation, "source_path")).resolve()
        == cohort.source_path.resolve()
    )
    if not valid_contract or not valid_generation:
        raise ValueError("checkpoint is not the exact current report-only runtime")
    if run.get("profile_fingerprint") != cohort.profile_fingerprint:
        raise ValueError("checkpoint run identity differs from active config")
    return {
        "run_id": _text(run, "run_id"),
        "run_started_at_utc": _text(run, "first_observed_at_utc"),
        "profile_id": cohort.profile_id,
        "profile_fingerprint": cohort.profile_fingerprint,
        "checkpoint_generated_at_utc": _text(checkpoint, "generated_at_utc"),
    }


def _frozen_contract(frozen: Mapping[str, object]) -> Record:
    valid = (
        frozen.get("schema_version") == "v51_index_source_parity_forward_v1"
        and frozen.get("mode") == "report_only"
        and frozen.get("execution_authority") == "none"
        and frozen.get("automatic_promotion") is False
        and frozen.get("runtime_strategy_changed") is False
    )
    if not valid:
        raise ValueError("frozen index signal contract is invalid")
    raw = _mapping(frozen, "frozen_signal_contract")
    if raw.get("timeframe") != "15m":
        raise ValueError("frozen index signal timeframe must be 15m")
    return raw


def _provider(
    cohort: MultiAssetLiveConfig, provider_id: str, symbol: str
) -> StrategyProviderConfig:
    matches = [
        provider for provider in cohort.providers if provider.strategy_id == provider_id
    ]
    if len(matches) != 1:
        raise ValueError("active config does not contain one exact index provider")
    provider = matches[0]
    valid = (
        provider.timeframe == "15m"
        and symbol in provider.execution_symbols
        and provider.executable_sides(symbol) == frozenset({"long", "short"})
    )
    if not valid:
        raise ValueError("active index route is not executable on both sides")
    return provider


def _candle_bounds(
    rows: list[Record], config: Hip3IndexLiveConditionConfig
) -> tuple[int, int, int]:
    decisions = [_mapping(row, "decision") for row in rows]
    boundaries = [
        _integer(row, "decision_time_ms")
        for row in decisions
        if _integer(row, "decision_time_ms") >= config.run_started_at_ms
    ]
    if not boundaries:
        raise ValueError("observer journal has no current-run decision")
    history_bars = (
        max(config.breakout.slow_ema, config.breakout.breakout_lookback_bars) + 2
    )
    start_ms = min(boundaries) - history_bars * _BAR_MS
    end_ms = max(boundaries)
    observed = [
        value
        for row in decisions
        if isinstance((value := row.get("observed_at_ms")), int)
    ]
    return start_ms, end_ms, max(observed, default=end_ms + 15_000)


def _attach_runtime_scope(report: Record, runtime: Record) -> None:
    scope = _mapping(report, "scope")
    scope.update(runtime)
    report["scope"] = scope


def _read_jsonl_prefix(path: Path) -> tuple[list[Record], Record]:
    content = path.read_bytes()
    if not content or not content.endswith(b"\n"):
        raise ValueError("observer journal prefix is empty or incomplete")
    rows: list[Record] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"observer row {line_number} must be an object")
        rows.append(cast(Record, value))
    return rows, {
        "path": str(path.resolve()),
        "bytes": len(content),
        "rows": len(rows),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _input_evidence(
    paths: Mapping[str, Path], exact: Mapping[str, Record], prefix: Record
) -> Record:
    return {
        "exact_files": {
            key: {"path": str(paths[key].resolve()), **value}
            for key, value in exact.items()
            if key != "observer_journal"
        },
        "observer_prefix": prefix,
    }


def _require_unchanged_exact(
    paths: Mapping[str, Path], expected: Mapping[str, Record]
) -> None:
    for key in ("config", "frozen_journal"):
        if file_evidence(paths[key]) != expected[key]:
            raise RuntimeError(f"live condition {key} changed during evaluation")


def _require_prefix_unchanged(path: Path, expected: Mapping[str, object]) -> None:
    length = _integer(expected, "bytes")
    with path.open("rb") as handle:
        content = handle.read(length)
    if len(content) != length or hashlib.sha256(content).hexdigest() != expected.get(
        "sha256"
    ):
        raise RuntimeError("observer journal prefix changed during evaluation")


def _generator_identity() -> Record:
    root = Path(__file__).parents[1]
    paths = (
        Path(__file__),
        root / "src/hypervector/research/hip3_index_live_condition_diagnostic.py",
        root / "src/hypervector/research/hip3_breakout_pressure_signals.py",
        root / "src/hypervector/live/multi_asset_live_config.py",
        root / "pyproject.toml",
        root / "uv.lock",
    )
    return {
        "files": [
            {"path": str(path.resolve()), **file_evidence(path)} for path in paths
        ]
    }


def _json_object(path: Path, label: str) -> Record:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Record, value)


def _mapping(row: Mapping[str, object], key: str) -> Record:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"live condition {key} must be an object")
    return dict(value)


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"live condition {key} must be text")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"live condition {key} must be an integer")
    return value


def _number(row: Mapping[str, object], key: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"live condition {key} must be numeric")
    return float(value)


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000)


def main() -> int:
    """Run the report-only CLI."""
    report = run_command(build_parser().parse_args())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
