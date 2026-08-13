#!/usr/bin/env python3
"""Compare predeclared long/short mechanisms on one report-only account."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.cohort_separate_side_portfolio import (
    SidePortfolioVariant,
    build_side_portfolio_experiment,
)
from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
    adapt_breakout_trades,
    adapt_range_event_payloads,
    default_sol_range_artifact_paths,
)
from hypervector.research.eth_pullback_replay import (
    replay_eth_precompression_pullback,
)
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)

HYPE_STRATEGY = "hype_breakout_onset_bidirectional_v1"
ETH_STRATEGY = "eth_breakout_precompression_pullback_bidirectional_v1"
SOL_STRATEGY = "range_onset_bidirectional_v1"
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
_SOL_ARTIFACTS = default_sol_range_artifact_paths()
_INITIAL_EQUITY_USD = 500.0
_DEVELOPMENT_END = "2026-05-28T00:00:00+00:00"
_FINAL_START = "2026-05-29T00:00:00+00:00"
_FINAL_END = "2026-07-28T00:00:00+00:00"
_SUMMARY_METRICS = (
    "completed_trades",
    "wins",
    "losses",
    "net_pnl_usd",
    "return_pct",
    "profit_factor",
    "maximum_drawdown_pct",
    "concentration",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable local separate-side experiment command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hype-bars", type=Path, default=_HYPE_BARS)
    parser.add_argument("--hype-funding", type=Path, default=_HYPE_FUNDING)
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


def portfolio_variants() -> tuple[SidePortfolioVariant, ...]:
    """Return the frozen asymmetric hypothesis and explicit comparators."""
    core = (
        (HYPE_STRATEGY, "HYPE", "long"),
        (ETH_STRATEGY, "ETH", "long"),
        (SOL_STRATEGY, "SOL", "short"),
    )
    symmetric = tuple(
        (strategy, symbol, side)
        for strategy, symbol in (
            (HYPE_STRATEGY, "HYPE"),
            (ETH_STRATEGY, "ETH"),
            (SOL_STRATEGY, "SOL"),
        )
        for side in ("long", "short")
    )
    priority = (HYPE_STRATEGY, SOL_STRATEGY, ETH_STRATEGY)
    return (
        SidePortfolioVariant("separate_long_short_core", core, priority, 3),
        SidePortfolioVariant(
            "sol_symmetric_sensitivity",
            core + ((SOL_STRATEGY, "SOL", "long"),),
            priority,
            3,
        ),
        SidePortfolioVariant("source_symmetric_baseline", symmetric, priority, 3),
    )


def trade_specs() -> dict[str, CohortTradeSpec]:
    """Return the current fixed-cap and friction identity for each source."""
    return {
        "HYPE": CohortTradeSpec(HYPE_STRATEGY, "HYPE", 75.0, 5.0, 4.5),
        "ETH": CohortTradeSpec(ETH_STRATEGY, "ETH", 25.0, 5.0, 4.5),
        "SOL": CohortTradeSpec(SOL_STRATEGY, "SOL", 75.0, 5.0, 4.5),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact local sources and compare the frozen side variants."""
    paths = _source_paths(args)
    _require_files(paths)
    outcomes = _source_outcomes(args, trade_specs())
    return build_side_portfolio_experiment(
        outcomes,
        variants=portfolio_variants(),
        initial_equity_usd=_INITIAL_EQUITY_USD,
        development_end_utc=_DEVELOPMENT_END,
        final_start_utc=_FINAL_START,
        final_end_utc=_FINAL_END,
        evidence=_evidence(paths),
    )


def _source_outcomes(
    args: argparse.Namespace,
    specs: dict[str, CohortTradeSpec],
) -> tuple[CohortOutcome, ...]:
    hype_bars = pd.read_parquet(args.hype_bars)
    hype_funding = pd.read_parquet(args.hype_funding)
    hype_market, _market_evidence = build_hype_exit_market(hype_bars, hype_funding)
    hype = replay_hype_breakout_exits(
        hype_market,
        HypeExitPolicy(HYPE_STRATEGY),
        HypeExitReplayConfig(
            stop_bps=80.0,
            maximum_hold_minutes=480,
            maximum_hold_policy="extend_while_regime_supported",
            hard_maximum_hold_minutes=1_440,
            fee_bps_per_side=4.5,
            slippage_bps_per_side=2.0,
        ),
    )
    eth = replay_eth_precompression_pullback(
        pd.read_parquet(args.eth_bars),
        pd.read_parquet(args.eth_funding),
    )
    sol_payloads = tuple(_load_json(path) for path in args.sol_artifact)
    return (
        adapt_breakout_trades(hype.trades, specs["HYPE"])
        + adapt_breakout_trades(eth.report.trades, specs["ETH"])
        + adapt_range_event_payloads(sol_payloads, specs["SOL"])
    )


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.hype_bars,
        args.hype_funding,
        args.eth_bars,
        args.eth_funding,
        *tuple(args.sol_artifact),
    )


def _require_files(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"separate-side source is missing: {path}")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"separate-side JSON source must be an object: {path}")
    return value


def _evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def command_summary(artifact: dict[str, object]) -> dict[str, object]:
    """Return decision metrics while excluding trade-level console payloads."""
    variants = artifact.get("variants")
    if not isinstance(variants, dict):
        raise RuntimeError("separate-side variants are malformed")
    return {
        str(variant_id): {
            block: _block_summary(variant_id, block, variant)
            for block in ("development", "opened_final_block")
        }
        for variant_id, variant in variants.items()
        if isinstance(variant, dict)
    }


def _block_summary(
    variant_id: object,
    block: str,
    variant: dict[object, object],
) -> dict[str, object]:
    value = variant.get(block)
    if not isinstance(value, dict):
        raise RuntimeError(f"variant {variant_id!s} has malformed {block} metrics")
    missing = tuple(metric for metric in _SUMMARY_METRICS if metric not in value)
    if missing:
        raise RuntimeError(
            f"variant {variant_id!s} {block} is missing metrics: {', '.join(missing)}"
        )
    return {metric: value[metric] for metric in _SUMMARY_METRICS}


def main() -> None:
    """Publish one immutable report-only side-composition experiment."""
    args = build_parser().parse_args()
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "variants": command_summary(artifact),
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
