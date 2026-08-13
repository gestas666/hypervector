#!/usr/bin/env python3
"""Replay the deployed v11 plus staged ETH candidate on one fixed-cap account."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
    adapt_breakout_trades,
    adapt_hulk_payloads,
    partition_cohort_outcomes,
    replay_cohort_outcomes,
)
from hypervector.research.eth_pullback_replay import (
    replay_eth_precompression_pullback,
)
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)

_INITIAL_EQUITY_USD = 500.0
_DEVELOPMENT_END = "2026-05-28T00:00:00+00:00"
_HOLDOUT_START = "2026-05-29T00:00:00+00:00"
_HOLDOUT_END = "2026-07-28T00:00:00+00:00"
_HULK_ARTIFACTS = (
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_development.json"),
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_validation.json"),
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_pseudo_holdout.json"),
)
_HYPE_BARS = Path("data/cache/HYPE_1m_365d.parquet")
_HYPE_FUNDING = Path(
    "data/cache/vendor/hyperliquid/HYPE/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_ETH_BARS = Path("data/cache/ETH_1m_365d.parquet")
_ETH_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the local, report-only shared-portfolio command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hulk-artifact",
        type=Path,
        action="append",
        default=list(_HULK_ARTIFACTS),
    )
    parser.add_argument("--hype-bars", type=Path, default=_HYPE_BARS)
    parser.add_argument("--hype-funding", type=Path, default=_HYPE_FUNDING)
    parser.add_argument("--eth-bars", type=Path, default=_ETH_BARS)
    parser.add_argument("--eth-funding", type=Path, default=_ETH_FUNDING)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build_artifact(
    trades: tuple[CohortOutcome, ...],
    *,
    data_evidence: dict[str, object],
    source_summaries: dict[str, object],
) -> dict[str, object]:
    """Build independent development/final reports under one common split."""
    partitions = partition_cohort_outcomes(
        trades,
        development_end_utc=_DEVELOPMENT_END,
        holdout_start_utc=_HOLDOUT_START,
        holdout_end_utc=_HOLDOUT_END,
    )
    development = partitions["development"]
    final = partitions["opened_final_60d"]
    return {
        "schema_version": 1,
        "mode": "current_cohort_shared_portfolio_report_only_v1",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": _contract(),
        "common_split": _common_split(),
        "input_trade_counts": {name: len(rows) for name, rows in partitions.items()},
        "input_trade_counts_by_strategy": _counts_by_strategy(trades),
        "development": replay_cohort_outcomes(
            development, initial_equity_usd=_INITIAL_EQUITY_USD
        ),
        "opened_final_60d": replay_cohort_outcomes(
            final, initial_equity_usd=_INITIAL_EQUITY_USD
        ),
        "combined_available_blocks": replay_cohort_outcomes(
            development + final, initial_equity_usd=_INITIAL_EQUITY_USD
        ),
        "source_summaries": source_summaries,
        "data_evidence": data_evidence,
        "decision": "diagnostic_only_no_automatic_promotion",
        "limitations": _limitations(),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact local sources, reconstruct lifecycles, and build the report."""
    source_paths = tuple(args.hulk_artifact) + (
        args.hype_bars,
        args.hype_funding,
        args.eth_bars,
        args.eth_funding,
    )
    for path in source_paths:
        _require_file(path)
    hulk_payloads = tuple(_load_json(path) for path in args.hulk_artifact)
    hulk = adapt_hulk_payloads(hulk_payloads, _hulk_spec())
    hype_report = _hype_report(args.hype_bars, args.hype_funding)
    eth_report = _eth_report(args.eth_bars, args.eth_funding)
    trades = hulk + adapt_breakout_trades(hype_report.trades, _hype_spec())
    trades += adapt_breakout_trades(eth_report.trades, _eth_spec())
    return build_artifact(
        trades,
        data_evidence=_data_evidence(source_paths),
        source_summaries=_source_summaries(hulk_payloads, hype_report, eth_report),
    )


def _hype_report(bars_path: Path, funding_path: Path) -> HypeExitReplayReport:
    bars = pd.read_parquet(bars_path)
    funding = pd.read_parquet(funding_path)
    market, _evidence = build_hype_exit_market(bars, funding)
    config = HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )
    return replay_hype_breakout_exits(
        market,
        HypeExitPolicy("hype_breakout_onset_bidirectional_v1"),
        config,
    )


def _eth_report(bars_path: Path, funding_path: Path) -> HypeExitReplayReport:
    """Return the exact reusable ETH pullback replay report."""
    bars = pd.read_parquet(bars_path)
    funding = pd.read_parquet(funding_path)
    return replay_eth_precompression_pullback(bars, funding).report


def _hulk_spec() -> CohortTradeSpec:
    return CohortTradeSpec(
        "hulk_expansion_bidirectional_tuned_v2", "BTC", 25.0, 5.0, 4.5
    )


def _hype_spec() -> CohortTradeSpec:
    return CohortTradeSpec(
        "hype_breakout_onset_bidirectional_v1", "HYPE", 75.0, 5.0, 4.5
    )


def _eth_spec() -> CohortTradeSpec:
    return CohortTradeSpec(
        "eth_breakout_precompression_pullback_bidirectional_v1",
        "ETH",
        25.0,
        5.0,
        4.5,
    )


def _contract() -> dict[str, object]:
    return {
        "initial_equity_usd": _INITIAL_EQUITY_USD,
        "margin_mode": "isolated",
        "one_position_per_symbol": True,
        "maximum_positions": 4,
        "fixed_notional_caps": {"BTC": 25.0, "ETH": 25.0, "HYPE": 75.0},
        "leverage": {"BTC": 5.0, "ETH": 5.0, "HYPE": 5.0},
        "entry_fee_bps": 4.5,
        "compounding_above_caps": False,
        "shared_realized_equity": True,
        "same_bar_exit_ordering": (
            "entry_timestamp_plus_1ms_only_when_bar_artifact_times_are_equal"
        ),
    }


def _common_split() -> dict[str, object]:
    return {
        "development_end_exclusive_utc": _DEVELOPMENT_END,
        "purge_minutes": 1_440,
        "holdout_start_utc": _HOLDOUT_START,
        "holdout_end_exclusive_utc": _HOLDOUT_END,
        "holdout_already_opened": True,
    }


def _counts_by_strategy(
    trades: tuple[CohortOutcome, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in trades:
        counts[trade.strategy_id] = counts.get(trade.strategy_id, 0) + 1
    return dict(sorted(counts.items()))


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _source_summaries(
    hulk_payloads: tuple[dict[str, object], ...],
    hype_report: HypeExitReplayReport,
    eth_report: HypeExitReplayReport,
) -> dict[str, object]:
    return {
        "hulk_expansion_bidirectional_tuned_v2": [
            _hulk_source_summary(payload) for payload in hulk_payloads
        ],
        "hype_breakout_onset_bidirectional_v1": _breakout_summary(hype_report),
        "eth_breakout_precompression_pullback_bidirectional_v1": (
            _breakout_summary(eth_report)
        ),
    }


def _hulk_source_summary(payload: dict[str, object]) -> dict[str, object]:
    performance = payload.get("performance")
    if not isinstance(performance, dict):
        raise ValueError("Hulk artifact performance must be an object")
    replay = payload.get("replay")
    if not isinstance(replay, dict) or not isinstance(replay.get("trades"), list):
        raise ValueError("Hulk artifact replay trades must be a list")
    return {
        "segment": payload.get("segment"),
        "start_utc": payload.get("start_utc"),
        "end_utc": payload.get("end_utc"),
        "performance": performance,
        "direction_attribution": payload.get("direction_attribution"),
        "same_bar_btc_lifecycles": _same_bar_btc_count(replay["trades"]),
    }


def _same_bar_btc_count(rows: list[object]) -> int:
    return sum(
        isinstance(row, dict)
        and row.get("symbol") == "BTC"
        and row.get("entry_time_utc") == row.get("exit_time_utc")
        for row in rows
    )


def _breakout_summary(report: HypeExitReplayReport) -> dict[str, object]:
    payload = asdict(report)
    payload.pop("trades")
    return payload


def _limitations() -> list[str]:
    return [
        "the opened final 60-day block was previously inspected and is descriptive",
        "one-minute and 30-minute bars cannot reproduce private queue position",
        "fixed slippage cannot reproduce every live IOC fill or stop gap",
        "realized-equity drawdown omits concurrent intratrade mark-to-market paths",
        "fixed notional caps intentionally prevent historical size compounding",
        "BTC begins later than ETH and HYPE because its exact source window is shorter",
        "portfolio aggregation cannot turn a negative component into proven edge",
    ]


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"cohort source artifact must be an object: {path}")
    return value


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"current cohort source is missing: {path}")


def main() -> None:
    """Publish one immutable, report-only shared-portfolio artifact."""
    args = build_parser().parse_args()
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "development": artifact["development"]["performance"],
                "opened_final_60d": artifact["opened_final_60d"]["performance"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
