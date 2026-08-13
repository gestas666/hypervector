#!/usr/bin/env python3
"""Replay source-follow signals through continuous production execution state."""

from __future__ import annotations

import argparse
from datetime import timedelta
import math
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.research_database_replay import (
    ResearchReplayConfig,
    database_replay_coverage,
)
from hypervector.research.source_follow_portfolio_artifact import (
    load_source_portfolio_selection,
)
from hypervector.research.source_follow_portfolio_io import (
    SourcePortfolioArchive,
    SourcePortfolioArchiveConfig,
)
from hypervector.research.source_follow_portfolio_replay import (
    SourcePortfolioReplayConfig,
)
from hypervector.research.source_follow_sparse_replay import (
    replay_sparse_source_portfolio,
)


def _positive_hours(value: str) -> float:
    hours = float(value)
    if not math.isfinite(hours) or hours <= 0.0:
        raise argparse.ArgumentTypeError("chunk hours must be finite and positive")
    return hours


def _leverage(value: str) -> float:
    leverage = float(value)
    if not math.isfinite(leverage) or not 0.0 < leverage <= 40.0:
        raise argparse.ArgumentTypeError("leverage must be within (0, 40]")
    return leverage


def _margin_fraction(value: str) -> float:
    fraction = float(value)
    if not math.isfinite(fraction) or not 0.0 < fraction <= 1.0:
        raise argparse.ArgumentTypeError("margin fraction must be within (0, 1]")
    return fraction


def _nonnegative_bps(value: str) -> float:
    bps = float(value)
    if not math.isfinite(bps) or bps < 0.0:
        raise argparse.ArgumentTypeError("basis-point threshold must be non-negative")
    return bps


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse explicit report-only replay inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--prices", type=Path, required=True)
    parser.add_argument("--funding", type=Path, required=True)
    parser.add_argument("--candidate", default="alloc50_lev30")
    parser.add_argument("--chunk-hours", type=_positive_hours, default=1.0)
    parser.add_argument("--leverage", type=_leverage, default=30.0)
    parser.add_argument("--margin-fraction", type=_margin_fraction, default=0.50)
    parser.add_argument(
        "--minimum-signal-range-bps",
        type=_nonnegative_bps,
        default=None,
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def replay_config(args: argparse.Namespace) -> SourcePortfolioReplayConfig:
    """Build one risk challenger while preserving the 8% margin target."""
    return SourcePortfolioReplayConfig(
        margin_fraction=args.margin_fraction,
        leverage=args.leverage,
        target_price_fraction=8.0 / args.leverage / 100.0,
    )


def main(argv: list[str] | None = None) -> int:
    """Run one immutable queue-aware portfolio replay artifact."""
    args = parse_args(argv)
    selection = load_source_portfolio_selection(
        args.artifact,
        args.candidate,
        minimum_signal_range_bps=args.minimum_signal_range_bps,
    )
    chunk = timedelta(hours=args.chunk_hours)
    archive = SourcePortfolioArchiveConfig(
        args.database,
        args.prices,
        args.funding,
        "BTC",
        selection.start,
        selection.end,
        chunk,
    )
    config = replay_config(args)
    with SourcePortfolioArchive(archive) as source:
        result = replay_sparse_source_portfolio(
            source,
            selection.start,
            selection.end,
            selection.signals,
            config,
        )
    report = result.report
    coverage = database_replay_coverage(
        ResearchReplayConfig(
            args.database,
            "BTC",
            selection.start,
            selection.end,
            chunk,
        ),
        include_trades=True,
    )
    baseline = baseline_summary(selection.baseline_replay)
    payload = _payload(
        args,
        len(selection.signals),
        selection.source_signal_count,
        config,
        report.to_dict(),
        coverage,
    )
    payload["sparse_execution_evidence"] = {
        "queried_intervals": result.queried_intervals,
        "queried_seconds": result.queried_seconds,
        "verified_window_seconds": result.window_seconds,
        "skipped_only_while_execution_idle": True,
    }
    comparable = _baseline_is_comparable(args)
    payload["optimistic_trade_through_baseline"] = baseline if comparable else None
    payload["comparison"] = (
        _comparison(baseline, report.to_dict()) if comparable else None
    )
    write_immutable_json(args.out, payload)
    print(f"wrote {args.out}")
    return 0


def baseline_summary(replay: dict[str, object]) -> dict[str, object]:
    """Reconstruct comparable baseline economics from completed trade rows."""
    trades = replay.get("trades")
    if not isinstance(trades, list):
        raise ValueError("baseline replay trades must be a list")
    pnls = [_trade_pnl(value) for value in trades]
    gains = sum(max(value, 0.0) for value in pnls)
    losses = -sum(min(value, 0.0) for value in pnls)
    return {
        "completed_trades": _integer(replay, "completed_trades"),
        "liquidations": _integer(replay, "liquidations"),
        "final_equity": _number(replay, "final_equity"),
        "net_pnl": sum(pnls),
        "profit_factor": gains / losses if losses > 0.0 else None,
        "maximum_drawdown_pct": _number(replay, "maximum_drawdown_pct"),
    }


def _payload(
    args: argparse.Namespace,
    selected_signal_count: int,
    source_signal_count: int,
    config: SourcePortfolioReplayConfig,
    report: dict[str, object],
    coverage: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "hypervelocity_source_production_portfolio_replay_v1",
        "report_only": True,
        "runtime_strategy_changed": False,
        "execution_authority": "none",
        "candidate": args.candidate,
        "source_signal_count": source_signal_count,
        "signal_count": selected_signal_count,
        "research_challenger": {
            "minimum_signal_range_bps": args.minimum_signal_range_bps,
            "margin_fraction": config.margin_fraction,
            "leverage": config.leverage,
            "gross_margin_target_pct": 8.0,
        },
        "source_artifact": file_evidence(args.artifact),
        "price_context": file_evidence(args.prices),
        "funding_context": file_evidence(args.funding),
        "archive_coverage": coverage,
        "production_contract": {
            "displayed_queue_ahead": True,
            "partial_fills": True,
            "submit_latency_ms": config.submit_latency_ms,
            "cancel_latency_ms": config.cancel_latency_ms,
            "margin_fraction": config.margin_fraction,
            "leverage": config.leverage,
            "target_margin_pct": 8.0,
            "maximum_hold_seconds": config.maximum_hold_seconds,
            "isolated_liquidation": True,
            "funding": True,
        },
        "production_replay": report,
        "limitations": [
            "Displayed public depth cannot reveal private cancellations.",
            "Archive exchange timestamps stand in for unavailable receipt time.",
            "Each gap-free artifact starts a separate $15,000 portfolio.",
            "A non-null minimum signal range is a development-only challenger.",
        ],
    }


def _baseline_is_comparable(args: argparse.Namespace) -> bool:
    return (
        args.leverage == 30.0
        and args.margin_fraction == 0.50
        and args.minimum_signal_range_bps is None
    )


def _comparison(
    baseline: dict[str, object],
    production: dict[str, object],
) -> dict[str, object]:
    keys = ("completed_trades", "liquidations", "final_equity")
    return {
        f"{key}_difference": _number(production, key) - _number(baseline, key)
        for key in keys
    }


def _trade_pnl(value: object) -> float:
    if not isinstance(value, dict):
        raise ValueError("baseline trade must be an object")
    return _number(cast(dict[str, object], value), "net_pnl")


def _number(row: dict[str, object], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{key} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def _integer(row: dict[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
