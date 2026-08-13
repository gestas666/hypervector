"""Source-bound technical readiness assessment for the $5K v41 successor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import math

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig

Record = Mapping[str, object]

_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_growth_5000_"
    "risk_normalized_candidate_v41"
)
_ACTIVE_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39"
)
_TARGET_EQUITY_USD = 5_000.0


def build_v41_successor_readiness(
    *,
    config: MultiAssetLiveConfig,
    preflight: Record,
    reprice: Record,
    concentration: Record,
    return_panel: Record,
    v39_review: Record,
    config_source_sha256: str | None = None,
) -> dict[str, object]:
    """Reconcile technical sizing and explicitly withhold profit optimality."""
    config_notionals = _config_notionals(config)
    config_digest = config_source_sha256 or config_sha256(config)
    _require_preflight(config, preflight, config_notionals)
    asset_risk = _require_reprice(reprice, config_notionals)
    clusters = _require_concentration(config, concentration, asset_risk, config_digest)
    _require_return_panel(config, return_panel, config_digest)
    current_evidence = _require_v39_review(preflight, v39_review)
    portfolio = _mapping(preflight.get("portfolio"), "preflight portfolio")
    comparison = _mapping(reprice.get("portfolio_comparison"), "comparison")
    repriced = _mapping(comparison.get("repriced_candidate"), "repriced candidate")
    return {
        "schema_version": "v41_successor_readiness_v1",
        "mode": "report_only_successor_readiness",
        "contract": _contract(),
        "candidate": _candidate(config),
        "capacity": _capacity(config),
        "sizing": _sizing(config, config_notionals),
        "risk": _risk(repriced, clusters, return_panel, asset_risk),
        "current_v39_evidence": current_evidence,
        "assessment": _assessment(portfolio),
        "transition": _transition(portfolio),
        "limitations": _limitations(),
    }


def _require_preflight(
    config: MultiAssetLiveConfig,
    preflight: Record,
    notionals: Record,
) -> None:
    identity = _mapping(preflight.get("identity"), "preflight identity")
    expected = (config.profile_id, config.profile_fingerprint)
    actual = (
        identity.get("candidate_profile_id"),
        identity.get("candidate_profile_fingerprint"),
    )
    if actual != expected:
        raise ValueError("preflight candidate identity does not match v41 config")
    authority = _mapping(preflight.get("authority"), "preflight authority")
    if authority.get("execution_authority") != "none":
        raise ValueError("preflight unexpectedly has execution authority")
    if authority.get("execution_client_constructed") is not False:
        raise ValueError("preflight constructed an execution client")
    portfolio = _mapping(preflight.get("portfolio"), "preflight portfolio")
    if portfolio.get("sizing_technically_ready") is not True:
        raise ValueError("preflight sizing is not technically ready")
    if portfolio.get("ledger_reconciled") is not True:
        raise ValueError("preflight ledger is not reconciled")
    _require_asset_notionals(preflight, notionals)


def _require_asset_notionals(preflight: Record, notionals: Record) -> None:
    rows = _sequence(preflight.get("assets"), "preflight assets")
    observed: dict[str, float] = {}
    for value in rows:
        row = _mapping(value, "preflight asset")
        symbol = _text(row.get("symbol"), "preflight symbol")
        sizing = _mapping(row.get("sizing"), f"{symbol} sizing")
        observed[symbol] = _number(
            sizing.get("planned_notional_usd"), f"{symbol} asset notional"
        )
        if row.get("sizing_technically_ready") is not True:
            raise ValueError(f"{symbol} asset sizing is not technically ready")
    if set(observed) != set(notionals):
        raise ValueError("preflight asset coverage does not match v41")
    for symbol, expected in notionals.items():
        if not math.isclose(observed[symbol], _number(expected, symbol), abs_tol=1e-9):
            raise ValueError(f"{symbol} asset notional does not match v41")


def _require_reprice(reprice: Record, notionals: Record) -> dict[str, float]:
    _require_report_contract(reprice, "repricing")
    if reprice.get("exact_notional_repricing_complete") is not True:
        raise ValueError("exact notional repricing is incomplete")
    rows = _mapping(reprice.get("by_asset"), "repriced assets")
    if set(rows) != set(notionals):
        raise ValueError("repriced asset coverage does not match v41")
    losses: dict[str, float] = {}
    for symbol, expected in notionals.items():
        row = _mapping(rows[symbol], f"repriced {symbol}")
        actual = _number(row.get("candidate_notional_usd"), "candidate notional")
        if not math.isclose(actual, _number(expected, symbol), abs_tol=1e-9):
            raise ValueError(f"{symbol} repriced asset notional does not match v41")
        losses[symbol] = _number(row.get("repriced_p99_loss_usd"), "p99 loss")
    return losses


def _require_concentration(
    config: MultiAssetLiveConfig,
    concentration: Record,
    asset_risk: Record,
    config_digest: str,
) -> list[dict[str, object]]:
    _require_report_contract(concentration, "concentration")
    _require_candidate_identity(config, concentration, "concentration")
    _require_evidence_config_hash(config_digest, concentration, "concentration")
    rows = _sequence(concentration.get("clusters"), "concentration clusters")
    clusters = [dict(_mapping(row, "concentration cluster")) for row in rows]
    cluster_total = sum(
        _number(row.get("p99_loss_usd"), "cluster loss") for row in rows
    )
    asset_total = sum(_number(value, "asset loss") for value in asset_risk.values())
    if not math.isclose(cluster_total, asset_total, abs_tol=1e-9):
        raise ValueError("provider family concentration does not reconcile")
    return clusters


def _require_return_panel(
    config: MultiAssetLiveConfig, panel: Record, config_digest: str
) -> None:
    _require_report_contract(panel, "return panel")
    _require_candidate_identity(config, panel, "return panel")
    _require_evidence_config_hash(config_digest, panel, "return panel")
    if panel.get("covariance_weighting_status") != "withheld":
        raise ValueError("return panel unexpectedly generated covariance weights")
    if _integer(panel.get("common_timestamp_count"), "common timestamps") != 0:
        raise ValueError(
            "v41 common return coverage changed; rerun allocation research"
        )


def _require_v39_review(preflight: Record, review: Record) -> dict[str, object]:
    _require_report_contract(review, "v39 review")
    source = _mapping(review.get("source"), "v39 review source")
    identity = _mapping(preflight.get("identity"), "preflight identity")
    actual = (source.get("profile_id"), source.get("profile_fingerprint"))
    expected = (
        identity.get("active_profile_id"),
        identity.get("active_profile_fingerprint"),
    )
    if actual != expected or actual[0] != _ACTIVE_PROFILE_ID:
        raise ValueError("v39 review identity does not match active preflight")
    summary = _mapping(review.get("summary"), "v39 review summary")
    challengers = _mapping(review.get("causal_challenger_program"), "challengers")
    return {
        "run_id": source.get("run_id"),
        "eligible_evaluations": summary.get("current_run_eligible_evaluations"),
        "closed_lifecycles": summary.get("current_run_closed_trades"),
        "open_lifecycles": summary.get("routes_with_open_positions"),
        "net_pnl_usd": summary.get("current_run_net_pnl_usd"),
        "model_fit_now": _mapping(challengers.get("assessment"), "assessment").get(
            "model_fit_now"
        ),
        "scope": "current_v39_exact_evidence_not_v41_edge_proof",
    }


def _require_report_contract(report: Record, label: str) -> None:
    contract = _mapping(report.get("contract"), f"{label} contract")
    required = {
        "report_only": True,
        "execution_authority": "none",
        "performance_gate": False,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError(f"{label} contract is not report-only and ungated")


def _require_candidate_identity(
    config: MultiAssetLiveConfig, report: Record, label: str
) -> None:
    identity = _mapping(report.get("candidate_profile"), f"{label} profile")
    if (
        identity.get("profile_id") != config.profile_id
        or identity.get("profile_fingerprint") != config.profile_fingerprint
    ):
        raise ValueError(f"{label} candidate identity does not match v41")


def _require_evidence_config_hash(
    config_digest: str, report: Record, label: str
) -> None:
    evidence = _mapping(report.get("evidence"), f"{label} evidence")
    source = _mapping(evidence.get("config"), f"{label} config evidence")
    if source.get("sha256") != config_digest:
        raise ValueError(f"{label} config hash does not match v41")


def _config_notionals(config: MultiAssetLiveConfig) -> dict[str, float]:
    if config.profile_id != _PROFILE_ID:
        raise ValueError("successor readiness requires the exact v41 profile")
    if config.network != "mainnet" or config.margin_mode != "isolated":
        raise ValueError("v41 must use isolated margin on mainnet")
    return {
        asset.symbol: _TARGET_EQUITY_USD * asset.margin_fraction * asset.leverage
        for asset in config.assets
    }


def _candidate(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "network": config.network,
        "margin_mode": config.margin_mode,
        "target_equity_usd": _TARGET_EQUITY_USD,
    }


def _capacity(config: MultiAssetLiveConfig) -> dict[str, int]:
    count = len(config.assets)
    return {
        "account_position_cap": config.maximum_positions,
        "configured_assets": count,
        "maximum_simultaneous_positions": min(count, config.maximum_positions),
        "unused_account_slots": max(config.maximum_positions - count, 0),
    }


def _sizing(config: MultiAssetLiveConfig, notionals: Record) -> dict[str, object]:
    margin = sum(asset.margin_fraction for asset in config.assets)
    return {
        "objective": "equalize_exact_repriced_venue_p99_stop_wave_loss_by_asset",
        "maximum_margin_fraction": margin,
        "initial_margin_usd": _TARGET_EQUITY_USD * margin,
        "gross_notional_usd": sum(
            _number(value, "notional") for value in notionals.values()
        ),
        "gross_account_exposure_multiple": sum(
            _number(value, "notional") for value in notionals.values()
        )
        / _TARGET_EQUITY_USD,
        "by_asset_notional_usd": dict(notionals),
        "performance_weighted": False,
    }


def _risk(
    repriced: Record,
    clusters: Sequence[Record],
    panel: Record,
    asset_risk: Record,
) -> dict[str, object]:
    return {
        "p50_stop_wave_loss_usd": repriced.get("p50_stop_wave_loss_usd"),
        "p90_stop_wave_loss_usd": repriced.get("p90_stop_wave_loss_usd"),
        "p99_stop_wave_loss_usd": repriced.get("p99_stop_wave_loss_usd"),
        "p99_stop_wave_loss_pct_equity": _number(
            repriced.get("p99_stop_wave_loss_usd"), "p99 loss"
        )
        / _TARGET_EQUITY_USD
        * 100.0,
        "minimum_visible_depth_complete_rate": repriced.get(
            "minimum_visible_depth_complete_rate"
        ),
        "by_asset_p99_loss_usd": dict(asset_risk),
        "provider_family_clusters": [dict(row) for row in clusters],
        "covariance_weighting_status": panel.get("covariance_weighting_status"),
        "common_return_timestamps": panel.get("common_timestamp_count"),
        "scope": "deterministic_simultaneous_stop_wave_not_a_worst_case_probability",
    }


def _assessment(portfolio: Record) -> dict[str, object]:
    return {
        "sizing_technically_coherent": True,
        "profit_optimality_proven": False,
        "route_edge_established": False,
        "transition_ready_now": portfolio.get(
            "technically_ready_for_profile_transition"
        ),
        "state": "venue_risk_normalized_successor_pending_live_evidence_and_flat_boundary",
        "recommended_live_change_now": False,
    }


def _transition(portfolio: Record) -> dict[str, object]:
    return {
        "blocking_assets_at_preflight": list(
            _sequence(portfolio.get("transition_blocking_assets"), "blocking assets")
        ),
        "requires_flat_and_no_owned_orders": True,
        "requires_fresh_boundary_preflight": True,
        "requires_prestart_backup": True,
        "requires_poststart_checkpoint_and_tui_acceptance": True,
        "rollback_only_when_flat_and_order_free": True,
        "hot_reload_allowed": False,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "automatic_sizing_change": False,
        "automatic_strategy_change": False,
        "balance_gate": False,
        "performance_gate": False,
        "trade_count_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "v41 route expectancy is not established by v39 mixed or sparse closes",
        "p99 stop-wave loss is deterministic sensitivity, not a worst-case guarantee",
        "gap-through stops, latency, and future depth can exceed modeled losses",
        "cross-asset covariance is withheld because synchronized coverage is absent",
        "two account slots are unused because only eight assets are configured",
        "a fresh flat-boundary preflight is required before any separately authorized start",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def config_sha256(config: MultiAssetLiveConfig) -> str:
    """Return the exact candidate configuration file digest."""
    return sha256(config.source_path.read_bytes()).hexdigest()
