#!/usr/bin/env python3
"""Evaluate one preregistered ETH component-decay exit without live authority."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.eth_component_decay_exit import (
    EthComponentDecayReplay,
    EthComponentDecaySpec,
    replay_eth_component_decay_exit,
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
    "docs/research-journal/v58-eth-r5-component-decay-exit-preregistration-v1.json"
)
_DEVELOPMENT_END = "2026-05-28T12:00:00Z"
_FINAL_START = "2026-05-29T00:00:00Z"
_FINAL_END = "2026-07-28T00:00:00Z"
_FOLD_COUNT = 5


def build_parser() -> argparse.ArgumentParser:
    """Return the source-bound report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--preregistration", type=Path, default=_PREREGISTRATION)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run the exact fixed-entry historical comparison and return its artifact."""
    paths = (args.bars, args.funding, args.preregistration)
    _require_files(paths)
    evidence = _data_evidence(paths)
    preregistration = _load_preregistration(args.preregistration, evidence, args)
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
    final_control = _trades_in_window(final_history.report.trades)
    development_candidate = replay_eth_component_decay_exit(
        development.market, development_control
    )
    final_candidate = replay_eth_component_decay_exit(
        final_history.market, final_control
    )
    artifact = _artifact(
        preregistration,
        evidence,
        generator,
        development_control,
        development_candidate,
        final_control,
        final_candidate,
    )
    _require_unchanged(evidence, paths)
    require_unchanged_dependencies(generator, _project_root())
    return artifact


def _artifact(
    preregistration: Mapping[str, object],
    evidence: Mapping[str, object],
    generator: Mapping[str, object],
    development_control: tuple[HypeExitTrade, ...],
    development_candidate: EthComponentDecayReplay,
    final_control: tuple[HypeExitTrade, ...],
    final_candidate: EthComponentDecayReplay,
) -> dict[str, object]:
    development = _segment(
        development_control, development_candidate, include_folds=True
    )
    final = _segment(final_control, final_candidate, include_folds=False)
    assessment = _assessment(development, final)
    return {
        "schema_version": 1,
        "mode": "eth_component_decay_exit_historical_report_only_v1",
        "hypothesis_id": preregistration["hypothesis_id"],
        "strategy_id": ETH_PULLBACK_STRATEGY,
        "symbol": "ETH",
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "current_open_lifecycle_used_for_economic_selection": False,
        "contract": asdict(EthComponentDecaySpec()),
        "windows": _windows(),
        "segments": {
            "development": development,
            "opened_final_60d": final,
        },
        "assessment": assessment,
        "hypothesis_ledger_status": assessment["status"],
        "preregistration": dict(preregistration),
        "data_evidence": dict(evidence),
        "generator_identity": dict(generator),
        "limitations": _limitations(),
    }


def _segment(
    control: tuple[HypeExitTrade, ...],
    candidate: EthComponentDecayReplay,
    *,
    include_folds: bool,
) -> dict[str, object]:
    candidate_trades = candidate.report.trades
    _require_entry_parity(control, candidate_trades)
    component_exits = sum(
        trade.exit_reason == "structural_reversal" for trade in candidate_trades
    )
    if component_exits > len(candidate.triggers):
        raise ValueError("ETH component exits exceed causal triggers")
    control_summary = _summary(control, component_adapter=False)
    candidate_summary = _summary(candidate_trades, component_adapter=True)
    folds = _folds(control, candidate_trades) if include_folds else []
    return {
        "technical_status": candidate.technical_status,
        "entry_parity": True,
        "triggered_lifecycles": len(candidate.triggers),
        "component_decay_exits": component_exits,
        "unavailable_component_rows": list(candidate.unavailable_component_rows),
        "control": control_summary,
        "candidate": candidate_summary,
        "delta_net_return_bps": (
            candidate_summary["net_return_bps"] - control_summary["net_return_bps"]
        ),
        "chronological_folds": folds,
    }


def _summary(
    trades: tuple[HypeExitTrade, ...],
    *,
    component_adapter: bool,
) -> dict[str, object]:
    returns = [trade.net_return_bps for trade in trades]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    reasons = Counter(trade.exit_reason for trade in trades)
    if component_adapter and "structural_reversal" in reasons:
        reasons["component_decay_next_open"] = reasons.pop("structural_reversal")
    return {
        "trades": len(trades),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "net_return_bps": sum(returns),
        "profit_factor": gains / losses if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(returns),
        "net_excluding_largest_winner_bps": (
            sum(returns) - max((value for value in returns if value > 0.0), default=0.0)
        ),
        "exit_reasons": dict(sorted(reasons.items())),
        "by_side": {
            side: _side_summary(tuple(trade for trade in trades if trade.side == side))
            for side in ("long", "short")
        },
    }


def _side_summary(trades: tuple[HypeExitTrade, ...]) -> dict[str, object]:
    returns = [trade.net_return_bps for trade in trades]
    losses = -sum(value for value in returns if value < 0.0)
    gains = sum(value for value in returns if value > 0.0)
    return {
        "trades": len(trades),
        "net_return_bps": sum(returns),
        "profit_factor": gains / losses if losses else None,
        "net_excluding_largest_winner_bps": (
            sum(returns) - max((value for value in returns if value > 0.0), default=0.0)
        ),
    }


def _folds(
    control: tuple[HypeExitTrade, ...],
    candidate: tuple[HypeExitTrade, ...],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for index in range(_FOLD_COUNT):
        start = index * len(control) // _FOLD_COUNT
        end = (index + 1) * len(control) // _FOLD_COUNT
        control_summary = _summary(control[start:end], component_adapter=False)
        candidate_summary = _summary(candidate[start:end], component_adapter=True)
        output.append(
            {
                "fold": index + 1,
                "control": control_summary,
                "candidate": candidate_summary,
                "delta_net_return_bps": (
                    candidate_summary["net_return_bps"]
                    - control_summary["net_return_bps"]
                ),
            }
        )
    return output


def _assessment(
    development: Mapping[str, object],
    final: Mapping[str, object],
) -> dict[str, object]:
    dev_control = _mapping(development["control"], "development control")
    dev_candidate = _mapping(development["candidate"], "development candidate")
    final_control = _mapping(final["control"], "final control")
    final_candidate = _mapping(final["candidate"], "final candidate")
    folds = development["chronological_folds"]
    if not isinstance(folds, list):
        raise ValueError("development folds must be a list")
    conditions = {
        "technical_paths_resolved": (
            development["technical_status"] == final["technical_status"] == "resolved"
        ),
        "development_net_and_pf_improve": _economics_improve(
            dev_control, dev_candidate
        ),
        "development_ex_largest_positive": (
            float(dev_candidate["net_excluding_largest_winner_bps"]) > 0.0
        ),
        "development_drawdown_not_worse": _drawdown_not_worse(
            dev_control, dev_candidate
        ),
        "development_fold_breadth": _fold_breadth(folds) >= 3,
        "opened_final_net_and_pf_improve": _economics_improve(
            final_control, final_candidate
        ),
        "opened_final_ex_largest_positive": (
            float(final_candidate["net_excluding_largest_winner_bps"]) > 0.0
        ),
        "opened_final_drawdown_not_worse": _drawdown_not_worse(
            final_control, final_candidate
        ),
        "opened_final_both_sides_positive": _both_sides_positive(final_candidate),
    }
    failed = [name for name, passed in conditions.items() if not passed]
    return {
        "status": (
            "eligible_for_future_report_only_observer"
            if not failed
            else "rejected_historical_candidate"
        ),
        "conditions": conditions,
        "failed_conditions": failed,
        "proposed_live_change": "none",
        "explicit_approval_requested": False,
        "confidence": "low_retrospective_fixed_hypothesis",
    }


def _economics_improve(
    control: Mapping[str, object], candidate: Mapping[str, object]
) -> bool:
    return float(candidate["net_return_bps"]) > float(control["net_return_bps"]) and (
        _profit_factor(candidate) > _profit_factor(control)
    )


def _profit_factor(summary: Mapping[str, object]) -> float:
    value = summary["profit_factor"]
    return (
        float("inf")
        if value is None and float(summary["net_return_bps"]) > 0
        else float(value or 0.0)
    )


def _drawdown_not_worse(
    control: Mapping[str, object], candidate: Mapping[str, object]
) -> bool:
    return float(candidate["maximum_drawdown_bps"]) <= float(
        control["maximum_drawdown_bps"]
    )


def _both_sides_positive(candidate: Mapping[str, object]) -> bool:
    sides = _mapping(candidate["by_side"], "candidate side summaries")
    return all(
        float(_mapping(sides[side], side)["net_return_bps"]) > 0.0
        for side in ("long", "short")
    )


def _fold_breadth(folds: list[object]) -> int:
    return sum(
        float(
            _mapping(_mapping(row, "fold")["candidate"], "fold candidate")[
                "net_return_bps"
            ]
        )
        > 0.0
        and float(_mapping(row, "fold")["delta_net_return_bps"]) > 0.0
        for row in folds
    )


def _maximum_drawdown(returns: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _require_entry_parity(
    control: tuple[HypeExitTrade, ...], candidate: tuple[HypeExitTrade, ...]
) -> None:
    if [_entry_identity(trade) for trade in control] != [
        _entry_identity(trade) for trade in candidate
    ]:
        raise ValueError("ETH component-decay artifact entry cohort changed")


def _entry_identity(trade: HypeExitTrade) -> tuple[str, str, str]:
    return trade.signal_time_utc, trade.entry_time_utc, trade.side


def _trades_in_window(
    trades: tuple[HypeExitTrade, ...],
) -> tuple[HypeExitTrade, ...]:
    start = pd.Timestamp(_FINAL_START)
    end = pd.Timestamp(_FINAL_END)
    return tuple(
        trade for trade in trades if start <= pd.Timestamp(trade.signal_time_utc) < end
    )


def _slice_bars(bars: pd.DataFrame, *, end_utc: str) -> pd.DataFrame:
    if "timestamp" not in bars:
        raise ValueError("ETH component-decay bars are missing timestamp")
    output = bars.loc[
        pd.to_datetime(bars["timestamp"], utc=True) < pd.Timestamp(end_utc)
    ].copy()
    if output.empty:
        raise ValueError("ETH component-decay replay window has no bars")
    return output


def _load_preregistration(
    path: Path,
    evidence: Mapping[str, object],
    args: argparse.Namespace,
) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ETH component-decay preregistration must be an object")
    _require_preregistered_contract(payload)
    frozen = _mapping(payload["frozen_inputs"], "frozen inputs")
    _require_frozen_hash(frozen, "bars", evidence[str(args.bars)])
    _require_frozen_hash(frozen, "funding", evidence[str(args.funding)])
    return payload


def _require_preregistered_contract(payload: Mapping[str, object]) -> None:
    expected = {
        "activation_mfe_bps": 300.0,
        "component_alignment_threshold": -0.5,
        "persistence_completed_1m_bars": 5,
        "stop_bps": 60.0,
        "maximum_hold_minutes": 720,
        "fee_bps_per_side": 4.5,
        "slippage_bps_per_side": 2.0,
        "parameter_grid": False,
    }
    contract = _mapping(payload["candidate_contract"], "candidate contract")
    windows = _mapping(payload["evaluation_windows"], "evaluation windows")
    if any(contract.get(name) != value for name, value in expected.items()):
        raise ValueError("ETH component-decay preregistration contract changed")
    if (
        payload.get("execution_authority") != "none"
        or payload.get("automatic_promotion") is not False
    ):
        raise ValueError("ETH component-decay preregistration is not report-only")
    if any(windows.get(name) != value for name, value in _windows().items()):
        raise ValueError("ETH component-decay preregistration windows changed")


def _require_frozen_hash(
    frozen: Mapping[str, object], name: str, observed: object
) -> None:
    expected = _mapping(frozen[name], f"frozen {name}")
    actual = _mapping(observed, f"observed {name}")
    if expected.get("sha256") != actual.get("sha256"):
        raise ValueError(f"ETH component-decay {name} hash changed")


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
            raise FileNotFoundError(f"ETH component-decay source is missing: {path}")


def _limitations() -> list[str]:
    return [
        "the hypothesis was formed after observing one open ETH giveback",
        "the opened-final block was not prospectively unseen for all prior ETH research",
        "component direction had inverse later-window IC in prior attribution",
        "one-minute OHLC cannot prove sub-bar component or fill ordering",
        "a historical pass can only define a future report-only observer",
    ]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable artifact and print a bounded disposition."""
    args = build_parser().parse_args(argv)
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "status": artifact["assessment"]["status"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
