"""Evidence-bound design assessment for the inactive focused $5K v42 profile."""

from __future__ import annotations

import math
from typing import Mapping

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

_TARGET_EQUITY_USD = 5_000.0
_EXPECTED_ROUTES = frozenset(
    {
        ("hulk_expansion_bidirectional_tuned_v2", "BTC"),
        ("hype_breakout_compression_pullback_bidirectional_v1", "HYPE"),
        ("hip3_breakout_pressure_sp500_spcx_bidirectional_v1", "xyz:SP500"),
    }
)


def build_v42_successor_design(
    *,
    config: MultiAssetLiveConfig,
    v41_readiness: Mapping[str, object],
    current_checkpoint: Mapping[str, object],
    hype_exit_evidence: Mapping[str, object],
) -> dict[str, object]:
    """Build a report-only v42 design from exact sizing and live-prefix sources."""
    _validate_config(config)
    v41_risk = _validate_v41(v41_readiness)
    live_prefix = _live_prefix(current_checkpoint)
    hype_disposition = _validate_hype_exit(hype_exit_evidence)
    sizing = _sizing(config)
    risk = _focused_risk(v41_risk, config.symbols)
    return {
        "schema_version": 1,
        "mode": "focused_growth_5000_v42_design_report_only",
        "contract": _contract(),
        "candidate": _candidate(config),
        "capacity": _capacity(config),
        "sizing": sizing,
        "risk": risk,
        "live_prefix": live_prefix,
        "route_evidence": _route_evidence(hype_disposition),
        "assessment": _assessment(current_checkpoint),
        "limitations": _limitations(),
    }


def _validate_config(config: MultiAssetLiveConfig) -> None:
    if (
        config.profile_id
        != "multi_asset_bidirectional_focused_growth_5000_candidate_v42"
    ):
        raise ValueError("v42 candidate profile identity is wrong")
    if config.network != "mainnet" or config.margin_mode != "isolated":
        raise ValueError("v42 candidate requires isolated mainnet execution")
    if set(config.symbols) != {"BTC", "HYPE", "xyz:SP500"}:
        raise ValueError("v42 candidate asset roster is wrong")
    if config.executable_provider_symbols != _EXPECTED_ROUTES:
        raise ValueError("v42 candidate provider-symbol routes are wrong")
    expected_directions = {
        (provider, symbol, side)
        for provider, symbol in _EXPECTED_ROUTES
        for side in ("long", "short")
    }
    if config.executable_provider_directions != expected_directions:
        raise ValueError("v42 candidate must retain both directions per route")


def _validate_v41(source: Mapping[str, object]) -> Mapping[str, object]:
    candidate = _mapping(source.get("candidate"), "v41 candidate")
    if candidate.get("profile_id") != (
        "multi_asset_bidirectional_hype_compression_growth_5000_"
        "risk_normalized_candidate_v41"
    ):
        raise ValueError("v41 source profile identity is wrong")
    assessment = _mapping(source.get("assessment"), "v41 assessment")
    if assessment.get("sizing_technically_coherent") is not True:
        raise ValueError("v41 source sizing is not technically coherent")
    risk = _mapping(source.get("risk"), "v41 risk")
    values = _mapping(risk.get("by_asset_p99_loss_usd"), "v41 asset risk")
    for symbol in ("BTC", "HYPE", "xyz:SP500"):
        _number(values.get(symbol), f"v41 {symbol} p99 loss")
    return values


def _validate_hype_exit(source: Mapping[str, object]) -> str:
    challenger = _mapping(
        source.get("compression_exit_challenger"),
        "HYPE compression exit challenger",
    )
    disposition = challenger.get("disposition")
    if disposition != "retain_control_exit":
        raise ValueError("HYPE exit disposition must retain the control")
    development = _mapping(
        challenger.get("development_acceptance"),
        "HYPE development acceptance",
    )
    if development.get("passed") is not False:
        raise ValueError("HYPE exit challenger development must remain rejected")
    return str(disposition)


def _live_prefix(checkpoint: Mapping[str, object]) -> dict[str, object]:
    generation = _mapping(
        checkpoint.get("configuration_generation"),
        "checkpoint configuration generation",
    )
    if generation.get("matches_runtime") is not True:
        raise ValueError("current checkpoint does not match the runtime")
    audit = _mapping(checkpoint.get("audit"), "checkpoint audit")
    reflections = _mapping(audit.get("trade_reflections"), "trade reflections")
    performance = _mapping(reflections.get("performance"), "trade performance")
    current_run = _mapping(performance.get("current_run"), "current run")
    total = _mapping(current_run.get("total"), "current run total")
    opens = _mapping(audit.get("open_trade_reflections"), "open reflections")
    return {
        "run_id": current_run.get("run_id"),
        "closed_trades": _integer(total.get("closed_trades"), "closed trades"),
        "wins": _integer(total.get("wins"), "wins"),
        "losses": _integer(total.get("losses"), "losses"),
        "net_pnl_usd": _number(total.get("net_pnl_usd"), "current net PnL"),
        "open_lifecycles": _integer(opens.get("open_lifecycles"), "open lifecycles"),
        "source_profile_fingerprint": generation.get("current_profile_fingerprint"),
    }


def _sizing(config: MultiAssetLiveConfig) -> dict[str, object]:
    notionals = {
        asset.symbol: _TARGET_EQUITY_USD * asset.margin_fraction * asset.leverage
        for asset in config.assets
    }
    margin_fraction = sum(asset.margin_fraction for asset in config.assets)
    return {
        "target_equity_usd": _TARGET_EQUITY_USD,
        "by_asset_notional_usd": notionals,
        "gross_notional_usd": sum(notionals.values()),
        "initial_margin_usd": _TARGET_EQUITY_USD * margin_fraction,
        "maximum_margin_fraction": margin_fraction,
        "gross_account_exposure_multiple": sum(notionals.values()) / _TARGET_EQUITY_USD,
        "removed_asset_risk_policy": "leave_unused_no_redistribution",
    }


def _focused_risk(
    by_asset: Mapping[str, object],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    values = {
        symbol: _number(by_asset[symbol], f"{symbol} p99 loss") for symbol in symbols
    }
    total = sum(values.values())
    return {
        "source": "v41_exact_repriced_visible_depth_p99_subset",
        "by_asset_p99_loss_usd": values,
        "p99_stop_wave_loss_usd": total,
        "p99_stop_wave_loss_pct_equity": total / _TARGET_EQUITY_USD * 100.0,
        "scope": "deterministic_simultaneous_stop_wave_not_worst_case",
    }


def _candidate(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "network": config.network,
        "margin_mode": config.margin_mode,
        "routes": [
            {"strategy_id": provider, "symbol": symbol, "sides": ["long", "short"]}
            for provider, symbol in sorted(_EXPECTED_ROUTES)
        ],
    }


def _capacity(config: MultiAssetLiveConfig) -> dict[str, int]:
    assets = len(config.assets)
    return {
        "account_position_cap": config.maximum_positions,
        "configured_assets": assets,
        "maximum_simultaneous_positions": min(config.maximum_positions, assets),
        "unused_account_slots": config.maximum_positions - assets,
    }


def _route_evidence(hype_disposition: str) -> dict[str, object]:
    return {
        "BTC": {
            "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
            "status": "contradictory_research_not_proven_edge",
        },
        "HYPE": {
            "strategy_id": "hype_breakout_compression_pullback_bidirectional_v1",
            "status": "fold_unstable_short_confirmation",
            "exit_disposition": hype_disposition,
        },
        "xyz:SP500": {
            "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
            "status": "approximate_positive_exact_lifecycle_open",
        },
    }


def _assessment(checkpoint: Mapping[str, object]) -> dict[str, object]:
    lifecycle = _mapping(checkpoint.get("lifecycle"), "checkpoint lifecycle")
    flat = lifecycle.get("all_assets_terminal") is True
    return {
        "removed_risk_redistributed": False,
        "sizing_technically_coherent": True,
        "route_edge_established": False,
        "profit_optimality_proven": False,
        "flat_boundary_ready": flat,
        "fresh_v42_preflight_present": False,
        "transition_ready_now": False,
        "state": "inactive_candidate_waiting_for_resolved_v39_and_fresh_preflight",
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_restart": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }


def _limitations() -> list[str]:
    return [
        "v42 route edge is not established by sparse or contradictory evidence",
        "the v39 open episode can still update route disposition",
        "visible-depth p99 is not a gap-through or worst-case loss guarantee",
        "a fresh flat and order-free v42 preflight is mandatory before authorization",
        "three configured assets leave seven account slots intentionally unused",
    ]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{label} must be finite")
    return numeric


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
