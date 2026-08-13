#!/usr/bin/env python3
"""Replay frozen v29 routes inside one fixed common entry window."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.current_cohort_shared_portfolio import CohortOutcome


def _load_frozen_runner() -> ModuleType:
    """Load the frozen sibling command without requiring a scripts package."""
    name = "_hypervector_evidence_selected_portfolio_v29_frozen"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).with_name("evidence_selected_portfolio_v29.py")
    spec = spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load frozen v29 runner: {path}")
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frozen = _load_frozen_runner()

WINDOW_START_MS = 1_781_320_500_000
WINDOW_END_MS = 1_783_252_800_000
WINDOW_START_UTC = "2026-06-13T03:15:00Z"
WINDOW_END_UTC = "2026-07-05T12:00:00Z"
FULL_WINDOW_ARTIFACT = Path(
    "data/logs/research/"
    "evidence_selected_portfolio_v29_shared_arbitration_20260808T070837Z.json"
)
FULL_WINDOW_SHA256 = "8af24ef32ee46be46f28f0f744313b40b9f8d380b3758e3a46094b5bf643bc54"
FULL_WINDOW_BYTES = 727_478
ROUTES = (
    ("range_onset_bidirectional_v1", "ETH"),
    ("range_onset_bidirectional_v1", "SOL"),
    ("eth_breakout_precompression_pullback_bidirectional_v1", "ETH"),
    ("hip3_swing_ha_sp500_spcx_bidirectional_v2", "xyz:SPCX"),
    ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    ("hip3_swing_ha_sndk_gold_brent_bidirectional_v1", "xyz:GOLD"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the fixed-window companion to the frozen revision-4 command."""
    parser = frozen.build_parser()
    parser.description = __doc__
    parser.add_argument(
        "--full-window-artifact",
        type=Path,
        default=FULL_WINDOW_ARTIFACT,
    )
    return parser


def filter_entry_window(rows: tuple[CohortOutcome, ...]) -> tuple[CohortOutcome, ...]:
    """Keep outcomes whose entry lies in the fixed half-open UTC interval."""
    return tuple(
        row
        for row in rows
        if WINDOW_START_MS <= row.outcome.entry_time_ms < WINDOW_END_MS
    )


def route_side_coverage(
    rows: tuple[CohortOutcome, ...],
    expected_scope: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    """Report exact route and direction counts without creating a trade gate."""
    by_route: dict[str, int] = {}
    by_route_side: dict[str, int] = {}
    for row in rows:
        route = f"{row.strategy_id}|{row.outcome.symbol}"
        route_side = f"{route}|{row.side}"
        by_route[route] = by_route.get(route, 0) + 1
        by_route_side[route_side] = by_route_side.get(route_side, 0) + 1
    expected_routes = [f"{strategy}|{symbol}" for strategy, symbol in expected_scope]
    missing_routes = sorted(set(expected_routes) - set(by_route))
    expected_sides = [
        f"{strategy}|{symbol}|{side}"
        for strategy, symbol in expected_scope
        for side in ("long", "short")
    ]
    missing_sides = sorted(set(expected_sides) - set(by_route_side))
    return {
        "total": len(rows),
        "by_route": dict(sorted(by_route.items())),
        "by_route_side": dict(sorted(by_route_side.items())),
        "all_routes_present": not missing_routes,
        "missing_routes": missing_routes,
        "all_route_sides_present": not missing_sides,
        "missing_route_sides": missing_sides,
    }


def build_common_window_artifact(
    contract: frozen.V29ProfileContract,
    scenarios: Mapping[str, tuple[CohortOutcome, ...]],
    *,
    data_evidence: Mapping[str, object],
    full_window_artifact: Mapping[str, object],
    full_window_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Build a fixed-window artifact and bind it to the frozen full replay."""
    _validate_scenario_names(scenarios)
    _validate_full_window(full_window_artifact, contract, data_evidence)
    filtered = {
        name: filter_entry_window(rows) for name, rows in sorted(scenarios.items())
    }
    coverage = {
        name: route_side_coverage(rows, contract.execution_scope)
        for name, rows in filtered.items()
    }
    population = _scenario_population_comparison(filtered)
    missing = {
        name: value["missing_routes"]
        for name, value in coverage.items()
        if value["missing_routes"]
    }
    if missing:
        raise ValueError(f"common window is missing selected v29 routes: {missing}")
    artifact = frozen.build_artifact(
        contract,
        filtered,
        data_evidence=data_evidence,
    )
    return _apply_common_window_metadata(
        artifact,
        contract,
        coverage,
        population,
        full_window_artifact,
        full_window_evidence,
    )


def _apply_common_window_metadata(
    artifact: dict[str, object],
    contract: object,
    coverage: Mapping[str, dict[str, object]],
    population: Mapping[str, object],
    full_window_artifact: Mapping[str, object],
    full_window_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Attach the fixed-window contract and immutable comparison identity."""
    artifact["schema_version"] = "evidence_selected_portfolio_v29_common_window_v1"
    artifact["mode"] = "report_only_fixed_common_window_shared_priority_diagnostic"
    artifact["common_window"] = _window_contract(coverage, population)
    artifact["full_window_reference"] = {
        "schema_version": full_window_artifact["schema_version"],
        "profile_fingerprint": getattr(contract, "profile_fingerprint"),
        "evidence": dict(full_window_evidence),
    }
    artifact["full_window_comparison"] = _full_window_comparison(
        artifact,
        full_window_artifact,
        coverage,
    )
    artifact["decision"] = "diagnostic_only_no_automatic_promotion"
    limitations = artifact["limitations"]
    if not isinstance(limitations, list):
        raise RuntimeError("common-window limitations projection is malformed")
    limitations.extend(
        [
            "the fixed overlap is post-hoc opened evidence, not a sealed holdout",
            "route-side absences remain reported evidence rather than technical aborts",
            "the shorter common window materially reduces range-onset sample size",
        ]
    )
    return artifact


def publish_artifact(path: Path, artifact: Mapping[str, object]) -> None:
    """Publish one immutable common-window evidence record."""
    write_immutable_json(path, dict(artifact))


def run(args: argparse.Namespace) -> dict[str, object]:
    """Load frozen sources, filter raw outcomes, and build the companion report."""
    _validate_frozen_scope()
    contract = frozen.load_profile_contract(args.config)
    source_paths = frozen._source_paths(args)
    frozen._require_files(source_paths)
    if not args.full_window_artifact.is_file():
        raise FileNotFoundError(
            f"frozen v29 full-window artifact is missing: {args.full_window_artifact}"
        )
    full_evidence = {
        "path": str(args.full_window_artifact.resolve()),
        **file_evidence(args.full_window_artifact),
    }
    _validate_frozen_artifact_file(full_evidence)
    full_artifact = _load_json(args.full_window_artifact)
    scenarios = _raw_scenarios(args, contract)
    return build_common_window_artifact(
        contract,
        scenarios,
        data_evidence=frozen._data_evidence(source_paths),
        full_window_artifact=full_artifact,
        full_window_evidence=full_evidence,
    )


def _raw_scenarios(
    args: argparse.Namespace,
    contract: frozen.V29ProfileContract,
) -> dict[str, tuple[CohortOutcome, ...]]:
    specs = frozen._route_specs(contract)
    crypto = frozen._crypto_outcomes(args, specs)
    hip3 = pd.read_parquet(args.hip3_sidecar)
    hip3_specs = {key: specs[key] for key in ROUTES[3:]}
    return {
        friction: crypto
        + frozen.adapt_hip3_sidecar(hip3, hip3_specs, friction=friction)
        for friction in ("nominal", "stress")
    }


def _validate_scenario_names(
    scenarios: Mapping[str, tuple[CohortOutcome, ...]],
) -> None:
    if set(scenarios) != {"nominal", "stress"}:
        raise ValueError(
            "common-window diagnostic requires nominal and stress scenarios"
        )


def _validate_frozen_scope() -> None:
    if tuple(frozen._ROUTES) != ROUTES:
        raise RuntimeError("frozen v29 route scope changed after revision 4")


def _validate_frozen_artifact_file(evidence: Mapping[str, object]) -> None:
    if (
        evidence.get("sha256") != FULL_WINDOW_SHA256
        or evidence.get("bytes") != FULL_WINDOW_BYTES
    ):
        raise ValueError("frozen v29 full-window artifact file identity changed")


def _validate_full_window(
    artifact: Mapping[str, object],
    contract: frozen.V29ProfileContract,
    data_evidence: Mapping[str, object],
) -> None:
    if (
        artifact.get("schema_version")
        != "evidence_selected_portfolio_v29_shared_arbitration_v1"
    ):
        raise ValueError("full-window schema is not the frozen revision-4 diagnostic")
    if (
        artifact.get("execution_authority") != "none"
        or artifact.get("report_only") is not True
    ):
        raise ValueError("full-window artifact violates report-only authority")
    if artifact.get("runtime_strategy_changed") is not False:
        raise ValueError("full-window artifact claims a runtime strategy change")
    profile = _mapping(artifact.get("profile_contract"), "full-window profile")
    if profile.get("profile_fingerprint") != contract.profile_fingerprint:
        raise ValueError("full-window profile fingerprint does not match v29")
    phase = _mapping(artifact.get("source_phase_contract"), "full-window phase")
    if phase.get("sealed_holdout_accessed") is not False:
        raise ValueError("full-window artifact accessed a sealed holdout")
    scenarios = _mapping(artifact.get("scenarios"), "full-window scenarios")
    if set(scenarios) != {"nominal", "stress"}:
        raise ValueError("full-window artifact scenario scope changed")
    if artifact.get("data_evidence") != dict(data_evidence):
        raise ValueError(
            "common-window source evidence differs from the full-window replay"
        )


def _window_contract(
    coverage: Mapping[str, dict[str, object]],
    population: Mapping[str, object],
) -> dict[str, object]:
    return {
        "start_utc_inclusive": WINDOW_START_UTC,
        "end_utc_exclusive": WINDOW_END_UTC,
        "start_ms": WINDOW_START_MS,
        "end_ms_exclusive": WINDOW_END_MS,
        "duration_days": (WINDOW_END_MS - WINDOW_START_MS) / 86_400_000.0,
        "filter_basis": "entry_time_ms",
        "selection_basis": (
            "latest first selected-route entry through first 15m boundary after "
            "earliest last selected-route entry in frozen revision-4 evidence"
        ),
        "coverage_by_scenario": dict(coverage),
        "scenario_population_comparison": dict(population),
    }


def _scenario_population_comparison(
    scenarios: Mapping[str, tuple[CohortOutcome, ...]],
) -> dict[str, object]:
    """Expose friction-path changes in the raw lifecycle population."""
    nominal = Counter(_population_identity(row) for row in scenarios["nominal"])
    stress = Counter(_population_identity(row) for row in scenarios["stress"])
    nominal_only = nominal - stress
    stress_only = stress - nominal
    shared = nominal & stress
    return {
        "identity_basis": "strategy_id|symbol|side|entry_time_ms",
        "nominal_total": sum(nominal.values()),
        "stress_total": sum(stress.values()),
        "shared_rows": sum(shared.values()),
        "path_dependent_population": bool(nominal_only or stress_only),
        "nominal_only": _population_differences(nominal_only),
        "stress_only": _population_differences(stress_only),
        "interpretation": (
            "scenario-specific lifecycle friction can change exit timing and later "
            "entry eligibility; differences are preserved rather than normalized"
        ),
    }


def _population_identity(row: CohortOutcome) -> str:
    """Return the scenario-neutral identity of one raw route entry."""
    return (
        f"{row.strategy_id}|{row.outcome.symbol}|{row.side}|{row.outcome.entry_time_ms}"
    )


def _population_differences(rows: Counter[str]) -> list[dict[str, object]]:
    """Serialize positive multiset differences in deterministic order."""
    return [
        {"identity": identity, "count": count}
        for identity, count in sorted(rows.items())
    ]


def _full_window_comparison(
    common: Mapping[str, object],
    full: Mapping[str, object],
    coverage: Mapping[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    common_scenarios = _mapping(common.get("scenarios"), "common-window scenarios")
    full_scenarios = _mapping(full.get("scenarios"), "full-window scenarios")
    result: dict[str, dict[str, object]] = {}
    for name in ("nominal", "stress"):
        common_report = _mapping(common_scenarios.get(name), f"common {name}")
        full_report = _mapping(full_scenarios.get(name), f"full {name}")
        common_net = _number(common_report.get("net_pnl_usd"), "common net PnL")
        full_net = _number(full_report.get("net_pnl_usd"), "full net PnL")
        concentration = _route_concentration(common_report)
        result[name] = {
            "common_window_completed_trades": _integer(
                common_report.get("completed_trades"), "common trades"
            ),
            "full_window_completed_trades": _integer(
                full_report.get("completed_trades"), "full trades"
            ),
            "common_window_net_pnl_usd": common_net,
            "full_window_net_pnl_usd": full_net,
            "net_pnl_delta_usd": common_net - full_net,
            "common_window_return_pct": _number(
                common_report.get("return_pct"), "common return"
            ),
            "common_window_profit_factor": common_report.get("profit_factor"),
            "common_window_maximum_drawdown_pct": _number(
                common_report.get("maximum_drawdown_pct"), "common drawdown"
            ),
            "negative_routes": concentration["negative_routes"],
            "largest_positive_route": concentration["largest_positive_route"],
            "largest_positive_route_share": concentration[
                "largest_positive_route_share"
            ],
            "all_routes_present": coverage[name]["all_routes_present"],
            "all_route_sides_present": coverage[name]["all_route_sides_present"],
            "missing_route_sides": coverage[name]["missing_route_sides"],
        }
    return result


def _route_concentration(report: Mapping[str, object]) -> dict[str, object]:
    by_route = _mapping(report.get("by_route"), "route attribution")
    pnl = {
        key: _number(
            _mapping(value, f"route {key}").get("net_pnl_usd"), f"route {key} PnL"
        )
        for key, value in by_route.items()
    }
    positive = {key: value for key, value in pnl.items() if value > 0.0}
    positive_total = sum(positive.values())
    largest = max(positive, key=positive.get) if positive else None
    share = positive[largest] / positive_total if largest is not None else None
    return {
        "negative_routes": sorted(key for key, value in pnl.items() if value < 0.0),
        "largest_positive_route": largest,
        "largest_positive_route_share": share,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    return float(value)


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"common-window JSON source must be an object: {path}")
    return value


def main() -> None:
    """Publish one immutable fixed-window v29 diagnostic."""
    args = build_parser().parse_args()
    artifact = run(args)
    publish_artifact(args.out, artifact)
    scenarios = _mapping(artifact.get("scenarios"), "published scenarios")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "execution_authority": artifact["execution_authority"],
                "nominal_net_pnl_usd": _mapping(
                    scenarios.get("nominal"), "nominal report"
                )["net_pnl_usd"],
                "stress_net_pnl_usd": _mapping(
                    scenarios.get("stress"), "stress report"
                )["net_pnl_usd"],
                "common_window": artifact["common_window"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
