#!/usr/bin/env python3
"""Replay all inactive v29 routes through one report-only shared account."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
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
from hypervector.research.evidence_selected_portfolio import (
    PrioritizedPortfolioConfig,
    replay_prioritized_outcomes,
)
from hypervector.research.evidence_selected_portfolio_inputs import (
    adapt_hip3_sidecar,
    adapt_range_context_payload,
)

_PROFILE_ID = "multi_asset_bidirectional_evidence_selected_portfolio_canary_v29"
_PROFILE_FINGERPRINT = (
    "d1f4cd3b03197e9e7a9899ab32e2b198fd4bd2a4117f1ea64261824fcdc4a393"
)
_INITIAL_EQUITY_USD = 500.0
_ENTRY_FEE_BPS = 4.5
_CONFIG = Path(
    "configs/multi_asset_bidirectional_evidence_selected_portfolio_canary_v29.toml"
)
_RANGE_CONTEXT = Path(
    "data/logs/research/range_onset_context_challenger_ETH_20250728_20260728_v2.json"
)
_HIP3_SIDECAR = Path(
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.trades.parquet"
)
_ETH_BARS = Path("data/cache/ETH_1m_365d.parquet")
_ETH_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_SOL_ARTIFACTS = default_sol_range_artifact_paths()
_ROUTES = (
    ("range_onset_bidirectional_v1", "ETH"),
    ("range_onset_bidirectional_v1", "SOL"),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
)


@dataclass(frozen=True)
class V29ProfileContract:
    """Exact inactive profile identity and shared-account assumptions."""

    profile_id: str
    profile_fingerprint: str
    initial_equity_usd: float
    maximum_positions: int
    execution_scope: tuple[tuple[str, str], ...]
    observe_only_scope: tuple[tuple[str, str], ...]
    strategy_priority: tuple[str, ...]
    notional_caps: dict[str, float]
    leverage: dict[str, float]


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable local v29 diagnostic command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_CONFIG)
    parser.add_argument("--range-context", type=Path, default=_RANGE_CONTEXT)
    parser.add_argument("--eth-bars", type=Path, default=_ETH_BARS)
    parser.add_argument("--eth-funding", type=Path, default=_ETH_FUNDING)
    parser.add_argument(
        "--sol-artifact",
        type=Path,
        action="append",
        default=list(_SOL_ARTIFACTS),
    )
    parser.add_argument("--hip3-sidecar", type=Path, default=_HIP3_SIDECAR)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def load_profile_contract(path: Path) -> V29ProfileContract:
    """Load and bind the exact inactive v29 strategy-selection contract."""
    config = load_multi_asset_live_config(path, mode="observe")
    scope = tuple(
        (provider.strategy_id, symbol)
        for provider in sorted(config.providers, key=lambda row: row.priority)
        for symbol in provider.execution_symbols
    )
    observed = {
        (provider.strategy_id, symbol)
        for provider in config.providers
        for symbol in provider.symbols
    }
    observe_only = tuple(sorted(observed - set(scope)))
    _validate_profile_identity(config.profile_id, scope, observe_only)
    _validate_profile_directions(config)
    if config.profile_fingerprint != _PROFILE_FINGERPRINT:
        raise ValueError("v29 profile fingerprint does not match the frozen candidate")
    assets = {asset.symbol: asset for asset in config.assets}
    return V29ProfileContract(
        config.profile_id,
        config.profile_fingerprint,
        _INITIAL_EQUITY_USD,
        config.maximum_positions,
        scope,
        observe_only,
        tuple(
            provider.strategy_id
            for provider in sorted(config.providers, key=lambda row: row.priority)
        ),
        {symbol: assets[symbol].max_notional_usd for symbol in assets},
        {symbol: assets[symbol].leverage for symbol in assets},
    )


def build_artifact(
    contract: V29ProfileContract,
    scenarios: Mapping[str, tuple[CohortOutcome, ...]],
    *,
    data_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Build nominal and stress shared-account reports with route coverage."""
    if set(scenarios) != {"nominal", "stress"}:
        raise ValueError("v29 diagnostic requires nominal and stress scenarios")
    if not data_evidence:
        raise ValueError("v29 diagnostic requires immutable data evidence")
    replay_config = PrioritizedPortfolioConfig(
        contract.initial_equity_usd,
        contract.maximum_positions,
        contract.strategy_priority,
    )
    reports = {
        name: _scenario_report(rows, replay_config, contract.execution_scope)
        for name, rows in sorted(scenarios.items())
    }
    return {
        "schema_version": "evidence_selected_portfolio_v29_shared_arbitration_v1",
        "mode": "report_only_shared_priority_and_friction_diagnostic",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "profile_contract": asdict(contract),
        "source_phase_contract": {
            "allowed": ["development", "validation"],
            "sealed_holdout_accessed": False,
        },
        "input_trade_counts": {
            name: _input_counts(rows) for name, rows in sorted(scenarios.items())
        },
        "scenarios": reports,
        "friction_comparison": _friction_comparison(reports),
        "data_evidence": dict(data_evidence),
        "decision": "diagnostic_only_no_automatic_promotion",
        "limitations": _limitations(),
    }


def publish_artifact(path: Path, artifact: Mapping[str, object]) -> None:
    """Publish one immutable evidence record without replacement."""
    write_immutable_json(path, dict(artifact))


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load exact opened sources and build the v29 diagnostic artifact."""
    contract = load_profile_contract(args.config)
    paths = _source_paths(args)
    _require_files(paths)
    specs = _route_specs(contract)
    common = _crypto_outcomes(args, specs)
    hip3 = pd.read_parquet(args.hip3_sidecar)
    hip3_specs = {key: specs[key] for key in _ROUTES[3:]}
    scenarios = {
        friction: common + adapt_hip3_sidecar(hip3, hip3_specs, friction=friction)
        for friction in ("nominal", "stress")
    }
    return build_artifact(
        contract,
        scenarios,
        data_evidence=_data_evidence(paths),
    )


def _validate_profile_identity(
    profile_id: str,
    scope: tuple[tuple[str, str], ...],
    observe_only: tuple[tuple[str, str], ...],
) -> None:
    if profile_id != _PROFILE_ID:
        raise ValueError("v29 diagnostic requires the exact selected profile ID")
    if scope != _ROUTES:
        raise ValueError("v29 execution scope does not match all six selected routes")
    if observe_only:
        raise ValueError("v29 selected profile must contain zero observe-only filler")


def _validate_profile_directions(config: object) -> None:
    providers = getattr(config, "providers", ())
    for provider in providers:
        for symbol in provider.execution_symbols:
            if provider.executable_sides(symbol) != frozenset({"long", "short"}):
                raise ValueError("every v29 route must retain both execution sides")


def _route_specs(
    contract: V29ProfileContract,
) -> dict[tuple[str, str], CohortTradeSpec]:
    specs: dict[tuple[str, str], CohortTradeSpec] = {}
    for strategy, symbol in contract.execution_scope:
        fee_bps = 0.0 if symbol.startswith("xyz:") else _ENTRY_FEE_BPS
        specs[(strategy, symbol)] = CohortTradeSpec(
            strategy,
            symbol,
            contract.notional_caps[symbol],
            contract.leverage[symbol],
            fee_bps,
            contract.initial_equity_usd,
        )
    return specs


def _crypto_outcomes(
    args: argparse.Namespace,
    specs: Mapping[tuple[str, str], CohortTradeSpec],
) -> tuple[CohortOutcome, ...]:
    context = _load_json(args.range_context)
    eth_range = adapt_range_context_payload(
        context,
        specs[_ROUTES[0]],
        candidate_id="dual_mtf_not_opposed",
    )
    sol_payloads = tuple(_load_json(path) for path in args.sol_artifact)
    sol_range = adapt_range_event_payloads(sol_payloads, specs[_ROUTES[1]])
    eth = replay_eth_precompression_pullback(
        pd.read_parquet(args.eth_bars),
        pd.read_parquet(args.eth_funding),
    )
    eth_pullback = adapt_breakout_trades(eth.report.trades, specs[_ROUTES[2]])
    return eth_range + sol_range + eth_pullback


def _scenario_report(
    rows: tuple[CohortOutcome, ...],
    config: PrioritizedPortfolioConfig,
    expected_scope: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    observed = {(row.strategy_id, row.outcome.symbol) for row in rows}
    missing = sorted(set(expected_scope) - observed)
    if missing:
        raise ValueError(f"v29 scenario is missing selected route outcomes: {missing}")
    report = replay_prioritized_outcomes(rows, config).to_dict()
    accepted = report["accepted"]
    if not isinstance(accepted, tuple):
        raise RuntimeError("v29 accepted lifecycle projection is malformed")
    report["by_route"] = _accepted_attribution(accepted, include_side=False)
    report["by_route_side"] = _accepted_attribution(accepted, include_side=True)
    return report


def _accepted_attribution(
    rows: tuple[object, ...],
    *,
    include_side: bool,
) -> dict[str, dict[str, float | int | None]]:
    groups: dict[str, list[float]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise RuntimeError("v29 accepted lifecycle must be an object")
        key = f"{raw['strategy_id']}|{raw['symbol']}"
        if include_side:
            key = f"{key}|{raw['side']}"
        groups.setdefault(key, []).append(float(raw["net_pnl_usd"]))
    return {key: _summary(values) for key, values in sorted(groups.items())}


def _summary(values: list[float]) -> dict[str, float | int | None]:
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(values) - len(wins) - len(losses),
        "net_pnl_usd": sum(values),
        "profit_factor": sum(wins) / sum(losses) if losses else None,
    }


def _input_counts(rows: tuple[CohortOutcome, ...]) -> dict[str, object]:
    by_route: dict[str, int] = {}
    by_route_side: dict[str, int] = {}
    for row in rows:
        route = f"{row.strategy_id}|{row.outcome.symbol}"
        by_route[route] = by_route.get(route, 0) + 1
        side = f"{route}|{row.side}"
        by_route_side[side] = by_route_side.get(side, 0) + 1
    return {
        "total": len(rows),
        "by_route": dict(sorted(by_route.items())),
        "by_route_side": dict(sorted(by_route_side.items())),
    }


def _friction_comparison(
    reports: Mapping[str, Mapping[str, object]],
) -> dict[str, float]:
    nominal = reports["nominal"]
    stress = reports["stress"]
    return {
        "stress_minus_nominal_net_pnl_usd": float(stress["net_pnl_usd"])
        - float(nominal["net_pnl_usd"]),
        "stress_minus_nominal_final_equity_usd": float(stress["final_equity_usd"])
        - float(nominal["final_equity_usd"]),
    }


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.config,
        args.range_context,
        args.eth_bars,
        args.eth_funding,
        *tuple(args.sol_artifact),
        args.hip3_sidecar,
    )


def _require_files(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"v29 portfolio source is missing: {path}")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"v29 portfolio JSON source must be an object: {path}")
    return value


def _data_evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _limitations() -> list[str]:
    return [
        "opened development and validation evidence is descriptive, not a sealed holdout",
        "precomputed exits cannot reproduce opposite-intent early closes",
        "HIP-3 entry fee reservation approximates half of observed round-trip fees",
        "completed-bar replay cannot establish private IOC fill or queue parity",
        "realized-equity drawdown omits concurrent intratrade mark-to-market paths",
        "fixed notional caps prevent upside compounding and scale down after account loss",
        "a positive aggregate cannot establish edge for every selected route",
    ]


def main() -> None:
    """Publish one immutable v29 priority and friction diagnostic."""
    args = build_parser().parse_args()
    artifact = run(args)
    publish_artifact(args.out, artifact)
    scenarios = artifact["scenarios"]
    if not isinstance(scenarios, dict):
        raise RuntimeError("v29 scenario output is malformed")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "nominal": scenarios["nominal"],
                "stress": scenarios["stress"],
                "execution_authority": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
