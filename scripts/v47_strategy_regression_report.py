#!/usr/bin/env python3
"""Build the source-reconciled strategy-regression and v47 repair report."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import tomllib
from typing import cast

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.growth_candidate_report_data import (
    candidate_capacity,
    candidate_routes,
    candidate_slot_risk,
)
from hypervector.research.v47_strategy_regression_report_manifest import (
    report_blocks,
    report_cards,
    report_charts,
    report_tables,
)

JsonMap = dict[str, object]


@dataclass(frozen=True)
class ReportPaths:
    """Exact local evidence paths consumed by the report."""

    checkpoint: Path
    v47_config: Path
    v47_stress: Path
    hip3_parity: Path
    hulk: Path
    hulk_holdout: Path
    hype: Path
    eth_range: Path
    sol_range: Path
    regime: Path
    disposition: Path


def default_report_paths(root: Path) -> ReportPaths:
    """Return the frozen report evidence below a repository root."""
    research = root / "data/logs/research"
    cohort = research / "bidirectional_cohort"
    return ReportPaths(
        checkpoint=root / "data/runtime/bidirectional_cohort/latest_checkpoint.json",
        v47_config=root
        / "configs/multi_asset_growth_first_5000_repaired_candidate_v47.toml",
        v47_stress=cohort / "v47_growth_sizing_stress_20260812_v3.json",
        hip3_parity=root
        / "docs/research-journal/hip3-live-pressure-freshness-parity-v2.json",
        hulk=research / "20260801_hulk_short_robust_v3_btc_validation.json",
        hulk_holdout=research / "20260801_hulk_short_robust_v3_btc_pseudo_holdout.json",
        hype=research / "hype_compression_breakout_challenger_20260811_v4/report.json",
        eth_range=research
        / "range_onset_context_challenger_ETH_20250728_20260728_v2.json",
        sol_range=research
        / "sol_range_onset_backward_exact_audit_20250302_20250727_v2.json",
        regime=cohort / "v39_regime_forward_accuracy_20260812T152631Z_v4.json",
        disposition=root
        / "docs/research-journal/v47-strategy-regression-disposition.json",
    )


def _mapping(value: object, label: str) -> JsonMap:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(JsonMap, value)


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    return value


def _load(path: Path) -> JsonMap:
    if not path.is_file():
        raise FileNotFoundError(f"report evidence does not exist: {path}")
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _nested(source: JsonMap, *keys: str) -> object:
    current: object = source
    for key in keys:
        current = _mapping(current, ".".join(keys))[key]
    return current


def _performance(checkpoint: JsonMap, scope: str) -> JsonMap:
    return _mapping(
        _nested(checkpoint, "audit", "trade_reflections", "performance", scope),
        f"performance.{scope}",
    )


def _close(value: float, expected: float, label: str) -> None:
    if not math.isclose(value, expected, abs_tol=1e-9):
        raise ValueError(f"{label} does not reconcile: {value} != {expected}")


def _performance_row(performance: JsonMap) -> JsonMap:
    return {
        "closed_trades": int(performance["closed_trades"]),
        "wins": int(performance["wins"]),
        "losses": int(performance["losses"]),
        "net_pnl_usd": float(performance["net_pnl_usd"]),
        "profit_factor": performance["profit_factor"],
        "fees_usd": float(performance["fees_usd"]),
        "funding_usd": float(performance["funding_usd"]),
        "net_ex_largest_usd": performance["net_pnl_excluding_largest_winner_usd"],
        "maximum_drawdown_usd": float(
            performance["maximum_closed_sequence_drawdown_usd"]
        ),
    }


def _strategy_label(strategy: str) -> str:
    aliases = {
        "hulk_expansion_bidirectional_tuned_v2": "Hulk Expansion",
        "hulk_expansion_short_robust_v3": "BTC Hulk Short v3",
        "hype_breakout_compression_pullback_bidirectional_v1": "HYPE Compression",
        "hype_breakout_onset_bidirectional_v1": "HT Onset",
        "hypervelocity_source_follow_bidirectional_5m_v1": "HV Source 5m",
        "range_onset_bidirectional_v1": "Range Onset",
        "liquidity_sweep_long_1h_stop60_target60_v2": "BTC Sweep Long",
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2": "SP500 Pressure v2",
    }
    if "hip3_swing" in strategy:
        return "HIP3 Swing"
    if "hip3_breakout_pressure" in strategy:
        return "HIP3 Pressure"
    return aliases.get(strategy, strategy)


def _validate_accounting(checkpoint: JsonMap) -> None:
    total = _mapping(_performance(checkpoint, "all_time_live")["total"], "total")
    routes = _mapping(
        _performance(checkpoint, "all_time_live")["by_provider_symbol"], "routes"
    )
    rows = [_mapping(value, "route") for value in routes.values()]
    if sum(int(row["closed_trades"]) for row in rows) != int(total["closed_trades"]):
        raise ValueError("all-time route trade count does not reconcile")
    _close(
        sum(float(row["net_pnl_usd"]) for row in rows),
        float(total["net_pnl_usd"]),
        "all-time route net",
    )


def _validate_inputs(inputs: JsonMap) -> None:
    config = _mapping(inputs["v47_config"], "v47_config")
    stress = _mapping(inputs["v47_stress"], "v47_stress")
    parity = _mapping(inputs["hip3_parity"], "hip3_parity")
    if config["profile"] != stress["profile_id"]:
        raise ValueError("v47 config and stress profile identity differ")
    providers = [
        _mapping(row, "provider") for row in _sequence(config["providers"], "providers")
    ]
    identities = {str(row["strategy_id"]) for row in providers}
    if "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v2" not in identities:
        raise ValueError("v47 does not contain corrected HIP3 v2")
    if "hype_breakout_onset_bidirectional_v1" in identities:
        raise ValueError("v47 retained the rejected HT onset transfer")
    affected = _sequence(
        parity["closed_entry_actions_older_than_15_seconds"], "affected"
    )
    if len(affected) != 4:
        raise ValueError("HIP3 parity affected-close count changed")
    _close(
        sum(float(_mapping(row, "affected")["net_pnl_usd"]) for row in affected),
        -2.097088,
        "HIP3 affected net",
    )
    disposition = _mapping(inputs["disposition"], "disposition")
    if disposition["profile_id"] != config["profile"]:
        raise ValueError("strategy disposition and v47 profile identity differ")
    decisions = [
        _mapping(row, "decision")
        for row in _sequence(disposition["decisions"], "decisions")
    ]
    hip3 = next(row for row in decisions if row["strategy"] == "HIP3 pressure v1")
    if int(hip3["affected_closed_trades"]) != len(affected):
        raise ValueError("strategy disposition HIP3 trade count is stale")
    _close(float(hip3["affected_net_pnl_usd"]), -2.097088, "disposition HIP3 net")


def _all_time_routes(checkpoint: JsonMap) -> list[JsonMap]:
    routes = _mapping(
        _performance(checkpoint, "all_time_live")["by_provider_symbol"], "routes"
    )
    rows = []
    for identity, raw in routes.items():
        strategy, symbol = identity.split("|", maxsplit=1)
        performance = _mapping(raw, identity)
        rows.append(
            {
                "route": identity,
                "route_label": f"{_strategy_label(strategy)} | {symbol}",
                "closed_trades": int(performance["closed_trades"]),
                "net_pnl_usd": float(performance["net_pnl_usd"]),
                "profit_factor": performance["profit_factor"],
                "net_ex_largest_usd": performance[
                    "net_pnl_excluding_largest_winner_usd"
                ],
            }
        )
    return sorted(rows, key=lambda row: float(row["net_pnl_usd"]))


def _open_positions(checkpoint: JsonMap) -> list[JsonMap]:
    open_report = _mapping(
        _nested(checkpoint, "audit", "open_trade_reflections"), "open"
    )
    trades = _sequence(open_report["trades"], "open.trades")
    if int(open_report["open_lifecycles"]) != len(trades):
        raise ValueError("open lifecycle count does not reconcile")
    rows = []
    for raw in trades:
        trade = _mapping(raw, "trade")
        economics = _mapping(trade["marked_economics"], "economics")
        stop = _mapping(trade["protective_stop"], "stop")
        strategy = str(trade["strategy_id"])
        rows.append(
            {
                "position": f"{trade['symbol']} {str(trade['side']).upper()}",
                "strategy_label": _strategy_label(strategy),
                "marked_net_pnl_usd": economics["active_lifecycle_marked_net_pnl_usd"],
                "protection": f"stop {stop['oid']} @ {float(stop['trigger_price']):g}",
                "contract_note": "legacy HIP3 v1 freshness unresolved"
                if "hip3_breakout_pressure" in strategy
                else "protected v39 lifecycle",
            }
        )
    return rows


def _regime_rows(regime: JsonMap) -> list[JsonMap]:
    rows = []
    for horizon in ("5m", "15m", "30m", "60m"):
        primary = _mapping(
            _nested(regime, "horizons", horizon, "state_fields", "primary_regime"),
            "primary",
        )
        for sample in ("pooled", "episode_onsets", "episode_onset_clusters"):
            states = _mapping(primary[sample], sample)
            for state in ("TREND_UP", "TREND_DOWN"):
                metrics = _mapping(states[state], state)
                rows.append(
                    {
                        "horizon": horizon,
                        "series": f"{state.replace('TREND_', '').lower()} {sample.split('_')[-1]}",
                        "accuracy_pct": metrics["directional_accuracy_pct"],
                        "observations": metrics["observations"],
                    }
                )
    return rows


def _sources(paths: ReportPaths) -> list[JsonMap]:
    entries = (
        ("live-checkpoint", "Fresh live checkpoint", paths.checkpoint),
        ("v47-config", "v47 repaired configuration", paths.v47_config),
        ("v47-stress", "v47 route-aware friction stress", paths.v47_stress),
        ("hip3-parity", "HIP3 live/research freshness parity", paths.hip3_parity),
        ("hulk-validation", "BTC Hulk short validation", paths.hulk),
        ("hulk-holdout", "BTC Hulk pseudo-holdout", paths.hulk_holdout),
        ("hype-compression", "HYPE compression challenger", paths.hype),
        ("eth-range", "ETH Range context challenger", paths.eth_range),
        ("sol-range", "SOL Range exact audit", paths.sol_range),
        ("regime-forward", "Canonical regime forward accuracy", paths.regime),
        ("strategy-disposition", "Strategy diagnosis synthesis", paths.disposition),
    )
    sources = []
    for key, label, path in entries:
        portable = path.relative_to(Path.cwd())
        query_path = str(portable).replace("'", "''")
        reader = "read_text" if path.suffix == ".toml" else "read_json_auto"
        sources.append(
            {
                "id": key,
                "label": label,
                "path": str(portable),
                "query": {
                    "engine": "duckdb",
                    "sql": f"SELECT * FROM {reader}('{query_path}')",
                    "description": f"Loads {label}.",
                },
            }
        )
    return sources


def _datasets(inputs: JsonMap) -> JsonMap:
    checkpoint = _mapping(inputs["checkpoint"], "checkpoint")
    config = _mapping(inputs["v47_config"], "config")
    stress = _mapping(inputs["v47_stress"], "stress")
    parity = _mapping(inputs["hip3_parity"], "parity")
    attribution = _mapping(parity["closed_pnl_attribution"], "attribution")
    return {
        "current_run": [
            _performance_row(
                _mapping(_performance(checkpoint, "current_run")["total"], "current")
            )
        ],
        "all_time": [
            _performance_row(
                _mapping(_performance(checkpoint, "all_time_live")["total"], "all_time")
            )
        ],
        "all_time_routes": _all_time_routes(checkpoint),
        "defect_summary": [
            {
                "affected_closed_trades": attribution["affected_hip3_closed_trades"],
                "affected_net_pnl_usd": attribution["affected_hip3_net_pnl_usd"],
                "affected_loss_fraction": float(
                    attribution["affected_share_of_absolute_run_loss_pct"]
                )
                / 100.0,
            }
        ],
        "strategy_decisions": [
            _mapping(row, "decision")
            for row in _sequence(
                _mapping(inputs["disposition"], "disposition")["decisions"], "decisions"
            )
        ],
        "candidate_routes": candidate_routes(config, stress, _strategy_label),
        "candidate_capacity": [candidate_capacity(config, stress, "v47")],
        "candidate_slot_risk": candidate_slot_risk(stress),
        "open_positions": _open_positions(checkpoint),
        "regime_accuracy": _regime_rows(_mapping(inputs["regime"], "regime")),
    }


def build_report_artifact(paths: ReportPaths) -> JsonMap:
    """Build and reconcile one canonical portable-report artifact."""
    inputs: JsonMap = {
        "checkpoint": _load(paths.checkpoint),
        "v47_config": _mapping(
            tomllib.loads(paths.v47_config.read_text(encoding="utf-8")),
            str(paths.v47_config),
        ),
        "v47_stress": _load(paths.v47_stress),
        "hip3_parity": _load(paths.hip3_parity),
        "hulk": _load(paths.hulk),
        "hulk_holdout": _load(paths.hulk_holdout),
        "hype": _load(paths.hype),
        "eth_range": _load(paths.eth_range),
        "sol_range": _load(paths.sol_range),
        "regime": _load(paths.regime),
        "disposition": _load(paths.disposition),
    }
    _validate_accounting(_mapping(inputs["checkpoint"], "checkpoint"))
    _validate_inputs(inputs)
    generated = datetime.now(tz=UTC).isoformat()
    cutoff = str(_mapping(inputs["checkpoint"], "checkpoint")["generated_at_utc"])
    sources = _sources(paths)
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Hypervector Strategy Regression and v47 Repair Plan",
            "description": "Source-reconciled diagnosis of live defects, strategy evidence, exits, regime telemetry, and $5K successor risk.",
            "generatedAt": generated,
            "cards": report_cards(),
            "charts": report_charts(),
            "tables": report_tables(),
            "blocks": report_blocks(cutoff),
            "sources": sources,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated,
            "status": "ready",
            "datasets": _datasets(inputs),
        },
        "sources": sources,
    }


def build_parser() -> argparse.ArgumentParser:
    """Return the report-only command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    """Publish one immutable report artifact and print its path."""
    args = build_parser().parse_args()
    artifact = build_report_artifact(default_report_paths(args.root.resolve()))
    write_immutable_json(args.output, artifact)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
