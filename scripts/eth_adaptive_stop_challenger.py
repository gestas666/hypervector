#!/usr/bin/env python3
"""Run the preregistered report-only ETH adaptive-stop challenger."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping, Sequence

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.eth_adaptive_stop_challenger import (
    ANCHOR_COLUMN,
    build_eth_adaptive_stop_market,
)
from hypervector.research.eth_adaptive_stop_evaluation import (
    compare_equal_risk,
    evaluate_eth_promotion,
)
from hypervector.research.eth_pullback_replay import (
    ETH_PULLBACK_STRATEGY,
    replay_eth_precompression_pullback,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits

_BARS = Path("data/cache/ETH_1m_365d.parquet")
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v62-eth-brentoil-exit-priority-preregistration-20260825-v1.json"
)
_CONSTRUCTION_END = "2026-03-28T12:00:00Z"
_PURGE_END = "2026-03-29T12:00:00Z"
_CONFIRMATION_END = "2026-05-28T12:00:00Z"
_AUDIT_START = "2026-05-29T00:00:00Z"
_AUDIT_END = "2026-07-28T00:00:00Z"


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build_control_config() -> HypeExitReplayConfig:
    """Return the fixed-60 live-parity control contract."""
    return HypeExitReplayConfig(
        stop_bps=60.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
        exit_on_opposite_signal=True,
    )


def build_candidate_config() -> HypeExitReplayConfig:
    """Return the frozen adaptive 60-to-120-bps challenger contract."""
    return HypeExitReplayConfig(
        stop_bps=60.0,
        stop_anchor_column=ANCHOR_COLUMN,
        minimum_stop_bps=60.0,
        maximum_stop_bps=120.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
        exit_on_opposite_signal=True,
    )


def select_partition_market(
    market: pd.DataFrame,
    *,
    signal_start_utc: str | None,
    signal_end_exclusive_utc: str,
    replay_end_exclusive_utc: str,
) -> pd.DataFrame:
    """Retain causal history while admitting only partition-owned signals."""
    replay_end = pd.Timestamp(replay_end_exclusive_utc)
    signal_end = pd.Timestamp(signal_end_exclusive_utc)
    output = market.loc[market.index < replay_end].copy()
    eligible = output.index < signal_end
    if signal_start_utc is not None:
        eligible &= output.index >= pd.Timestamp(signal_start_utc)
    output.loc[~eligible, "entry_side"] = None
    if len(output) < 2:
        raise ValueError("ETH adaptive-stop partition has insufficient bars")
    return output


def source_signal_parity(control: pd.DataFrame, candidate: pd.DataFrame) -> bool:
    """Compare exact source signal timestamps and directions."""
    return _signals(control) == _signals(candidate)


def run(args: argparse.Namespace) -> dict[str, object]:
    """Execute the frozen replay once and return its immutable evidence payload."""
    inputs = (args.bars, args.funding, args.preregistration)
    for path in inputs:
        _require_file(path)
    preregistration = _load_preregistration(args.preregistration)
    input_evidence = _capture_input_evidence(inputs)
    _validate_preregistered_inputs(preregistration, args, input_evidence)
    generator_identity = _generator_identity()
    bars = _slice_bars(pd.read_parquet(args.bars), _AUDIT_END)
    funding = pd.read_parquet(args.funding)
    source = replay_eth_precompression_pullback(bars, funding)
    control_market = source.market
    candidate_market = build_eth_adaptive_stop_market(control_market)
    parity = source_signal_parity(control_market, candidate_market)
    partitions = _run_partitions(control_market, candidate_market)
    decision = evaluate_eth_promotion(partitions, source_signal_parity=parity)
    artifact = {
        "schema_version": 1,
        "mode": "report_only",
        "hypothesis_id": preregistration.get("hypothesis_id"),
        "strategy_id": ETH_PULLBACK_STRATEGY,
        "symbol": "ETH",
        "source_signals": _signal_evidence(control_market, candidate_market, parity),
        "source_replay": {
            "market_evidence": asdict(source.market_evidence),
            "policy_evidence": asdict(source.policy_evidence),
        },
        "partitions": partitions,
        "promotion_evaluation": decision,
        "input_evidence": input_evidence,
        "generator_identity": generator_identity,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    _require_unchanged_inputs(input_evidence, inputs)
    require_unchanged_dependencies(generator_identity, _project_root())
    return artifact


def _run_partitions(
    control_market: pd.DataFrame,
    candidate_market: pd.DataFrame,
) -> dict[str, Mapping[str, object]]:
    windows = {
        "construction": (None, _CONSTRUCTION_END, _PURGE_END),
        "confirmation": (_PURGE_END, _CONFIRMATION_END, _CONFIRMATION_END),
        "opened_final_audit": (_AUDIT_START, _AUDIT_END, _AUDIT_END),
    }
    return {
        name: _run_partition(control_market, candidate_market, *window)
        for name, window in windows.items()
    }


def _run_partition(
    control_market: pd.DataFrame,
    candidate_market: pd.DataFrame,
    signal_start: str | None,
    signal_end: str,
    replay_end: str,
) -> Mapping[str, object]:
    control = select_partition_market(
        control_market,
        signal_start_utc=signal_start,
        signal_end_exclusive_utc=signal_end,
        replay_end_exclusive_utc=replay_end,
    )
    candidate = select_partition_market(
        candidate_market,
        signal_start_utc=signal_start,
        signal_end_exclusive_utc=signal_end,
        replay_end_exclusive_utc=replay_end,
    )
    policy = HypeExitPolicy("eth_adaptive_stop_partition_replay")
    control_report = replay_hype_breakout_exits(control, policy, build_control_config())
    candidate_report = replay_hype_breakout_exits(
        candidate, policy, build_candidate_config()
    )
    comparison = compare_equal_risk(control_report.trades, candidate_report.trades)
    return {
        **comparison,
        "source_signal_parity": source_signal_parity(control, candidate),
        "source_signal_count": len(_signals(control)),
        "control_occupied_signals": control_report.occupied_signals,
        "candidate_occupied_signals": candidate_report.occupied_signals,
    }


def _signals(market: pd.DataFrame) -> tuple[tuple[str, str], ...]:
    selected = market.loc[market["entry_side"].isin(("long", "short")), "entry_side"]
    return tuple(
        (timestamp.isoformat(), str(side)) for timestamp, side in selected.items()
    )


def _signal_evidence(
    control: pd.DataFrame,
    candidate: pd.DataFrame,
    parity: bool,
) -> dict[str, object]:
    control_signals = _signals(control)
    candidate_signals = _signals(candidate)
    return {
        "exact_timestamp_and_direction_parity": parity,
        "control_count": len(control_signals),
        "candidate_count": len(candidate_signals),
        "control_sha256": _signal_sha256(control_signals),
        "candidate_sha256": _signal_sha256(candidate_signals),
    }


def _signal_sha256(signals: tuple[tuple[str, str], ...]) -> str:
    payload = json.dumps(signals, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _slice_bars(bars: pd.DataFrame, end_exclusive_utc: str) -> pd.DataFrame:
    if "timestamp" not in bars:
        raise ValueError("ETH adaptive-stop bars are missing timestamp")
    timestamps = pd.to_datetime(bars["timestamp"], utc=True)
    output = bars.loc[timestamps < pd.Timestamp(end_exclusive_utc)].copy()
    if output.empty:
        raise ValueError("ETH adaptive-stop source window has no bars")
    return output


def _load_preregistration(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ETH adaptive-stop preregistration must be an object")
    if payload.get("status") != "preregistered_before_candidate_replay":
        raise ValueError("ETH adaptive-stop preregistration status is invalid")
    return payload


def _capture_input_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _validate_preregistered_inputs(
    preregistration: Mapping[str, object],
    args: argparse.Namespace,
    evidence: Mapping[str, object],
) -> None:
    declared = preregistration.get("input_evidence")
    if not isinstance(declared, list):
        raise ValueError("ETH preregistration input evidence is missing")
    expected = {
        Path(str(item["path"])).name: item
        for item in declared
        if isinstance(item, dict) and "path" in item
    }
    for path in (args.bars, args.funding):
        actual = evidence.get(str(path))
        frozen = expected.get(path.name)
        if not isinstance(actual, Mapping) or not isinstance(frozen, Mapping):
            raise ValueError(f"ETH preregistered source is missing: {path}")
        if actual.get("sha256") != frozen.get("sha256") or actual.get(
            "bytes"
        ) != frozen.get("bytes"):
            raise ValueError(f"ETH preregistered source changed: {path}")


def _require_unchanged_inputs(
    evidence: Mapping[str, object], paths: tuple[Path, ...]
) -> None:
    for path in paths:
        expected = evidence.get(str(path))
        if not isinstance(expected, dict):
            raise ValueError(f"ETH adaptive-stop evidence is missing: {path}")
        require_unchanged_file(path, expected)


def _generator_identity() -> dict[str, object]:
    root = _project_root()
    paths = loaded_project_source_paths(root, Path(__file__))
    return source_dependency_identity(root, paths)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"ETH adaptive-stop source is missing: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable artifact and print its bounded disposition."""
    args = build_parser().parse_args(argv)
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "promotion_evaluation": artifact["promotion_evaluation"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
