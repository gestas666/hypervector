#!/usr/bin/env python3
"""Publish the preregistered V58 BTC subminute absorption experiment."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    publish_immutable_directory,
    write_immutable_parquet,
    write_json,
)
from hypervector.research.btc_subminute_absorption_database_replay import (
    replay_btc_absorption_from_database,
)
from hypervector.research.btc_subminute_absorption_inputs import (
    BtcAbsorptionWindow,
    btc_absorption_source_evidence,
    load_btc_absorption_inputs,
)
from hypervector.research.btc_subminute_absorption_replay import (
    BtcAbsorptionReplayConfig,
)
from hypervector.research.btc_subminute_absorption_reporting import (
    evaluate_btc_absorption_support,
    summarize_btc_absorption_replay,
)
from hypervector.research.btc_subminute_absorption_signals import (
    build_btc_absorption_signals,
)
from hypervector.research.market_cipher_data import load_verified_hourly_funding


_SCHEMA = "v58_btc_subminute_sell_flow_absorption_preregistration_v1"
_HYPOTHESIS = "V58_BTC_SUBMINUTE_SELL_FLOW_ABSORPTION_LONG_V1"
_GENERATORS = (
    "scripts/v58_btc_subminute_absorption.py",
    "src/hypervector/research/btc_subminute_absorption_inputs.py",
    "src/hypervector/research/btc_subminute_absorption_signals.py",
    "src/hypervector/research/btc_subminute_absorption_replay.py",
    "src/hypervector/research/btc_subminute_absorption_database_replay.py",
    "src/hypervector/research/btc_subminute_absorption_reporting.py",
    "src/hypervector/research/market_depth_fill.py",
    "src/hypervector/research/market_cipher_data.py",
)
_FUNDING_DEFAULTS = (
    Path(
        "data/cache/vendor/hyperliquid/BTC/"
        "20250425T000000000000Z_20250728T000000000000Z_funding/funding.parquet"
    ),
    Path(
        "data/cache/vendor/hyperliquid/BTC/"
        "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
    ),
)


@dataclass(frozen=True)
class FrozenPartition:
    """One preregistered half-open historical partition."""

    name: str
    start_utc: datetime
    end_utc: datetime

    @property
    def window(self) -> BtcAbsorptionWindow:
        """Return the input extractor window."""
        return BtcAbsorptionWindow(self.start_utc, self.end_utc)


def build_parser() -> argparse.ArgumentParser:
    """Return the fixed report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/research/market.duckdb")
    )
    parser.add_argument("--funding", type=Path, action="append", default=None)
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(
            "docs/research-journal/"
            "v58-btc-subminute-sell-flow-absorption-preregistration-20260821-v1.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/logs/research/bidirectional_cohort/"
            "v58_btc_subminute_sell_flow_absorption_20260821_v1"
        ),
    )
    return parser


def frozen_partitions() -> tuple[FrozenPartition, ...]:
    """Return the three exact preregistered historical windows."""
    return (
        FrozenPartition(
            "development",
            datetime(2025, 4, 25, tzinfo=UTC),
            datetime(2026, 1, 29, tzinfo=UTC),
        ),
        FrozenPartition(
            "validation",
            datetime(2026, 1, 29, tzinfo=UTC),
            datetime(2026, 4, 29, tzinfo=UTC),
        ),
        FrozenPartition(
            "pseudo_holdout",
            datetime(2026, 4, 29, tzinfo=UTC),
            datetime(2026, 7, 28, tzinfo=UTC),
        ),
    )


def frozen_replay_configs() -> tuple[BtcAbsorptionReplayConfig, ...]:
    """Return nominal, latency stress, and public-trade stop scenarios."""
    return (
        BtcAbsorptionReplayConfig(),
        BtcAbsorptionReplayConfig(
            scenario="latency_and_slippage_stress",
            entry_latency_ms=2_000,
            additional_entry_slippage_bps=3.0,
        ),
        BtcAbsorptionReplayConfig(
            scenario="public_trade_stop_proxy",
            stop_trigger_proxy="public_trade",
        ),
    )


def validate_preregistration_payload(payload: object) -> dict[str, object]:
    """Return a validated authority-none preregistration mapping."""
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA:
        raise ValueError("BTC absorption preregistration schema drifted")
    if payload.get("hypothesis_id") != _HYPOTHESIS:
        raise ValueError("BTC absorption preregistration identity drifted")
    authority = payload.get("authority")
    if (
        not isinstance(authority, dict)
        or authority.get("execution_authority") != "none"
    ):
        raise ValueError("BTC absorption preregistration authority is not none")
    return payload


def run_command(args: argparse.Namespace) -> Path:
    """Evaluate all frozen rows and publish one immutable evidence bundle."""
    funding_paths = tuple(args.funding or _FUNDING_DEFAULTS)
    prereg_before = file_evidence(args.preregistration)
    prereg = validate_preregistration_payload(_load_json(args.preregistration))
    partitions = frozen_partitions()
    funding = load_verified_hourly_funding(
        list(funding_paths),
        pd.Timestamp(partitions[0].start_utc),
        pd.Timestamp(partitions[-1].end_utc),
    )
    sources = _source_evidence(args.database, funding_paths, partitions)
    _validate_registered_sources(prereg, sources)
    generators = _generator_identity(Path(__file__).resolve().parents[1])
    summaries, trades, signals, input_rows = _evaluate(
        args.database, funding, partitions, frozen_replay_configs()
    )
    _require_unchanged(args, prereg_before, sources, partitions)
    support = evaluate_btc_absorption_support(summaries, trades)
    report = _report(
        summaries, support, sources, generators, input_rows, trades, signals
    )
    publish_result_bundle(args.output, report, trades, signals)
    return args.output


def publish_result_bundle(
    output: Path,
    report: dict[str, object],
    trades: pd.DataFrame,
    signals: pd.DataFrame,
) -> None:
    """Atomically publish report, complete signals, trades, and manifest."""

    def writer(staging: Path) -> None:
        write_json(staging / "report.json", report)
        write_immutable_parquet(staging / "signals.parquet", signals)
        write_immutable_parquet(staging / "trades.parquet", trades)
        files = {
            name: file_evidence(staging / name)
            for name in ("report.json", "signals.parquet", "trades.parquet")
        }
        write_json(
            staging / "manifest.json",
            {"schema_version": "immutable_evidence_manifest_v1", "files": files},
        )

    publish_immutable_directory(output, writer)


def _evaluate(
    database: Path,
    funding: pd.Series,
    partitions: tuple[FrozenPartition, ...],
    configs: tuple[BtcAbsorptionReplayConfig, ...],
) -> tuple[
    list[dict[str, object]], pd.DataFrame, pd.DataFrame, list[dict[str, object]]
]:
    summaries: list[dict[str, object]] = []
    trade_frames: list[pd.DataFrame] = []
    signal_frames: list[pd.DataFrame] = []
    input_rows: list[dict[str, object]] = []
    for partition in partitions:
        inputs = load_btc_absorption_inputs(database, partition.window)
        signal_report = build_btc_absorption_signals(inputs.features)
        arms = (signal_report.candidate, signal_report.control)
        overlap = _overlap_count(*arms)
        input_rows.append(_input_row(partition, inputs, signal_report, overlap))
        for arm_signals in arms:
            _evaluate_arm(
                database,
                funding,
                partition,
                arm_signals,
                configs,
                summaries,
                trade_frames,
                signal_frames,
                overlap,
            )
    trades = (
        pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    )
    signals = (
        pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    )
    return summaries, trades, signals, input_rows


def _evaluate_arm(
    database: Path,
    funding: pd.Series,
    partition: FrozenPartition,
    signals: pd.DataFrame,
    configs: tuple[BtcAbsorptionReplayConfig, ...],
    summaries: list[dict[str, object]],
    trade_frames: list[pd.DataFrame],
    signal_frames: list[pd.DataFrame],
    overlap: int,
) -> None:
    arm = str(signals["arm"].iloc[0]) if not signals.empty else "unknown"
    published_signals = signals.assign(partition=partition.name)
    signal_frames.append(published_signals)
    for config in configs:
        replay = replay_btc_absorption_from_database(
            database, signals, funding, (config,)
        )
        summary = summarize_btc_absorption_replay(
            signals, replay, partition.name, arm, config.scenario
        )
        summary["candidate_control_same_time_overlap"] = overlap
        summaries.append(summary)
        if not replay.trades.empty:
            trade_frames.append(replay.trades.assign(partition=partition.name))


def _source_evidence(
    database: Path,
    funding_paths: tuple[Path, ...],
    partitions: tuple[FrozenPartition, ...],
) -> dict[str, object]:
    return {
        "archive": {
            row.name: asdict(btc_absorption_source_evidence(database, row.window))
            for row in partitions
        },
        "funding": [
            {"path": str(path), **file_evidence(path)} for path in funding_paths
        ],
        "database_path": str(database.resolve()),
        "database_file_hash_excluded": "mutable_ingestion_database",
    }


def _validate_registered_sources(
    prereg: dict[str, object],
    sources: dict[str, object],
) -> None:
    registered_archive = prereg.get("archive_source_evidence")
    observed_archive = sources.get("archive")
    if not isinstance(registered_archive, dict) or not isinstance(
        observed_archive, dict
    ):
        raise ValueError("BTC absorption archive evidence is unavailable")
    for name, observed in observed_archive.items():
        expected = registered_archive.get(name)
        if not isinstance(expected, dict) or not isinstance(observed, dict):
            raise ValueError(f"BTC absorption archive identity missing: {name}")
        if expected.get("bundle_identity_sha256") != observed.get(
            "bundle_identity_sha256"
        ):
            raise ValueError(f"BTC absorption archive identity drifted: {name}")
    _validate_registered_funding(prereg, sources)


def _validate_registered_funding(
    prereg: dict[str, object],
    sources: dict[str, object],
) -> None:
    expected = prereg.get("funding_source_evidence")
    observed = sources.get("funding")
    if not isinstance(expected, list) or not isinstance(observed, list):
        raise ValueError("BTC absorption funding evidence is unavailable")
    expected_pairs = {
        (row.get("bytes"), row.get("sha256"))
        for row in expected
        if isinstance(row, dict)
    }
    observed_pairs = {
        (row.get("bytes"), row.get("sha256"))
        for row in observed
        if isinstance(row, dict)
    }
    if expected_pairs != observed_pairs:
        raise ValueError("BTC absorption funding evidence drifted")


def _require_unchanged(
    args: argparse.Namespace,
    prereg_before: dict[str, object],
    sources: dict[str, object],
    partitions: tuple[FrozenPartition, ...],
) -> None:
    if file_evidence(args.preregistration) != prereg_before:
        raise RuntimeError("BTC absorption preregistration changed during evaluation")
    funding_paths = tuple(args.funding or _FUNDING_DEFAULTS)
    if _source_evidence(args.database, funding_paths, partitions) != sources:
        raise RuntimeError(
            "BTC absorption registered sources changed during evaluation"
        )


def _generator_identity(project_root: Path) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    digest = hashlib.sha256()
    for relative in _GENERATORS:
        evidence = file_evidence(project_root / relative)
        files[relative] = evidence
        digest.update(f"{relative}:{evidence['sha256']}\n".encode())
    return {"aggregate_sha256": digest.hexdigest(), "files": files}


def _report(
    summaries: list[dict[str, object]],
    support: dict[str, object],
    sources: dict[str, object],
    generators: dict[str, object],
    input_rows: list[dict[str, object]],
    trades: pd.DataFrame,
    signals: pd.DataFrame,
) -> dict[str, object]:
    return {
        "schema_version": "v58_btc_subminute_absorption_result_v1",
        "hypothesis_id": _HYPOTHESIS,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "authority": {"execution_authority": "none", "orders_attempted": False},
        "runtime_strategy_changed": False,
        "automatic_live_change": False,
        "input_evidence": sources,
        "generator_identity": generators,
        "input_rows": input_rows,
        "result_rows": summaries,
        "support": support,
        "signal_sidecar_rows": len(signals),
        "trade_sidecar_rows": len(trades),
        "limitations": [
            "Historical midpoint and public-trade stop proxies are not Hyperliquid mark price.",
            "Best-bid target crossing does not reconstruct maker queue position.",
            "All partitions were opened by prior project research.",
            "Standalone BTC results do not model shared V58 portfolio displacement.",
        ],
    }


def _input_row(
    partition: FrozenPartition,
    inputs: object,
    signals: object,
    overlap: int,
) -> dict[str, object]:
    return {
        "partition": partition.name,
        "start_utc": partition.start_utc.isoformat(),
        "end_utc": partition.end_utc.isoformat(),
        "input_feature_rows": len(inputs.features),
        "input_rejections": inputs.rejections,
        "candidate_signals": len(signals.candidate),
        "control_signals": len(signals.control),
        "candidate_control_same_time_overlap": overlap,
        "candidate_blockers": signals.candidate_blockers,
        "control_blockers": signals.control_blockers,
    }


def _overlap_count(candidate: pd.DataFrame, control: pd.DataFrame) -> int:
    left = set(pd.DatetimeIndex(candidate["available_at_utc"]))
    right = set(pd.DatetimeIndex(control["available_at_utc"]))
    return len(left.intersection(right))


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"BTC absorption preregistration is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    """Run once, publish immutable evidence, and print its path."""
    output = run_command(build_parser().parse_args())
    print(output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
