#!/usr/bin/env python3
"""Evaluate the preregistered ETH opposing-breakout exit without live authority."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.eth_opposing_breakout_assessment import (
    assess_eth_opposing_breakout,
    build_eth_opposing_breakout_segment,
)
from hypervector.research.eth_opposing_breakout_exit import (
    EthOpposingBreakoutSpec,
    replay_eth_opposing_breakout_exit,
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
from hypervector.research.hype_breakout_exit_models import HypeExitTrade

_BARS = Path("data/cache/ETH_1m_365d.parquet")
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_PREREGISTRATION = Path(
    "docs/research-journal/"
    "v58-eth-opposing-breakout-exit-preregistration-20260822-v1.json"
)
_DEVELOPMENT_END = "2026-05-28T12:00:00Z"
_FINAL_START = "2026-05-29T00:00:00Z"
_FINAL_END = "2026-07-28T00:00:00Z"


def build_parser() -> argparse.ArgumentParser:
    """Return the source-bound report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run both fixed-entry windows and return one immutable-ready artifact."""
    paths = (args.bars, args.funding, args.preregistration)
    _require_files(paths)
    evidence = _data_evidence(paths)
    preregistration = _load_preregistration(args, evidence)
    generator = _generator_identity()
    bars = pd.read_parquet(args.bars)
    funding = pd.read_parquet(args.funding)
    development = replay_eth_precompression_pullback(
        _slice_bars(bars, end_utc=_DEVELOPMENT_END), funding
    )
    final_history = replay_eth_precompression_pullback(
        _slice_bars(bars, end_utc=_FINAL_END), funding
    )
    development_control = development.report.trades
    final_control = _trades_in_final_window(final_history.report.trades)
    artifact = _artifact(
        preregistration,
        evidence,
        generator,
        development.market,
        development_control,
        final_history.market,
        final_control,
    )
    _require_unchanged(evidence, paths)
    require_unchanged_dependencies(generator, _project_root())
    return artifact


def _artifact(
    preregistration: Mapping[str, object],
    evidence: Mapping[str, object],
    generator: Mapping[str, object],
    development_market: pd.DataFrame,
    development_control: tuple[HypeExitTrade, ...],
    final_market: pd.DataFrame,
    final_control: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    baseline = EthOpposingBreakoutSpec()
    delayed = EthOpposingBreakoutSpec(additional_decision_delay_minutes=1)
    development = _segment(
        development_market, development_control, baseline, delayed, folds=True
    )
    final = _segment(final_market, final_control, baseline, delayed, folds=False)
    assessment = assess_eth_opposing_breakout(development, final)
    return {
        "schema_version": 1,
        "mode": "eth_opposing_breakout_exit_historical_report_only_v1",
        "hypothesis_id": preregistration["hypothesis_id"],
        "strategy_id": ETH_PULLBACK_STRATEGY,
        "symbol": "ETH",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "current_open_lifecycle_used_for_economic_selection": False,
        "contracts": {"baseline": asdict(baseline), "delay_stress": asdict(delayed)},
        "windows": _windows(),
        "segments": {"development": development, "opened_final_60d": final},
        "assessment": assessment,
        "hypothesis_ledger_status": assessment["status"],
        "preregistration": dict(preregistration),
        "data_evidence": dict(evidence),
        "generator_identity": dict(generator),
        "limitations": _limitations(),
    }


def _segment(
    market: pd.DataFrame,
    control: tuple[HypeExitTrade, ...],
    baseline: EthOpposingBreakoutSpec,
    delayed: EthOpposingBreakoutSpec,
    *,
    folds: bool,
) -> dict[str, object]:
    candidate = replay_eth_opposing_breakout_exit(market, control, baseline)
    delay_stress = replay_eth_opposing_breakout_exit(market, control, delayed)
    return build_eth_opposing_breakout_segment(
        control,
        candidate,
        delay_stress,
        include_folds=folds,
    )


def _load_preregistration(
    args: argparse.Namespace,
    evidence: Mapping[str, object],
) -> dict[str, object]:
    payload = json.loads(args.preregistration.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ETH opposing-breakout preregistration must be an object")
    _require_preregistered_contract(payload)
    frozen = _mapping(payload["frozen_inputs"], "frozen inputs")
    _require_frozen_hash(frozen, "bars", evidence[str(args.bars)])
    _require_frozen_hash(frozen, "funding", evidence[str(args.funding)])
    return payload


def _require_preregistered_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "trigger_state": "fresh_completed_5m_BREAKOUT_onset",
        "trigger_direction": "point_in_time_5m_breakout_side_opposes_open_position",
        "execution_reference": "next_1m_open",
        "delay_stress_execution_reference": "second_1m_open_after_trigger",
        "stop_bps": 60.0,
        "maximum_hold_minutes": 720,
        "fee_bps_per_side": 4.5,
        "slippage_bps_per_side": 2.0,
        "protective_stop_precedence": True,
        "parameter_grid": False,
        "entry_policy_changed": False,
    }
    contract = _mapping(payload["candidate_contract"], "candidate contract")
    if any(contract.get(name) != value for name, value in expected.items()):
        raise ValueError("ETH opposing-breakout preregistration contract changed")
    if payload.get("execution_authority") != "none":
        raise ValueError("ETH opposing-breakout preregistration has live authority")
    if payload.get("automatic_promotion") is not False:
        raise ValueError("ETH opposing-breakout preregistration can auto-promote")
    windows = _mapping(payload["evaluation_windows"], "evaluation windows")
    if any(windows.get(name) != value for name, value in _windows().items()):
        raise ValueError("ETH opposing-breakout preregistration windows changed")


def _trades_in_final_window(
    trades: tuple[HypeExitTrade, ...],
) -> tuple[HypeExitTrade, ...]:
    start = pd.Timestamp(_FINAL_START)
    end = pd.Timestamp(_FINAL_END)
    return tuple(
        trade for trade in trades if start <= pd.Timestamp(trade.signal_time_utc) < end
    )


def _slice_bars(bars: pd.DataFrame, *, end_utc: str) -> pd.DataFrame:
    if "timestamp" not in bars:
        raise ValueError("ETH opposing-breakout bars are missing timestamp")
    output = bars.loc[
        pd.to_datetime(bars["timestamp"], utc=True) < pd.Timestamp(end_utc)
    ].copy()
    if output.empty:
        raise ValueError("ETH opposing-breakout replay window has no bars")
    return output


def _require_frozen_hash(
    frozen: Mapping[str, object], name: str, observed: object
) -> None:
    expected = _mapping(frozen[name], f"frozen {name}")
    actual = _mapping(observed, f"observed {name}")
    if expected.get("sha256") != actual.get("sha256"):
        raise ValueError(f"ETH opposing-breakout {name} hash changed")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _windows() -> dict[str, str]:
    return {
        "development_end_utc": _DEVELOPMENT_END,
        "opened_final_start_utc": _FINAL_START,
        "opened_final_end_utc": _FINAL_END,
    }


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _generator_identity() -> dict[str, object]:
    root = _project_root()
    return source_dependency_identity(
        root, loaded_project_source_paths(root, Path(__file__))
    )


def _require_unchanged(evidence: Mapping[str, object], paths: tuple[Path, ...]) -> None:
    for path in paths:
        require_unchanged_file(path, _mapping(evidence[str(path)], str(path)))


def _require_files(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"ETH opposing-breakout source is missing: {path}")


def _limitations() -> list[str]:
    return [
        "the hypothesis followed one selected live ETH terminal path",
        "the opened-final block was already viewed in prior ETH research",
        "five-minute opposing breakouts can whipsaw before hourly structure changes",
        "one-minute OHLC cannot reproduce private IOC latency or sub-bar ordering",
        "a historical pass permits only a future report-only observer proposal",
    ]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable artifact and print its bounded disposition."""
    args = build_parser().parse_args(argv)
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    assessment = _mapping(artifact["assessment"], "assessment")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "status": assessment["status"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
