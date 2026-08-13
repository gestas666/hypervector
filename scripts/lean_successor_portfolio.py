#!/usr/bin/env python3
"""Compare fixed lean successor portfolios through one report-only account."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
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
)
from hypervector.research.eth_pullback_replay import replay_eth_precompression_pullback
from hypervector.research.evidence_selected_portfolio import PrioritizedPortfolioConfig
from hypervector.research.evidence_selected_portfolio_inputs import (
    adapt_hip3_sidecar,
    adapt_range_context_payload,
)
from hypervector.research.lean_successor_portfolio import (
    EvidenceWindow,
    RouteKey,
    RouteOutcomes,
    SuccessorVariant,
    apply_incremental_round_trip_cost,
    evaluate_successor_comparison,
)

RANGE = "range_onset_bidirectional_v1"
PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"
SPCX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
SOL_ROUTE = (RANGE, "SOL")
ETH_RANGE_ROUTE = (RANGE, "ETH")
ETH_PULLBACK_ROUTE = (PULLBACK, "ETH")
SPCX_ROUTE = (SPCX, "xyz:SPCX")
NOMINAL_CRYPTO_ROUND_TRIP_BPS = 13.0
STRESS_CRYPTO_ROUND_TRIP_BPS = 20.0
_INITIAL_EQUITY_USD = 500.0
_RANGE_CONTEXT = Path(
    "data/logs/research/range_onset_context_challenger_ETH_20250728_20260728_v2.json"
)
_ETH_BARS = Path("data/cache/ETH_1m_365d.parquet")
_ETH_FUNDING = Path(
    "data/cache/vendor/hyperliquid/ETH/"
    "20250728T000000000000Z_20260728T000000000000Z_funding/funding.parquet"
)
_HIP3_SIDECAR = Path(
    "data/logs/research/hip3_v25_lifecycle_bar_diagnostic_20260807.trades.parquet"
)
_ACTIVE_PROFILE = Path(
    "configs/multi_asset_bidirectional_complete_portfolio_canary_v25.toml"
)
_IMPLEMENTATION_SOURCES = (
    Path("scripts/multi_asset_bidirectional_live.py"),
    Path("src/hypervector/live/multi_asset_signal_source.py"),
    Path("src/hypervector/live/hip3_cohort_providers.py"),
    Path("src/hypervector/research/eth_pullback_replay.py"),
    Path("src/hypervector/research/range_onset_signals.py"),
    Path("src/hypervector/research/evidence_selected_portfolio.py"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the immutable local successor comparison command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range-context", type=Path, default=_RANGE_CONTEXT)
    parser.add_argument("--eth-bars", type=Path, default=_ETH_BARS)
    parser.add_argument("--eth-funding", type=Path, default=_ETH_FUNDING)
    parser.add_argument(
        "--sol-artifact",
        type=Path,
        action="append",
        default=list(default_sol_range_artifact_paths()),
    )
    parser.add_argument("--hip3-sidecar", type=Path, default=_HIP3_SIDECAR)
    parser.add_argument("--active-profile", type=Path, default=_ACTIVE_PROFILE)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def fixed_variants() -> tuple[SuccessorVariant, ...]:
    """Return the preregistered additive route surface."""
    return (
        SuccessorVariant("sol_range_control", (SOL_ROUTE,)),
        SuccessorVariant(
            "sol_range_spcx",
            (SOL_ROUTE, SPCX_ROUTE),
            baseline_variant_id="sol_range_control",
        ),
        SuccessorVariant(
            "sol_range_spcx_eth_pullback",
            (SOL_ROUTE, SPCX_ROUTE, ETH_PULLBACK_ROUTE),
            baseline_variant_id="sol_range_spcx",
        ),
        SuccessorVariant(
            "sol_range_spcx_eth_dual_mtf",
            (SOL_ROUTE, SPCX_ROUTE, ETH_RANGE_ROUTE),
            baseline_variant_id="sol_range_spcx",
        ),
    )


def fixed_windows() -> tuple[EvidenceWindow, ...]:
    """Return the preregistered common and full opened evidence windows."""
    return (
        EvidenceWindow("development_common", 1_781_320_500_000, 1_783_252_800_000),
        EvidenceWindow("opened_final_common", 1_783_296_900_000, 1_784_593_800_000),
        EvidenceWindow("full_opened_descriptive", None, None),
    )


def publish_artifact(path: Path, artifact: Mapping[str, object]) -> None:
    """Write one append-only report-only comparison artifact."""
    write_immutable_json(path, dict(artifact))


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load immutable local sources and build the fixed successor comparison."""
    source_paths = _source_paths(args)
    _require_files(source_paths + _IMPLEMENTATION_SOURCES)
    scenarios = _build_scenarios(args)
    config = PrioritizedPortfolioConfig(
        _INITIAL_EQUITY_USD,
        3,
        (RANGE, PULLBACK, SPCX),
    )
    artifact = evaluate_successor_comparison(
        scenarios,
        fixed_variants(),
        fixed_windows(),
        config,
    )
    return _attach_contract(
        artifact,
        scenarios,
        _evidence(source_paths),
        _evidence(_IMPLEMENTATION_SOURCES),
    )


def _build_scenarios(args: argparse.Namespace) -> dict[str, RouteOutcomes]:
    specs = _route_specs()
    nominal_crypto = _load_crypto_routes(args, specs)
    stress_delta = STRESS_CRYPTO_ROUND_TRIP_BPS - NOMINAL_CRYPTO_ROUND_TRIP_BPS
    stress_crypto = {
        route: apply_incremental_round_trip_cost(
            rows,
            {route: specs[route].notional_usd},
            incremental_bps=stress_delta,
        )
        for route, rows in nominal_crypto.items()
    }
    hip3 = pd.read_parquet(args.hip3_sidecar)
    nominal = dict(nominal_crypto)
    stress = dict(stress_crypto)
    nominal[SPCX_ROUTE] = adapt_hip3_sidecar(
        hip3,
        {SPCX_ROUTE: specs[SPCX_ROUTE]},
        friction="nominal",
    )
    stress[SPCX_ROUTE] = adapt_hip3_sidecar(
        hip3,
        {SPCX_ROUTE: specs[SPCX_ROUTE]},
        friction="stress",
    )
    return {"nominal": nominal, "stress": stress}


def _load_crypto_routes(
    args: argparse.Namespace,
    specs: Mapping[RouteKey, CohortTradeSpec],
) -> dict[RouteKey, tuple[CohortOutcome, ...]]:
    context = _load_json(args.range_context)
    eth_range = adapt_range_context_payload(
        context,
        specs[ETH_RANGE_ROUTE],
        candidate_id="dual_mtf_not_opposed",
    )
    sol_range = adapt_range_event_payloads(
        tuple(_load_json(path) for path in args.sol_artifact),
        specs[SOL_ROUTE],
    )
    replay = replay_eth_precompression_pullback(
        pd.read_parquet(args.eth_bars),
        pd.read_parquet(args.eth_funding),
    )
    pullback = adapt_breakout_trades(replay.report.trades, specs[ETH_PULLBACK_ROUTE])
    return {
        SOL_ROUTE: sol_range,
        ETH_RANGE_ROUTE: eth_range,
        ETH_PULLBACK_ROUTE: pullback,
    }


def _route_specs() -> dict[RouteKey, CohortTradeSpec]:
    return {
        SOL_ROUTE: CohortTradeSpec(RANGE, "SOL", 75.0, 5.0, 4.5),
        ETH_RANGE_ROUTE: CohortTradeSpec(RANGE, "ETH", 25.0, 5.0, 4.5),
        ETH_PULLBACK_ROUTE: CohortTradeSpec(PULLBACK, "ETH", 25.0, 5.0, 4.5),
        SPCX_ROUTE: CohortTradeSpec(SPCX, "xyz:SPCX", 75.0, 5.0, 0.0),
    }


def _attach_contract(
    artifact: dict[str, object],
    scenarios: Mapping[str, RouteOutcomes],
    data_evidence: Mapping[str, object],
    implementation_evidence: Mapping[str, object],
) -> dict[str, object]:
    artifact["friction_contract"] = {
        "crypto_nominal_round_trip_bps": NOMINAL_CRYPTO_ROUND_TRIP_BPS,
        "crypto_stress_round_trip_bps": STRESS_CRYPTO_ROUND_TRIP_BPS,
        "crypto_incremental_stress_bps": (
            STRESS_CRYPTO_ROUND_TRIP_BPS - NOMINAL_CRYPTO_ROUND_TRIP_BPS
        ),
        "spcx": "immutable venue-specific nominal/stress lifecycle rows",
    }
    artifact["route_contract"] = _route_contract()
    artifact["input_route_counts"] = _input_counts(scenarios)
    artifact["data_evidence"] = dict(data_evidence)
    artifact["implementation_evidence"] = dict(implementation_evidence)
    artifact["source_phase_contract"] = {
        "sealed_holdout_accessed": False,
        "development_and_opened_final_are_descriptive": True,
    }
    artifact["head_to_head"] = _head_to_head(artifact)
    artifact["decision"] = "diagnostic_only_no_automatic_promotion"
    artifact["limitations"] = _limitations()
    return artifact


def _route_contract() -> dict[str, object]:
    specs = _route_specs()
    return {
        f"{strategy}|{symbol}": {
            "notional_usd": specs[(strategy, symbol)].notional_usd,
            "leverage": specs[(strategy, symbol)].leverage,
            "directions": ["long", "short"],
        }
        for strategy, symbol in specs
    }


def _input_counts(scenarios: Mapping[str, RouteOutcomes]) -> dict[str, object]:
    return {
        friction: {
            f"{strategy}|{symbol}": len(rows)
            for (strategy, symbol), rows in sorted(route_rows.items())
        }
        for friction, route_rows in sorted(scenarios.items())
    }


def _head_to_head(artifact: Mapping[str, object]) -> dict[str, object]:
    windows = artifact.get("windows")
    if not isinstance(windows, Mapping):
        raise RuntimeError("successor comparison windows are malformed")
    return {
        window: {
            friction: _candidate_delta(reports)
            for friction, reports in _mapping(value, "window").items()
        }
        for window, value in windows.items()
    }


def _candidate_delta(reports: object) -> dict[str, float]:
    values = _mapping(reports, "friction reports")
    dual = _mapping(values["sol_range_spcx_eth_dual_mtf"], "dual-MTF report")
    pullback = _mapping(values["sol_range_spcx_eth_pullback"], "pullback report")
    return {
        "dual_mtf_minus_pullback_net_pnl_usd": float(dual["net_pnl_usd"])
        - float(pullback["net_pnl_usd"]),
        "dual_mtf_minus_pullback_completed_trades": float(dual["completed_trades"])
        - float(pullback["completed_trades"]),
    }


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.range_context,
        args.eth_bars,
        args.eth_funding,
        *tuple(args.sol_artifact),
        args.hip3_sidecar,
        args.active_profile,
    )


def _require_files(paths: tuple[Path, ...]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"lean successor source is missing: {path}")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"lean successor JSON source must be an object: {path}")
    return value


def _evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be an object with text keys")
    return value


def _limitations() -> list[str]:
    return [
        "all windows are opened descriptive evidence rather than a sealed holdout",
        "the full source union has asynchronous route coverage start dates",
        "completed outcomes cannot reproduce opposite-intent close interactions",
        "realized-equity drawdown omits concurrent intratrade mark-to-market paths",
        "public replay cannot establish private IOC queue position or stop gaps",
        "the ETH dual-MTF rule and all included routes are selection-contaminated",
        "fixed notional caps do not estimate compounding at larger account sizes",
        "a positive route or aggregate remains vulnerable to largest-winner concentration",
    ]


def _console_summary(artifact: Mapping[str, object]) -> dict[str, object]:
    windows = _mapping(artifact["windows"], "artifact windows")
    return {
        window: {
            friction: {
                variant: {
                    key: report[key]
                    for key in (
                        "completed_trades",
                        "net_pnl_usd",
                        "profit_factor",
                        "maximum_drawdown_pct",
                    )
                }
                for variant, report in _mapping(reports, "variant reports").items()
            }
            for friction, reports in _mapping(value, "friction reports").items()
        }
        for window, value in windows.items()
    }


def main() -> None:
    """Publish one immutable lean successor comparison."""
    args = build_parser().parse_args()
    artifact = run(args)
    publish_artifact(args.out, artifact)
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "execution_authority": "none",
                "summary": _console_summary(artifact),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
