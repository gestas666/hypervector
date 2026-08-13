#!/usr/bin/env python3
"""Replay the bounded bidirectional ETH/SOL canary on one shared account."""

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
    adapt_range_event_payloads,
    default_sol_range_artifact_paths,
    partition_cohort_outcomes,
    replay_cohort_outcomes,
)
from hypervector.research.eth_pullback_replay import (
    ETH_PULLBACK_STRATEGY,
    EthPullbackReplay,
    replay_eth_precompression_pullback,
)

ETH_STRATEGY = ETH_PULLBACK_STRATEGY
SOL_STRATEGY = "range_onset_bidirectional_v1"
_INITIAL_EQUITY_USD = 500.0
_DEVELOPMENT_END = "2026-05-28T00:00:00+00:00"
_HOLDOUT_START = "2026-05-29T00:00:00+00:00"
_HOLDOUT_END = "2026-07-28T00:00:00+00:00"
_ETH_BARS = Path("data/cache/ETH_1m_365d.parquet")
_ETH_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_SOL_ARTIFACTS = default_sol_range_artifact_paths()


def build_parser() -> argparse.ArgumentParser:
    """Return the immutable report-only portfolio replay CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eth-bars", type=Path, default=_ETH_BARS)
    parser.add_argument("--eth-funding", type=Path, default=_ETH_FUNDING)
    parser.add_argument(
        "--sol-artifact",
        type=Path,
        action="append",
        default=list(_SOL_ARTIFACTS),
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build_artifact(
    trades: tuple[CohortOutcome, ...],
    *,
    data_evidence: dict[str, object],
    source_summaries: dict[str, object],
) -> dict[str, object]:
    """Build independent common-window reports and full attribution."""
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
        "mode": "eth_sol_shared_canary_falsification_v1",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": _contract(),
        "common_split": _common_split(),
        "input_trade_counts": {name: len(rows) for name, rows in partitions.items()},
        "development": replay_cohort_outcomes(
            development,
            initial_equity_usd=_INITIAL_EQUITY_USD,
        ),
        "opened_final_60d": replay_cohort_outcomes(
            final,
            initial_equity_usd=_INITIAL_EQUITY_USD,
        ),
        "all_available": replay_cohort_outcomes(
            development + final,
            initial_equity_usd=_INITIAL_EQUITY_USD,
        ),
        "source_summaries": source_summaries,
        "data_evidence": data_evidence,
        "decision": "bounded_falsification_no_automatic_promotion",
        "limitations": _limitations(),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact sources and replay the two executable mechanisms."""
    paths = (args.eth_bars, args.eth_funding, *tuple(args.sol_artifact))
    for path in paths:
        _require_file(path)
    eth = replay_eth_precompression_pullback(
        pd.read_parquet(args.eth_bars),
        pd.read_parquet(args.eth_funding),
    )
    sol_payloads = tuple(_load_json(path) for path in args.sol_artifact)
    trades = adapt_breakout_trades(eth.report.trades, _eth_spec())
    trades += adapt_range_event_payloads(sol_payloads, _sol_spec())
    return build_artifact(
        trades,
        data_evidence=_data_evidence(paths),
        source_summaries=_source_summaries(eth, sol_payloads),
    )


def _eth_spec() -> CohortTradeSpec:
    """Return the exact live ETH sizing contract."""
    return CohortTradeSpec(ETH_STRATEGY, "ETH", 25.0, 5.0, 4.5)


def _sol_spec() -> CohortTradeSpec:
    """Return the exact staged SOL sizing contract."""
    return CohortTradeSpec(SOL_STRATEGY, "SOL", 75.0, 5.0, 4.5)


def _contract() -> dict[str, object]:
    """Return the shared-account assumptions mirrored by the live profile."""
    return {
        "initial_equity_usd": _INITIAL_EQUITY_USD,
        "margin_mode": "isolated",
        "one_position_per_symbol": True,
        "maximum_positions": 2,
        "fixed_notional_caps": {"ETH": 25.0, "SOL": 75.0},
        "leverage": {"ETH": 5.0, "SOL": 5.0},
        "entry_fee_bps": 4.5,
        "entry_slippage_bps": 2.0,
        "shared_realized_equity": True,
        "compounding_above_caps": False,
    }


def _common_split() -> dict[str, object]:
    """Return the frozen development, purge, and opened-final boundaries."""
    return {
        "development_end_exclusive_utc": _DEVELOPMENT_END,
        "purge_minutes": 1_440,
        "holdout_start_utc": _HOLDOUT_START,
        "holdout_end_exclusive_utc": _HOLDOUT_END,
        "holdout_already_opened": True,
    }


def _source_summaries(
    eth: EthPullbackReplay,
    sol_payloads: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Return source-level coverage without duplicating lifecycle rows."""
    eth_report = asdict(eth.report)
    eth_report.pop("trades")
    return {
        ETH_STRATEGY: {
            "report": eth_report,
            "market_evidence": asdict(eth.market_evidence),
            "policy_evidence": asdict(eth.policy_evidence),
        },
        SOL_STRATEGY: [_sol_summary(payload) for payload in sol_payloads],
    }


def _sol_summary(payload: dict[str, object]) -> dict[str, object]:
    """Return the exact 15%-exposure SOL trial summary."""
    continuous = payload.get("continuous")
    if not isinstance(continuous, dict):
        raise ValueError("SOL source continuous result must be an object")
    rows = continuous.get("trials")
    if not isinstance(rows, list):
        raise ValueError("SOL source trials must be a list")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("effective_exposure") == 0.15
    ]
    if len(matches) != 1:
        raise ValueError("SOL source must contain one 15%-exposure trial")
    replay = matches[0].get("event_replay")
    if not isinstance(replay, dict):
        raise ValueError("SOL source event replay must be an object")
    return {
        "start_utc": continuous.get("start_utc"),
        "end_utc": continuous.get("end_utc"),
        "completed_trades": replay.get("completed_trades"),
        "wins": replay.get("wins"),
        "losses": replay.get("losses"),
        "profit_factor": replay.get("profit_factor"),
        "funding_cashflow_usd": replay.get("funding_cashflow_usd"),
        "total_fees_usd": replay.get("total_fees_usd"),
    }


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    """Hash every local source used by the replay."""
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _limitations() -> list[str]:
    """Return material empirical limits on the portfolio result."""
    return [
        "the final 60-day block was previously inspected and is descriptive",
        "SOL evidence contains twelve measured blocks rather than continuous coverage",
        "one-minute bars cannot reproduce private queue position or every stop gap",
        "realized-equity drawdown omits concurrent intratrade mark-to-market paths",
        "fixed notional caps intentionally prevent historical size compounding",
        "a positive aggregate cannot establish that both components have durable edge",
    ]


def _load_json(path: Path) -> dict[str, object]:
    """Load one required JSON object with an actionable failure."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"SOL source artifact must be an object: {path}")
    return value


def _require_file(path: Path) -> None:
    """Fail before computation if an evidence source is missing."""
    if not path.is_file():
        raise FileNotFoundError(f"ETH/SOL portfolio source is missing: {path}")


def main() -> None:
    """Publish one immutable shared-portfolio falsification artifact."""
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
