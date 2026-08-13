"""Deterministic exposure accounting for the BTC specialist successor."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from pathlib import Path

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    StrategyProviderConfig,
    load_multi_asset_live_config,
)

_SHORT = "hulk_expansion_short_robust_v3"
_LONG = "liquidity_sweep_long_1h_stop60_v1"
_LONG_TARGET60 = "liquidity_sweep_long_1h_stop60_target60_v2"
_SHORT_EVIDENCE = Path(
    "data/logs/research/20260811_hulk_short_robust_v3_btc_forward_nominal.json"
)
_LONG_EVIDENCE = Path(
    "data/logs/research/"
    "hypervelocity_liquidity_sweep_long_forward_20260730T1200_"
    "20260811T2300_trade_through_v1.json"
)
_LONG_TARGET60_EVIDENCE = Path(
    "data/logs/research/bidirectional_cohort/"
    "btc_liquidity_sweep_taker_parity_20260811_v2.json"
)
_FEE_EVIDENCE = Path(
    "data/logs/research/bidirectional_cohort/"
    "v42_growth_5000_preflight_20260811T2245Z.json"
)


def build_btc_specialist_successor_risk(
    profile: Path,
    *,
    account_values_usd: Sequence[float],
    taker_fee_bps_per_side: float,
) -> dict[str, object]:
    """Build report-only stop/fee exposure at explicit account-value scenarios."""
    config = load_multi_asset_live_config(profile, mode="observe")
    account_values = _account_values(account_values_usd)
    fee_bps = _finite_positive(taker_fee_bps_per_side, "taker fee")
    _require_fee_evidence(fee_bps)
    short, long = _btc_providers(config)
    return {
        "schema_version": "btc_specialist_successor_risk_v1",
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "execution_authority": "none",
        "maximum_positions_capacity": config.maximum_positions,
        "actual_asset_slots": len(config.assets),
        "maximum_simultaneous_margin_fraction": sum(
            asset.margin_fraction for asset in config.assets
        ),
        "maximum_simultaneous_gross_account_multiple": sum(
            asset.margin_fraction * asset.leverage for asset in config.assets
        ),
        "evidence_state": _evidence_state(long),
        "repeatability_established": False,
        "fee_evidence": _fee_payload(fee_bps),
        "scenarios": [
            _scenario(config, short, long, account, fee_bps)
            for account in account_values
        ],
        "inputs": _inputs(profile, long),
        "risk_limitations": _limitations(long),
    }


def _btc_providers(
    config: MultiAssetLiveConfig,
) -> tuple[StrategyProviderConfig, StrategyProviderConfig]:
    providers = {provider.strategy_id: provider for provider in config.providers}
    long_ids = set((_LONG, _LONG_TARGET60)).intersection(providers)
    if _SHORT not in providers or len(long_ids) != 1:
        raise ValueError("BTC successor profile is missing an exact specialist")
    return providers[_SHORT], providers[long_ids.pop()]


def _scenario(
    config: MultiAssetLiveConfig,
    short: StrategyProviderConfig,
    long: StrategyProviderConfig,
    account: float,
    fee_bps: float,
) -> dict[str, object]:
    asset = next((row for row in config.assets if row.symbol == "BTC"), None)
    if asset is None:
        raise ValueError("BTC successor profile is missing the BTC asset")
    return {
        "account_value_usd": account,
        "btc_routes": [
            _short_risk(short, account, asset.leverage, fee_bps),
            _long_risk(long, account, asset.leverage, fee_bps),
        ],
    }


def _short_risk(
    provider: StrategyProviderConfig,
    account: float,
    leverage: float,
    fee_bps: float,
) -> dict[str, object]:
    sizing = provider.entry_sizing("BTC")
    execution = provider.execution
    if sizing is None or execution.maximum_stop_bps is None:
        raise ValueError("BTC short sizing or maximum stop is unavailable")
    notional = sizing.planned_notional(
        account_value_usd=account,
        leverage=leverage,
    )
    fees = _round_trip_fees(notional, fee_bps)
    maximum_stop = notional * execution.maximum_stop_bps / 10_000.0
    maximum_target = maximum_stop * _required(execution.target_r_multiple, "short R")
    return {
        "strategy_id": provider.strategy_id,
        "side": "short",
        "planned_notional_usd": notional,
        "round_trip_fee_usd": fees,
        "maximum_stop_bps": execution.maximum_stop_bps,
        "maximum_stop_loss_plus_round_trip_fees_usd": maximum_stop + fees,
        "maximum_stop_loss_fraction": (maximum_stop + fees) / account,
        "maximum_stop_net_target_usd": maximum_target - fees,
    }


def _long_risk(
    provider: StrategyProviderConfig,
    account: float,
    leverage: float,
    fee_bps: float,
) -> dict[str, object]:
    sizing = provider.entry_sizing("BTC")
    execution = provider.execution
    if sizing is None:
        raise ValueError("BTC long sizing is unavailable")
    notional = sizing.planned_notional(
        account_value_usd=account,
        leverage=leverage,
    )
    fees = _round_trip_fees(notional, fee_bps)
    stop_bps = _required(execution.stop_bps, "long stop")
    target_bps = _required(execution.target_bps, "long target")
    stop = notional * stop_bps / 10_000.0
    target = notional * target_bps / 10_000.0
    return {
        "strategy_id": provider.strategy_id,
        "side": "long",
        "planned_notional_usd": notional,
        "round_trip_fee_usd": fees,
        "stop_bps": stop_bps,
        "target_bps": target_bps,
        "stop_loss_plus_round_trip_fees_usd": stop + fees,
        "stop_loss_fraction": (stop + fees) / account,
        "net_target_usd": target - fees,
    }


def _account_values(values: Sequence[float]) -> tuple[float, ...]:
    output = tuple(_finite_positive(value, "account value") for value in values)
    if not output or len(set(output)) != len(output):
        raise ValueError("account values must be non-empty and unique")
    return output


def _round_trip_fees(notional: float, fee_bps: float) -> float:
    return notional * fee_bps * 2.0 / 10_000.0


def _require_fee_evidence(expected_bps: float) -> None:
    document = _mapping(json.loads(_FEE_EVIDENCE.read_text()), "fee evidence")
    assets = document.get("assets")
    if not isinstance(assets, list):
        raise ValueError("fee evidence assets must be a list")
    btc = next(
        (
            row
            for row in assets
            if isinstance(row, Mapping) and row.get("symbol") == "BTC"
        ),
        None,
    )
    venue = _mapping(btc.get("venue") if btc is not None else None, "BTC venue")
    observed = _finite_positive(venue.get("one_way_taker_fee_bps"), "BTC fee")
    if not math.isclose(observed, expected_bps, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("requested fee differs from frozen BTC venue evidence")


def _fee_payload(fee_bps: float) -> dict[str, object]:
    return {
        "one_way_taker_fee_bps": fee_bps,
        "source": str(_FEE_EVIDENCE),
        "limitation": "Point-in-time account fee evidence; recheck before every start.",
    }


def _inputs(
    profile: Path, long: StrategyProviderConfig
) -> dict[str, dict[str, object]]:
    long_evidence = (
        _LONG_TARGET60_EVIDENCE
        if long.strategy_id == _LONG_TARGET60
        else _LONG_EVIDENCE
    )
    return {
        name: _file_identity(path)
        for name, path in (
            ("generator", Path(__file__)),
            ("profile", profile),
            ("short_forward", _SHORT_EVIDENCE),
            ("long_forward", long_evidence),
            ("fee_preflight", _FEE_EVIDENCE),
        )
    }


def _evidence_state(long: StrategyProviderConfig) -> str:
    if long.strategy_id == _LONG_TARGET60:
        return "short_n1_long_taker_path_unresolved"
    return "two_distinct_forward_exact_n1_routes"


def _file_identity(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _limitations(long: StrategyProviderConfig) -> list[str]:
    evidence = (
        "BTC short has one exact forward event; corrected BTC long has six "
        "development signals, one unresolved path, and one forward event."
        if long.strategy_id == _LONG_TARGET60
        else "Each BTC side has one exact forward event; repeatability is unproven."
    )
    return [
        evidence,
        "Stop-market gap and latency can lose more than the configured stop distance.",
        "Funding and realized slippage are excluded from the simple route arithmetic.",
        "BTC side specialists share one asset slot and cannot be open simultaneously.",
    ]


def _required(value: float | None, label: str) -> float:
    if value is None:
        raise ValueError(f"{label} is unavailable")
    return _finite_positive(value, label)


def _finite_positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
