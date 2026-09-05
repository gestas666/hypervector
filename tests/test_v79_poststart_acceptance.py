"""Post-start monitoring acceptance for the exact V79 live cohort."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_cohort_payloads import (
    asset_config_payload,
    provider_config_payload,
)
from hypervector.research.cohort_configuration_generation import (
    configuration_generation_evidence,
    load_configuration_expectation,
)
from hypervector.research.cohort_friction_contracts import runtime_contract
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)
from hypervector.research.v79_checkpoint_acceptance import (
    attach_v79_poststart_acceptance,
)
from hypervector.research.seven_asset_checkpoint_acceptance import (
    attach_seven_asset_poststart_acceptance,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_seven_asset_all_active_v79.toml")
_V80_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_entry_ioc_hardened_v80.toml"
)
_V85_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_btc_tuned_retired_v85.toml"
)
_V86_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_EPOCH_MANIFEST = Path(
    "data/backups/bidirectional_cohort/accounting_epochs/"
    "v79_seven_asset_all_active_6c12d96_20260903T0220Z/manifest.json"
)
_NOW = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)
_RUN_ID = "bidirectional-live-v79-test"


def test_v79_accepts_fresh_exact_route_and_execution_monitoring() -> None:
    """All seven assets and nine routes must be attributable and protected."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    report = build_v79_poststart_acceptance(
        _checkpoint(config),
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is True
    assert report["reasons"] == []
    assert report["checks"]["provider_monitoring"] == {
        "passed": True,
        "reasons": [],
        "expected_routes": 9,
        "evaluated_routes": 9,
        "routes_with_metrics": 9,
    }
    assert report["checks"]["execution_attribution"]["fills"] == 2


def test_v79_checkpoint_attachment_publishes_monitoring_verdict() -> None:
    """The rolling checkpoint must carry V79 acceptance without another command."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)

    attach_v79_poststart_acceptance(checkpoint, _CONFIG, observed_at=_NOW)

    acceptance = checkpoint["poststart_acceptance"]
    assert acceptance["accepted"] is True
    assert acceptance["contract"]["execution_authority"] == "none"


def test_v80_accepts_exact_split_caps_and_rejects_generation_drift() -> None:
    config = load_multi_asset_live_config(_V80_CONFIG, mode="observe")
    checkpoint = _checkpoint(config, _V80_CONFIG)
    epoch = {
        "epoch_id": "v80-test",
        "profile_fingerprint": config.profile_fingerprint,
        "start_venue_timestamp_ms": 1_788_402_027_059,
    }
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = epoch

    accepted = build_v79_poststart_acceptance(
        checkpoint,
        config,
        epoch,
        now_utc=_NOW,
    )
    checkpoint["configuration_generation"]["current_asset_entry_slippage_caps"][
        "ETH"
    ] = 0.01
    rejected = build_v79_poststart_acceptance(
        checkpoint,
        config,
        epoch,
        now_utc=_NOW,
    )

    assert accepted["schema_version"] == "v80_poststart_acceptance_v1"
    assert accepted["accepted"] is True
    assert "runtime_execution_contract_drift" in rejected["reasons"]


def test_v80_checkpoint_attachment_uses_the_bound_epoch() -> None:
    config = load_multi_asset_live_config(_V80_CONFIG, mode="observe")
    checkpoint = _checkpoint(config, _V80_CONFIG)
    epoch = checkpoint["audit"]["portfolio_archive"]["accounting_epoch"]
    epoch["epoch_id"] = "v80_entry_ioc_hardened_89c84ec_test"
    epoch["profile_fingerprint"] = config.profile_fingerprint

    attached = attach_seven_asset_poststart_acceptance(
        checkpoint,
        _V80_CONFIG,
        observed_at=_NOW,
    )

    assert attached is True
    assert checkpoint["poststart_acceptance"]["accepted"] is True


def test_v85_accepts_nine_monitored_routes_with_one_observe_only() -> None:
    """V85 must monitor the retired route while excluding it from execution."""
    config = load_multi_asset_live_config(_V85_CONFIG, mode="observe")
    checkpoint = _checkpoint(config, _V85_CONFIG)
    epoch = {
        "epoch_id": "v85_btc_tuned_retired_18306afa_test",
        "profile_fingerprint": config.profile_fingerprint,
        "start_venue_timestamp_ms": 1_788_457_000_000,
    }
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = epoch

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        epoch,
        now_utc=_NOW,
    )

    assert report["schema_version"] == "v85_poststart_acceptance_v1"
    assert report["accepted"] is True
    assert report["checks"]["provider_monitoring"]["expected_routes"] == 9
    assert checkpoint["audit"]["run"]["observe_only_provider_symbols"] == [
        "hulk_expansion_short_tuned_v2|BTC"
    ]
    assert len(checkpoint["audit"]["run"]["executable_provider_symbols"]) == 8


def test_v85_rejects_missing_observe_only_identity() -> None:
    """Retirement cannot silently disappear from runtime identity telemetry."""
    config = load_multi_asset_live_config(_V85_CONFIG, mode="observe")
    checkpoint = _checkpoint(config, _V85_CONFIG)
    epoch = {
        "epoch_id": "v85_btc_tuned_retired_18306afa_test",
        "profile_fingerprint": config.profile_fingerprint,
        "start_venue_timestamp_ms": 1_788_457_000_000,
    }
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = epoch
    checkpoint["audit"]["run"]["observe_only_provider_symbols"] = []

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        epoch,
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_identity_mismatch" in report["reasons"]


def test_v86_accepts_nine_monitored_routes_with_three_observe_only() -> None:
    """V86 must keep failed routes visible while exposing only six executions."""
    config = load_multi_asset_live_config(_V86_CONFIG, mode="observe")
    checkpoint = _checkpoint(config, _V86_CONFIG)
    epoch = {
        "epoch_id": "v86_failed_routes_retired_f454101e_test",
        "profile_fingerprint": config.profile_fingerprint,
        "start_venue_timestamp_ms": 1_788_457_000_000,
    }
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"] = epoch
    route = "liquidity_sweep_long_1h_stop60_target60_v2"
    exit_fill, entry_fill = checkpoint["audit"]["execution"]["fill_details"]
    exit_fill.update(
        strategy_id=route,
        exit_controller_id=route,
        direction="Close Long",
        side="A",
    )
    entry_fill.update(strategy_id=route, direction="Open Long", side="B")
    trade = checkpoint["audit"]["trade_reflections"]["trades"][0]
    trade.update(
        strategy_id=route,
        entry_strategy_id=route,
        exit_controller_strategy_id=route,
        side="long",
    )

    attached = attach_seven_asset_poststart_acceptance(
        checkpoint,
        _V86_CONFIG,
        observed_at=_NOW,
    )

    assert attached is True
    report = checkpoint["poststart_acceptance"]
    assert report["schema_version"] == "v86_poststart_acceptance_v1"
    assert report["accepted"] is True
    assert report["checks"]["provider_monitoring"]["expected_routes"] == 9
    assert checkpoint["audit"]["run"]["observe_only_provider_symbols"] == [
        "hulk_expansion_short_robust_v3|BTC",
        "hulk_expansion_short_tuned_v2|BTC",
        "zec_donchian_20_10_atr20_long_v1|ZEC",
    ]
    assert len(checkpoint["audit"]["run"]["executable_provider_symbols"]) == 6


def test_v79_rejects_one_missing_provider_evaluation() -> None:
    """A nominally running asset cannot hide an unevaluated strategy route."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    readiness = checkpoint["audit"]["readiness"]["by_provider_symbol"]
    readiness.pop("zec_donchian_20_10_atr20_long_v1|ZEC")

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "provider_monitoring_incomplete" in report["reasons"]


@pytest.mark.parametrize(
    "field,value", [("strategy_id", "unattributed"), ("operation", "unknown")]
)
def test_v79_rejects_placeholder_fill_attribution(field: str, value: str) -> None:
    """Every fill must retain a concrete route and lifecycle operation."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["audit"]["execution"]["fill_details"][0][field] = value

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "execution_fill_attribution_incomplete" in report["reasons"]


@pytest.mark.parametrize(
    "operation,direction,side",
    [
        ("entry", "Open Long", "B"),
        ("entry", "Open Short", "B"),
        ("protective_stop", "Close Long", "A"),
    ],
)
def test_v79_rejects_fill_direction_outside_the_route_contract(
    operation: str,
    direction: str,
    side: str,
) -> None:
    """A BTC-short route cannot report a long fill or invalid venue side."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    fill = checkpoint["audit"]["execution"]["fill_details"][0]
    fill.update({"operation": operation, "direction": direction, "side": side})

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "execution_fill_direction_invalid" in report["reasons"]


def test_v79_rejects_an_unprotected_open_position() -> None:
    """A live position without an acknowledged stop must fail acceptance."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    checkpoint["lifecycle"]["asset_states"]["ETH"] = "OPEN"
    eth = checkpoint["audit"]["health"]["assets"]["ETH"]
    eth.update({"final_state": "OPEN", "protected_if_open": False, "stop_oid": None})

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "open_position_unprotected:ETH" in report["reasons"]


def test_v79_accepts_a_concretely_attributed_profit_target_fill() -> None:
    """Target fills are valid exits when route and controller remain concrete."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    fill = checkpoint["audit"]["execution"]["fill_details"][0]
    fill.update({"operation": "target", "exit_reason": "profit_target"})
    checkpoint["audit"]["trade_reflections"]["trades"][0]["exit_reason"] = (
        "profit_target"
    )

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is True


def test_v79_rejects_exit_policy_or_epoch_drift() -> None:
    """Runtime exits and displayed accounting must remain bound to V79."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    policies = checkpoint["configuration_generation"]["current_provider_exit_policies"]
    policies["eth_range_onset_long_dual_mtf_v2"]["maximum_hold_seconds"] = 1
    checkpoint["audit"]["portfolio_archive"]["accounting_epoch"][
        "start_venue_timestamp_ms"
    ] += 1

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_execution_contract_drift" in report["reasons"]
    assert "accounting_epoch_mismatch" in report["reasons"]


@pytest.mark.parametrize(
    "route,field,value",
    [
        ("zec_donchian_20_10_atr20_long_v1|ZEC", "maximum_stop_bps", 999.0),
        ("hip3_spcx_cash_session_fresh15_long_v4|xyz:SPCX", "target_bps", 1.0),
    ],
)
def test_v79_rejects_runtime_stop_or_target_drift(
    route: str,
    field: str,
    value: float,
) -> None:
    """A changed protective stop or profit target must be visible and rejected."""
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    parity = checkpoint["audit"]["execution"]["friction_parity"]
    parity["by_provider_symbol"][route]["runtime_contract"][field] = value

    report = build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )

    assert report["accepted"] is False
    assert "runtime_execution_contract_drift" in report["reasons"]


def _checkpoint(
    config: MultiAssetLiveConfig,
    config_path: Path = _CONFIG,
) -> dict[str, object]:
    symbols = tuple(config.symbols)
    routes = _routes(config)
    observed_routes = _observed_routes(config)
    health = _health(symbols)
    expectation = load_configuration_expectation(config_path)
    generation = configuration_generation_evidence(
        config.profile_fingerprint,
        expectation,
        health,
    )
    return {
        "generated_at_utc": "2026-09-03T00:59:30+00:00",
        "checkpoint_contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_pause": False,
            "automatic_retuning": False,
            "runtime_strategy_changed": False,
        },
        "lifecycle": {
            "state": "running_consistent",
            "backend_process_health": "healthy",
            "cohort_heartbeat_status": "running",
            "cohort_heartbeat_age_seconds": 5.0,
            "faulted_assets": [],
            "asset_states": dict.fromkeys(symbols, "FLAT"),
        },
        "configuration_generation": generation,
        "audit": _audit(config, health, routes, observed_routes),
    }


def _routes(config: MultiAssetLiveConfig) -> list[str]:
    return sorted(
        f"{strategy}|{symbol}"
        for strategy, symbol in config.executable_provider_symbols
    )


def _observed_routes(config: MultiAssetLiveConfig) -> list[str]:
    return sorted(
        f"{provider.strategy_id}|{symbol}"
        for provider in config.providers
        for symbol in provider.symbols
    )


def _health(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
    return {
        symbol: {
            "final_state": "FLAT",
            "protected_if_open": True,
            "stop_oid": None,
            "faults": 0,
        }
        for symbol in symbols
    }


def _audit(
    config: MultiAssetLiveConfig,
    health: dict[str, dict[str, object]],
    routes: list[str],
    observed_routes: list[str],
) -> dict[str, object]:
    return {
        "run": {
            "run_id": _RUN_ID,
            "profile_id": config.profile_id,
            "profile_fingerprint": config.profile_fingerprint,
            "symbols": list(config.symbols),
            "executable_provider_symbols": routes,
            "observe_only_provider_symbols": sorted(
                set(observed_routes).difference(routes)
            ),
            "maximum_concurrent_positions": 7,
        },
        "routing": {"executable_provider_symbols": routes},
        "readiness": {"by_provider_symbol": _readiness(observed_routes)},
        "health": {"assets": health, "faults": 0},
        "execution": {
            "fills": 2,
            "current_run_fills": 2,
            "history_run_ids": [_RUN_ID],
            "projected_fills": 2,
            "closed_trades": 1,
            "open_lifecycles": 0,
            "open_positions": [],
            "fees_usd": 0.0085968,
            "funding_usd": 0.0,
            "net_pnl_usd": -0.1085968,
            "wins": 0,
            "losses": 1,
            "fill_details": [_fill(), _entry_fill()],
            "fee_rate_bps": _metric_summary(4.32, 4.32),
            "slippage_bps": _metric_summary(0.0, 0.0),
            "acknowledgement_latency_ms": _metric_summary(10.0, 11.0),
            "friction_parity": _friction_parity(config),
        },
        "trade_reflections": _trade_reflections(config),
        "portfolio_archive": {"accounting_epoch": _epoch()},
    }


def _readiness(routes: list[str]) -> dict[str, dict[str, object]]:
    return {
        route: {
            "count": 1,
            "latest_metrics": {"technical_availability": "available"},
        }
        for route in routes
    }


def _fill() -> dict[str, object]:
    return {
        "trade_id": 1,
        "oid": 2,
        "symbol": "BTC",
        "origin_run_id": _RUN_ID,
        "strategy_id": "hulk_expansion_short_robust_v3",
        "operation": "protective_stop",
        "exit_controller_id": "hulk_expansion_short_robust_v3",
        "exit_reason": "protective_stop",
        "direction": "Close Short",
        "side": "B",
        "price": 100.0,
        "size": 0.1,
        "fee_usd": 0.00432,
        "closed_pnl_usd": -0.1,
        "expected_price": 100.0,
        "slippage_bps": 0.0,
        "acknowledgement_latency_ms": 11,
        "venue_timestamp_ms": 1_788_394_750_000,
    }


def _entry_fill() -> dict[str, object]:
    return {
        "trade_id": 2,
        "oid": 1,
        "symbol": "BTC",
        "origin_run_id": _RUN_ID,
        "strategy_id": "hulk_expansion_short_robust_v3",
        "operation": "entry",
        "direction": "Open Short",
        "side": "A",
        "price": 99.0,
        "size": 0.1,
        "fee_usd": 0.0042768,
        "closed_pnl_usd": 0.0,
        "expected_price": 99.0,
        "slippage_bps": 0.0,
        "acknowledgement_latency_ms": 10,
        "venue_timestamp_ms": 1_788_394_749_000,
    }


def _trade_reflections(config: MultiAssetLiveConfig) -> dict[str, object]:
    return {
        "closed_trades": 1,
        "trades": [
            {
                "lifecycle_id": "BTC:1",
                "source_run_id": "bidirectional-live-v79-test",
                "source_profile_fingerprint": config.profile_fingerprint,
                "symbol": "BTC",
                "strategy_id": "hulk_expansion_short_robust_v3",
                "entry_strategy_id": "hulk_expansion_short_robust_v3",
                "exit_controller_strategy_id": "hulk_expansion_short_robust_v3",
                "cross_provider_exit": False,
                "side": "short",
                "entry_oid": 1,
                "exit_oid": 2,
                "entry": {
                    "price": 99.0,
                    "size": 0.1,
                    "venue_timestamp_ms": 1_788_394_749_000,
                },
                "exit": {
                    "price": 100.0,
                    "size": 0.1,
                    "venue_timestamp_ms": 1_788_394_750_000,
                },
                "exit_reason": "protective_stop",
                "holding_time_ms": 1_000,
                "fees_usd": 0.0085968,
                "funding_usd": 0.0,
                "net_pnl_usd": -0.1085968,
            }
        ],
    }


def _metric_summary(first: float, second: float) -> dict[str, object]:
    values = sorted((first, second))
    return {
        "status": "observed",
        "count": 2,
        "minimum": values[0],
        "median": sum(values) / 2.0,
        "maximum": values[1],
        "mean": sum(values) / 2.0,
    }


def _friction_parity(config: MultiAssetLiveConfig) -> dict[str, object]:
    assets = {asset.symbol: asset_config_payload(asset) for asset in config.assets}
    rows: dict[str, object] = {}
    for provider in config.providers:
        payload = provider_config_payload(provider)
        for symbol in provider.symbols:
            contract, source = runtime_contract(payload, assets[symbol])
            rows[f"{provider.strategy_id}|{symbol}"] = {
                "runtime_contract": contract,
                "runtime_contract_source": source,
                "execution_effect": "report_only",
            }
    return {"by_provider_symbol": rows}


def _epoch() -> dict[str, object]:
    document = json.loads(_EPOCH_MANIFEST.read_text(encoding="utf-8"))
    return deepcopy(document["accounting_epoch"])
