#!/usr/bin/env python3
"""Publish exact ETH pullback side and breakout-relation attribution."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.eth_pullback_mechanism_attribution import (
    build_eth_pullback_mechanism_attribution,
)
from hypervector.research.eth_pullback_replay import (
    ETH_PULLBACK_STRATEGY,
    EthPullbackReplay,
    replay_eth_precompression_pullback,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    HypeExitTrade,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits
from hypervector.research.hype_breakout_profit_research import (
    declared_hype_profit_policies,
    freeze_hype_entry_cohort,
)
from hypervector.research.hip3_development_provenance import (
    loaded_project_source_paths,
    require_unchanged_dependencies,
    require_unchanged_file,
    source_dependency_identity,
)

_BARS = Path("data/cache/ETH_1m_365d.parquet")
_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_DEVELOPMENT_END = "2026-05-28T12:00:00Z"
_FINAL_START = "2026-05-29T00:00:00Z"
_FINAL_END = "2026-07-28T00:00:00Z"
_DURATION_MINUTES = (240, 480, 720)
_STOP_WIDTHS_BPS = (60.0, 80.0, 100.0, 120.0, 150.0, 180.0)
_CONTROL_STOP_BPS = 60.0


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=Path, default=_BARS)
    parser.add_argument("--funding", type=Path, default=_FUNDING)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load the exact ETH replay and build causal mechanism attribution."""
    _require_file(args.bars)
    _require_file(args.funding)
    data_evidence = _data_evidence((args.bars, args.funding))
    generator_identity = _generator_identity()
    bars = pd.read_parquet(args.bars)
    funding = pd.read_parquet(args.funding)
    development = replay_eth_precompression_pullback(
        _slice_bars(bars, end_utc=_DEVELOPMENT_END),
        funding,
    )
    final_history = replay_eth_precompression_pullback(
        _slice_bars(bars, end_utc=_FINAL_END),
        funding,
    )
    final_trades = _trades_in_window(
        final_history.report.trades,
        start_utc=_FINAL_START,
        end_utc=_FINAL_END,
    )
    development_trades = development.report.trades
    artifact = _build_artifact(
        args,
        development,
        development_trades,
        final_history,
        final_trades,
        data_evidence=data_evidence,
        generator_identity=generator_identity,
    )
    _require_unchanged_inputs(data_evidence, (args.bars, args.funding))
    require_unchanged_dependencies(generator_identity, _project_root())
    return artifact


def _build_artifact(
    args: argparse.Namespace,
    development: EthPullbackReplay,
    development_trades: tuple[HypeExitTrade, ...],
    final_history: EthPullbackReplay,
    final_trades: tuple[HypeExitTrade, ...],
    *,
    data_evidence: dict[str, object],
    generator_identity: dict[str, object],
) -> dict[str, object]:
    signal_market = pd.concat(
        (
            _market_for_trades(development, development_trades),
            _market_for_trades(final_history, final_trades),
        )
    )
    artifact = build_eth_pullback_mechanism_attribution(
        signal_market,
        development_trades + final_trades,
        development_end_utc=_DEVELOPMENT_END,
        opened_final_start_utc=_FINAL_START,
        opened_final_end_utc=_FINAL_END,
    )
    artifact.update(
        {
            "strategy_id": ETH_PULLBACK_STRATEGY,
            "symbol": "ETH",
            "source_replay": _source_replay_evidence(
                development, development_trades, final_history, final_trades
            ),
            **_comparison_evidence(
                development, development_trades, final_history, final_trades
            ),
            "data_evidence": data_evidence,
            "generator_identity": generator_identity,
            "decision": "descriptive_mechanism_attribution_no_selection",
        }
    )
    return artifact


def _comparison_evidence(
    development: EthPullbackReplay,
    development_trades: tuple[HypeExitTrade, ...],
    final_history: EthPullbackReplay,
    final_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    comparisons = {
        "profit_lock_comparison": _profit_lock_comparison,
        "risk_normalized_profit_lock_comparison": (
            _risk_normalized_profit_lock_comparison
        ),
        "duration_comparison": _duration_comparison,
        "stop_width_comparison": _stop_width_comparison,
    }
    return {
        name: _segment_comparison(
            comparison,
            development,
            development_trades,
            final_history,
            final_trades,
        )
        for name, comparison in comparisons.items()
    }


def _source_replay_evidence(
    development: EthPullbackReplay,
    development_trades: tuple[HypeExitTrade, ...],
    final_history: EthPullbackReplay,
    final_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    return {
        "development": _replay_evidence(
            development,
            selected_trades=len(development_trades),
            source_scope="development_boundary_replay",
        ),
        "opened_final_60d": _replay_evidence(
            final_history,
            selected_trades=len(final_trades),
            source_scope="full_history_causal_warmup_then_boundary_selection",
        ),
    }


def _segment_comparison(
    comparison: Callable[[pd.DataFrame, tuple[HypeExitTrade, ...]], dict[str, object]],
    development: EthPullbackReplay,
    development_trades: tuple[HypeExitTrade, ...],
    final_history: EthPullbackReplay,
    final_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    return {
        "development": comparison(development.market, development_trades),
        "opened_final_60d": comparison(final_history.market, final_trades),
    }


def _profit_lock_comparison(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    config = HypeExitReplayConfig(
        stop_bps=60.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    return {
        policy.policy_id: _exit_summary(
            replay_hype_breakout_exits(fixed_market, policy, config)
        )
        for policy in declared_hype_profit_policies()
    }


def _duration_comparison(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    reports = {
        f"fixed_{minutes}m": replay_hype_breakout_exits(
            fixed_market,
            HypeExitPolicy(f"fixed_{minutes}m"),
            HypeExitReplayConfig(
                stop_bps=60.0,
                maximum_hold_minutes=minutes,
                fee_bps_per_side=4.5,
                slippage_bps_per_side=2.0,
            ),
        )
        for minutes in _DURATION_MINUTES
    }
    return {
        policy_id: _duration_summary(report) for policy_id, report in reports.items()
    }


def _risk_normalized_profit_lock_comparison(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    config = HypeExitReplayConfig(
        stop_bps=60.0,
        maximum_hold_minutes=720,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )
    policies = (
        HypeExitPolicy("native_12h_control"),
        HypeExitPolicy(
            "r2_floor1_trail1",
            profit_activation_bps=120.0,
            profit_floor_bps=60.0,
            trailing_giveback_bps=60.0,
        ),
        HypeExitPolicy(
            "r5_floor2_trail2",
            profit_activation_bps=300.0,
            profit_floor_bps=120.0,
            trailing_giveback_bps=120.0,
        ),
    )
    return {
        policy.policy_id: _duration_summary(
            replay_hype_breakout_exits(fixed_market, policy, config)
        )
        for policy in policies
    }


def _stop_width_comparison(
    market: pd.DataFrame,
    control_trades: tuple[HypeExitTrade, ...],
) -> dict[str, object]:
    """Replay fixed control intents while holding dollar barrier risk equal."""
    fixed_market = freeze_hype_entry_cohort(market, control_trades)
    policy = HypeExitPolicy("eth_fixed_entry_stop_width_sensitivity")
    output: dict[str, object] = {}
    for width in _STOP_WIDTHS_BPS:
        config = HypeExitReplayConfig(
            stop_bps=width,
            maximum_hold_minutes=720,
            fee_bps_per_side=4.5,
            slippage_bps_per_side=2.0,
        )
        report = replay_hype_breakout_exits(fixed_market, policy, config)
        output[f"{width:g}bps"] = _equal_risk_stop_summary(report, width)
    return output


def _equal_risk_stop_summary(
    report: HypeExitReplayReport, width: float
) -> dict[str, object]:
    """Scale unit-notional replay economics to the control barrier risk."""
    scale = _CONTROL_STOP_BPS / width
    summary = _duration_summary(report)
    net_ex_largest = float(summary["net_excluding_largest_winner_bps"])
    return {
        **summary,
        "stop_width_bps": width,
        "notional_scale_vs_control": scale,
        "equal_risk_net_return_bps": report.net_return_bps * scale,
        "equal_risk_net_excluding_largest_winner_bps": net_ex_largest * scale,
        "equal_risk_maximum_drawdown_bps": report.maximum_drawdown_bps * scale,
    }


def _duration_summary(report: HypeExitReplayReport) -> dict[str, object]:
    trades = report.trades
    return {
        **_exit_summary(report),
        "net_excluding_largest_winner_bps": _net_excluding_largest_winner(trades),
        "monthly_net_bps": dict(report.monthly_net_bps),
        "by_side": {
            side: _trade_summary(tuple(trade for trade in trades if trade.side == side))
            for side in ("long", "short")
        },
    }


def _trade_summary(trades: tuple[HypeExitTrade, ...]) -> dict[str, object]:
    returns = [trade.net_return_bps for trade in trades]
    gains = sum(value for value in returns if value > 0.0)
    losses = -sum(value for value in returns if value < 0.0)
    return {
        "trades": len(trades),
        "wins": sum(value > 0.0 for value in returns),
        "losses": sum(value < 0.0 for value in returns),
        "net_return_bps": sum(returns),
        "profit_factor": gains / losses if losses else None,
        "net_excluding_largest_winner_bps": _net_excluding_largest_winner(trades),
    }


def _net_excluding_largest_winner(trades: tuple[HypeExitTrade, ...]) -> float:
    returns = [trade.net_return_bps for trade in trades]
    return sum(returns) - max((value for value in returns if value > 0.0), default=0.0)


def _exit_summary(report: HypeExitReplayReport) -> dict[str, object]:
    return {
        "trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "exit_reasons": report.exit_reasons,
    }


def _trades_in_window(
    trades: tuple[HypeExitTrade, ...],
    *,
    start_utc: str,
    end_utc: str,
) -> tuple[HypeExitTrade, ...]:
    start = pd.Timestamp(start_utc)
    end = pd.Timestamp(end_utc)
    return tuple(
        trade for trade in trades if start <= pd.Timestamp(trade.signal_time_utc) < end
    )


def _market_for_trades(
    replay: EthPullbackReplay,
    trades: tuple[HypeExitTrade, ...],
) -> pd.DataFrame:
    timestamps = pd.DatetimeIndex(
        [pd.Timestamp(trade.signal_time_utc) for trade in trades]
    )
    missing = timestamps.difference(replay.market.index)
    if not missing.empty:
        raise ValueError("ETH attribution signal is missing replay market evidence")
    return replay.market.loc[timestamps].copy()


def _slice_bars(
    bars: pd.DataFrame,
    *,
    start_utc: str | None = None,
    end_utc: str,
) -> pd.DataFrame:
    if "timestamp" not in bars:
        raise ValueError("ETH attribution bars are missing timestamp")
    timestamps = pd.to_datetime(bars["timestamp"], utc=True)
    selected = timestamps.lt(pd.Timestamp(end_utc))
    if start_utc is not None:
        selected &= timestamps.ge(pd.Timestamp(start_utc))
    output = bars.loc[selected].copy()
    if output.empty:
        raise ValueError("ETH attribution replay window has no bars")
    return output


def _replay_evidence(
    replay: EthPullbackReplay,
    *,
    selected_trades: int,
    source_scope: str,
) -> dict[str, object]:
    return {
        "market_evidence": asdict(replay.market_evidence),
        "policy_evidence": asdict(replay.policy_evidence),
        "selection": {
            "source_scope": source_scope,
            "selected_trades": selected_trades,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Write one immutable attribution artifact and print a bounded summary."""
    args = build_parser().parse_args(argv)
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    segments = artifact["segments"]
    if not isinstance(segments, dict):
        raise RuntimeError("ETH attribution segments are unavailable")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "development": segments["development"]["all"],
                "opened_final_60d": segments["opened_final_60d"]["all"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )
    return 0


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _generator_identity() -> dict[str, object]:
    root = _project_root()
    paths = loaded_project_source_paths(root, Path(__file__))
    return source_dependency_identity(root, paths)


def _require_unchanged_inputs(
    evidence: dict[str, object],
    paths: tuple[Path, ...],
) -> None:
    for path in paths:
        expected = evidence.get(str(path))
        if not isinstance(expected, dict):
            raise ValueError(f"ETH attribution evidence is missing: {path}")
        require_unchanged_file(path, expected)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"ETH attribution source is missing: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
