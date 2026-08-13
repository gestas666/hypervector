#!/usr/bin/env python3
"""Compare two static SOL provider orders without execution authority."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
    adapt_breakout_trades,
    adapt_hulk_payloads,
    adapt_range_event_payloads,
    default_sol_range_artifact_paths,
)
from hypervector.research.hype_breakout_exit_market import build_hype_exit_market
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits
from hypervector.research.sol_route_priority_interaction import (
    BREAKOUT_STRATEGY,
    CURRENT_STATIC_PRIORITY,
    HULK_STRATEGY,
    RANGE_STRATEGY,
    build_sol_route_priority_interaction,
)

_PROFILE_ID = "multi_asset_bidirectional_complete_portfolio_canary_v25"
_CONFIG = Path("configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml")
_HULK_ARTIFACTS = (
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_development.json"),
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_validation.json"),
    Path("data/logs/research/20260801_hulk_bidirectional_tuned_v2_pseudo_holdout.json"),
)
_SOL_BARS = Path("data/cache/SOL_1m_365d.parquet")
_SOL_FUNDING = Path(
    "data/cache/vendor/hyperliquid/SOL/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_DEVELOPMENT_END_MS = 1_779_926_400_000
_OPENED_FINAL_START_MS = 1_780_012_800_000
_OPENED_FINAL_END_MS = 1_785_196_800_000
_INITIAL_EQUITY_USD = 500.0
_ENTRY_FEE_BPS = 4.5


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument(
        "--hulk-artifact",
        type=Path,
        action="append",
        default=list(_HULK_ARTIFACTS),
    )
    parser.add_argument("--sol-bars", type=Path, default=_SOL_BARS)
    parser.add_argument("--sol-funding", type=Path, default=_SOL_FUNDING)
    parser.add_argument(
        "--range-artifact",
        type=Path,
        action="append",
        default=list(default_sol_range_artifact_paths()),
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def load_profile_contract(path: Path) -> dict[str, object]:
    """Bind the exact v25 SOL sizing and static fallback priority."""
    config = load_multi_asset_live_config(path, mode="observe")
    if config.profile_id != _PROFILE_ID:
        raise ValueError("SOL priority replay requires the exact v25 profile")
    assets = {asset.symbol: asset for asset in config.assets}
    if "SOL" not in assets:
        raise ValueError("v25 profile has no SOL asset contract")
    relevant = tuple(
        provider
        for provider in config.providers
        if provider.strategy_id in set(CURRENT_STATIC_PRIORITY)
    )
    _validate_provider_contract(relevant)
    asset = assets["SOL"]
    priority = tuple(
        row.strategy_id for row in sorted(relevant, key=lambda row: -row.priority)
    )
    if priority != CURRENT_STATIC_PRIORITY:
        raise ValueError("v25 SOL static fallback priority has changed")
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "notional_usd": asset.max_notional_usd,
        "leverage": asset.leverage,
        "entry_fee_bps": _ENTRY_FEE_BPS,
        "static_priority": list(priority),
        "provider_priority": {row.strategy_id: row.priority for row in relevant},
    }


def build_artifact(
    outcomes: tuple[CohortOutcome, ...],
    *,
    profile_contract: Mapping[str, object],
    data_evidence: Mapping[str, object],
    source_summaries: Mapping[str, object],
    development_end_ms: int = _DEVELOPMENT_END_MS,
    opened_final_start_ms: int = _OPENED_FINAL_START_MS,
    opened_final_end_ms: int = _OPENED_FINAL_END_MS,
) -> dict[str, object]:
    """Attach source identity to the pure two-arm interaction report."""
    artifact = build_sol_route_priority_interaction(
        outcomes,
        development_end_ms=development_end_ms,
        opened_final_start_ms=opened_final_start_ms,
        opened_final_end_ms=opened_final_end_ms,
        source_evidence=data_evidence,
        initial_equity_usd=_INITIAL_EQUITY_USD,
    )
    artifact["profile_contract"] = dict(profile_contract)
    artifact["source_summaries"] = dict(source_summaries)
    return artifact


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact local lifecycles and build one report-only artifact."""
    if args.out.exists():
        raise FileExistsError(f"immutable SOL priority output exists: {args.out}")
    paths = _source_paths(args)
    _require_files(paths)
    contract = load_profile_contract(args.config)
    spec = CohortTradeSpec(
        HULK_STRATEGY,
        "SOL",
        float(contract["notional_usd"]),
        float(contract["leverage"]),
        float(contract["entry_fee_bps"]),
    )
    outcomes = _load_outcomes(args, spec)
    return build_artifact(
        outcomes,
        profile_contract=contract,
        data_evidence=_data_evidence(paths),
        source_summaries=_source_summaries(outcomes),
    )


def _load_outcomes(
    args: argparse.Namespace,
    base_spec: CohortTradeSpec,
) -> tuple[CohortOutcome, ...]:
    hulk_payloads = tuple(_load_json(path) for path in args.hulk_artifact)
    range_payloads = tuple(_load_json(path) for path in args.range_artifact)
    hulk = adapt_hulk_payloads(hulk_payloads, base_spec)
    breakout_report = _breakout_report(args.sol_bars, args.sol_funding)
    breakout = adapt_breakout_trades(
        breakout_report.trades,
        _spec_for(BREAKOUT_STRATEGY, base_spec),
    )
    range_onset = adapt_range_event_payloads(
        range_payloads,
        _spec_for(RANGE_STRATEGY, base_spec),
        effective_exposure=0.15,
    )
    return hulk + breakout + range_onset


def _breakout_report(
    bars_path: Path,
    funding_path: Path,
) -> HypeExitReplayReport:
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
        HypeExitPolicy(BREAKOUT_STRATEGY),
        config,
    )


def _spec_for(strategy_id: str, source: CohortTradeSpec) -> CohortTradeSpec:
    return CohortTradeSpec(
        strategy_id,
        source.symbol,
        source.notional_usd,
        source.leverage,
        source.entry_fee_bps,
        source.reference_equity_usd,
    )


def _validate_provider_contract(providers: Sequence[object]) -> None:
    identities = {getattr(row, "strategy_id", None) for row in providers}
    if identities != set(CURRENT_STATIC_PRIORITY):
        raise ValueError("v25 profile is missing a SOL priority source")
    for provider in providers:
        if "SOL" not in getattr(provider, "execution_symbols", ()):
            raise ValueError("v25 SOL priority source is not executable")
        if getattr(provider, "executable_sides")("SOL") != frozenset({"long", "short"}):
            raise ValueError("v25 SOL priority source must retain both sides")


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.config,
        *tuple(args.hulk_artifact),
        args.sol_bars,
        args.sol_funding,
        *tuple(args.range_artifact),
    )


def _source_summaries(outcomes: tuple[CohortOutcome, ...]) -> dict[str, object]:
    return {
        strategy: _route_summary(outcomes, strategy)
        for strategy in CURRENT_STATIC_PRIORITY
    }


def _route_summary(
    outcomes: tuple[CohortOutcome, ...],
    strategy_id: str,
) -> dict[str, object]:
    selected = tuple(row for row in outcomes if row.strategy_id == strategy_id)
    sides = {
        side: sum(row.side == side for row in selected) for side in ("long", "short")
    }
    return {
        "trades": len(selected),
        "by_side": sides,
        "first_entry_ms": min(row.outcome.entry_time_ms for row in selected),
        "last_exit_ms": max(row.outcome.exit_time_ms for row in selected),
    }


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"SOL priority source must be an object: {path}")
    return payload


def _require_files(paths: tuple[Path, ...]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"SOL priority sources are missing: {missing}")


def main() -> None:
    """Publish one immutable SOL priority interaction report."""
    args = build_parser().parse_args()
    artifact = run(args)
    write_immutable_json(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "development": artifact["development"],
                "opened_final_confirmation": artifact["opened_final_confirmation"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
