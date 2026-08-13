#!/usr/bin/env python3
"""Build a source-reconciled v39-to-v45 growth-readiness report artifact."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
from typing import cast

from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.v39_v45_growth_report_manifest import (
    report_blocks,
    report_cards,
    report_charts,
    report_tables,
)

JsonMap = dict[str, object]


@dataclass(frozen=True)
class ReportPaths:
    """Exact local evidence paths used by the report."""

    checkpoint: Path
    route_review: Path
    regime: Path
    v45_risk: Path
    v45_stress: Path
    variable_sizing: Path


def default_report_paths(root: Path) -> ReportPaths:
    """Return the frozen default evidence paths below one repository root."""
    research = root / "data/logs/research/bidirectional_cohort"
    return ReportPaths(
        checkpoint=root / "data/runtime/bidirectional_cohort/latest_checkpoint.json",
        route_review=research / "v39_route_portfolio_review_20260812T112929Z_v1.json",
        regime=research / "v39_regime_forward_accuracy_20260812T112929Z_v1.json",
        v45_risk=research / "v45_btc_specialist_successor_risk_20260812_v1.json",
        v45_stress=research / "v45_growth_sizing_stress_20260812_v2.json",
        variable_sizing=root / "data/runtime/research/v45_variable_sizing_latest.json",
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


def _close(value: float, expected: float, label: str) -> None:
    if not math.isclose(value, expected, abs_tol=1e-9):
        raise ValueError(f"{label} does not reconcile: {value} != {expected}")


def _performance(checkpoint: JsonMap, scope: str) -> JsonMap:
    return _mapping(
        _nested(checkpoint, "audit", "trade_reflections", "performance", scope),
        f"performance.{scope}",
    )


def _validate_accounting(checkpoint: JsonMap, route_review: JsonMap) -> None:
    all_time = _performance(checkpoint, "all_time_live")
    current = _performance(checkpoint, "current_run")
    total = _mapping(all_time["total"], "all_time.total")
    routes = _mapping(all_time["by_provider_symbol"], "all_time.routes")
    route_rows = [_mapping(value, "all_time.route") for value in routes.values()]
    closed = sum(int(row["closed_trades"]) for row in route_rows)
    net = sum(float(row["net_pnl_usd"]) for row in route_rows)
    if closed != int(total["closed_trades"]):
        raise ValueError("all-time provider trade count does not reconcile")
    _close(net, float(total["net_pnl_usd"]), "all-time provider net PnL")
    archive = _mapping(
        _nested(checkpoint, "audit", "portfolio_archive", "coverage"), "archive"
    )
    if int(archive["closed_orders"]) != closed or archive["complete"] is not True:
        raise ValueError("portfolio archive coverage is incomplete")
    summary = _mapping(route_review["summary"], "route_review.summary")
    current_total = _mapping(current["total"], "current.total")
    if int(summary["current_run_closed_trades"]) != int(current_total["closed_trades"]):
        raise ValueError("route review current trade count does not reconcile")
    _close(
        float(summary["current_run_net_pnl_usd"]),
        float(current_total["net_pnl_usd"]),
        "current-run net PnL",
    )


def _performance_row(performance: JsonMap) -> JsonMap:
    return {
        "closed_trades": int(performance["closed_trades"]),
        "wins": int(performance["wins"]),
        "losses": int(performance["losses"]),
        "win_rate_fraction": float(performance["win_rate_pct"]) / 100.0,
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
        "eth_breakout_precompression_pullback_bidirectional_v1": "ETH Pullback",
        "hip3_breakout_pressure_sndk_gold_brent_bidirectional_v1": "HIP3 Pressure Commodity",
        "hip3_breakout_pressure_sp500_spcx_bidirectional_v1": "HIP3 Pressure Index",
        "hip3_swing_ha_sndk_gold_brent_bidirectional_v1": "HIP3 Swing Commodity",
        "hip3_swing_ha_sp500_spcx_bidirectional_v2": "HIP3 Swing Index",
        "hulk_expansion_bidirectional_tuned_v2": "Hulk Expansion",
        "hulk_expansion_short_robust_v3": "Hulk Short v3",
        "hype_breakout_compression_pullback_bidirectional_v1": "HYPE Compression",
        "hype_breakout_onset_bidirectional_v1": "Breakout Onset",
        "hypervelocity_source_follow_bidirectional_5m_v1": "HV Source 5m",
        "liquidity_sweep_long_1h_stop60_target60_v2": "BTC Sweep Long",
        "range_onset_bidirectional_v1": "Range Onset",
    }
    return aliases.get(strategy, strategy)


def _all_time_routes(checkpoint: JsonMap) -> list[JsonMap]:
    routes = _mapping(
        _performance(checkpoint, "all_time_live")["by_provider_symbol"], "routes"
    )
    rows = []
    for identity, raw in routes.items():
        performance = _mapping(raw, identity)
        strategy, symbol = identity.split("|", maxsplit=1)
        row = _performance_row(performance)
        row.update(
            {
                "route": identity,
                "route_label": f"{_strategy_label(strategy)} | {symbol}",
                "strategy": strategy,
                "symbol": symbol,
            }
        )
        rows.append(row)
    return sorted(rows, key=lambda row: float(row["net_pnl_usd"]))


def _current_routes(route_review: JsonMap) -> list[JsonMap]:
    rows = []
    for identity, raw in _mapping(
        route_review["routes"], "route_review.routes"
    ).items():
        route = _mapping(raw, identity)
        closed = _mapping(_nested(route, "current_run", "closed"), "current.closed")
        strategy, symbol = identity.split("|", maxsplit=1)
        rows.append(
            {
                "route": identity,
                "route_label": f"{_strategy_label(strategy)} | {symbol}",
                "evaluations": int(_nested(route, "current_run", "evaluations")),
                "eligible": int(_nested(route, "current_run", "eligible_evaluations")),
                "closed_trades": int(closed["closed_trades"]),
                "net_pnl_usd": float(closed["net_pnl_usd"]),
                "evidence_state": str(route["evidence_state"]),
                "v45_action": "retained/replaced"
                if "sp500_spcx" in identity
                else "removed",
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
        trade = _mapping(raw, "open.trade")
        economics = _mapping(trade["marked_economics"], "marked_economics")
        stop = _mapping(trade["protective_stop"], "protective_stop")
        plan = _mapping(trade["exit_plan"], "exit_plan")
        rows.append(
            {
                "symbol": trade["symbol"],
                "strategy": trade["strategy_id"],
                "strategy_label": _strategy_label(str(trade["strategy_id"])),
                "side": trade["side"],
                "position_label": f"{trade['symbol']} {str(trade['side']).upper()}",
                "marked_net_pnl_usd": economics["active_lifecycle_marked_net_pnl_usd"],
                "liquidation_distance_pct": economics["liquidation_distance_pct"],
                "stop_oid": stop["oid"],
                "stop_price": stop["trigger_price"],
                "protection": f"stop {stop['oid']} / liq {float(economics['liquidation_distance_pct']):.1f}%",
                "maximum_hold_policy": plan["maximum_hold_policy"],
            }
        )
    return rows


def _regime_rows(regime: JsonMap) -> list[JsonMap]:
    rows = []
    sample_labels = {"pooled": "pool", "episode_onsets": "episodes"}
    state_labels = {"TREND_UP": "up", "TREND_DOWN": "down"}
    for horizon in ("5m", "15m", "30m", "60m"):
        primary = _mapping(
            _nested(regime, "horizons", horizon, "state_fields", "primary_regime"),
            "primary",
        )
        for sample in ("pooled", "episode_onsets"):
            states = _mapping(primary[sample], sample)
            for state in ("TREND_UP", "TREND_DOWN"):
                metrics = _mapping(states[state], state)
                rows.append(
                    {
                        "horizon": horizon,
                        "series": f"{state_labels[state]} {sample_labels[sample]}",
                        "state": state,
                        "sample": sample,
                        "accuracy_pct": metrics["directional_accuracy_pct"],
                        "observations": metrics["observations"],
                    }
                )
    return rows


def _scenario(stress: JsonMap, account_value: float) -> JsonMap:
    for raw in _sequence(stress["scenarios"], "stress.scenarios"):
        scenario = _mapping(raw, "stress.scenario")
        if math.isclose(float(scenario["account_value_usd"]), account_value):
            return scenario
    raise ValueError(f"v45 stress lacks ${account_value:g} scenario")


def _v45_routes(stress: JsonMap) -> list[JsonMap]:
    slots = _mapping(_scenario(stress, 5_000.0)["asset_slots"], "asset_slots")
    rows = []
    for asset, slot_raw in slots.items():
        slot = _mapping(slot_raw, asset)
        for route_raw in _sequence(slot["routes"], f"{asset}.routes"):
            route = _mapping(route_raw, f"{asset}.route")
            target = route["target_bps"]
            rows.append(
                {
                    "asset": asset,
                    "side": "/".join(cast(list[str], route["sides"])),
                    "route": route["strategy_id"],
                    "route_label": _strategy_label(str(route["strategy_id"])),
                    "leverage": 5.0,
                    "margin_pct": float(route["margin_fraction"]) * 100.0,
                    "planned_notional_usd": route["planned_notional_usd"],
                    "stop_bps": route["stop_bps"],
                    "target_policy": f"{float(target):g} bps"
                    if target is not None
                    else "strategy/opposite intent",
                    "risk_contract": f"stop {float(route['stop_bps']):g} / target {float(target):g} bps"
                    if target is not None
                    else f"stop {float(route['stop_bps']):g} / strategy exit",
                    "p99_stop_loss_usd": route["stacked_p99_stop_loss_usd"],
                    "target_net_usd": route.get(
                        "stacked_target_net_before_funding_usd"
                    ),
                }
            )
    return rows


def _slot_risk(stress: JsonMap) -> list[JsonMap]:
    slots = _mapping(_scenario(stress, 5_000.0)["asset_slots"], "asset_slots")
    return [
        {
            "asset": asset,
            "p99_stop_loss_usd": _mapping(raw, asset)["stacked_p99_slot_loss_usd"],
        }
        for asset, raw in slots.items()
    ]


def _sources(paths: ReportPaths) -> list[JsonMap]:
    entries = (
        ("v39-checkpoint", "Fresh v39 live checkpoint", paths.checkpoint),
        ("v39-routes", "v39 exact route review", paths.route_review),
        ("v39-regime", "v39 canonical regime accuracy", paths.regime),
        ("v45-risk", "v45 successor risk contract", paths.v45_risk),
        ("v45-stress", "v45 route-aware friction stress", paths.v45_stress),
        ("v45-sizing", "v45 adaptive sizing observer", paths.variable_sizing),
    )
    sources = []
    for key, label, path in entries:
        portable_path = path.relative_to(Path.cwd())
        sql_path = str(portable_path).replace("'", "''")
        sources.append(
            {
                "id": key,
                "label": label,
                "path": str(portable_path),
                "query": {
                    "engine": "duckdb",
                    "sql": f"SELECT * FROM read_json_auto('{sql_path}')",
                    "description": f"Loads the exact local JSON source for {label}.",
                },
            }
        )
    return sources


def _datasets(inputs: JsonMap) -> JsonMap:
    checkpoint = _mapping(inputs["checkpoint"], "checkpoint")
    route_review = _mapping(inputs["route_review"], "route_review")
    stress = _mapping(inputs["v45_stress"], "v45_stress")
    variable = _mapping(inputs["variable_sizing"], "variable_sizing")
    current = _performance_row(
        _mapping(_performance(checkpoint, "current_run")["total"], "current")
    )
    all_time = _performance_row(
        _mapping(_performance(checkpoint, "all_time_live")["total"], "all_time")
    )
    scenario = _scenario(stress, 5_000.0)
    return {
        "current_run": [current],
        "all_time": [all_time],
        "all_time_routes": _all_time_routes(checkpoint),
        "current_routes": _current_routes(route_review),
        "open_positions": _open_positions(checkpoint),
        "regime_accuracy": _regime_rows(_mapping(inputs["regime"], "regime")),
        "v45_routes": _v45_routes(stress),
        "v45_slot_risk": _slot_risk(stress),
        "v45_capacity": [
            {
                "actual_asset_slots": 3,
                "maximum_positions_capacity": 10,
                "p99_stop_wave_usd": scenario["stacked_p99_stop_wave_loss_usd"],
                "p99_stop_wave_fraction": float(
                    scenario["stacked_p99_stop_wave_loss_pct_equity"]
                )
                / 100.0,
            }
        ],
        "v45_policy": [
            {
                "leverage_policy": "fixed_5x",
                "sizing_policy": "adaptive_notional_only",
                "candidate_tiers": "0.75x/1.00x/1.25x",
                "regime_is_sizing_score": False,
            }
        ],
        "variable_sizing_status": [
            {
                "evaluations": variable["evaluations"],
                "eligible_candidates": variable["eligible_candidates"],
                "selected_tier_policy": variable["selected_tier_policy"],
                "tier_authority": variable["tier_authority"],
                "execution_authority": variable["execution_authority"],
            }
        ],
    }


def build_report_artifact(paths: ReportPaths) -> JsonMap:
    """Build and reconcile one canonical portable-report artifact."""
    inputs = {
        "checkpoint": _load(paths.checkpoint),
        "route_review": _load(paths.route_review),
        "regime": _load(paths.regime),
        "v45_risk": _load(paths.v45_risk),
        "v45_stress": _load(paths.v45_stress),
        "variable_sizing": _load(paths.variable_sizing),
    }
    _validate_accounting(
        _mapping(inputs["checkpoint"], "checkpoint"),
        _mapping(inputs["route_review"], "route_review"),
    )
    generated = datetime.now(tz=UTC).isoformat()
    sources = _sources(paths)
    manifest = {
        "version": 1,
        "surface": "report",
        "title": "Hypervector v39 → v45 $5,000 Growth Readiness",
        "description": "Reconciled live strategy, regime, friction, exit, and adaptive-sizing evidence.",
        "generatedAt": generated,
        "cards": report_cards(),
        "charts": report_charts(),
        "tables": report_tables(),
        "blocks": report_blocks(
            str(_mapping(inputs["checkpoint"], "checkpoint")["generated_at_utc"])
        ),
        "sources": sources,
    }
    artifact = {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated,
            "status": "ready",
            "datasets": _datasets(inputs),
        },
        "sources": sources,
    }
    if "v44" in json.dumps(artifact).lower():
        raise ValueError("stale v44 identity leaked into v45 report")
    return artifact


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only command parser."""
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
