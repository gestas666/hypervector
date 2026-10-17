"""V79 post-start acceptance for actual open stop, target, and exit plans."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)
from test_v79_poststart_acceptance import _CONFIG, _checkpoint, _epoch

_NOW = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)
_BTC_SWEEP = "liquidity_sweep_long_1h_stop60_target60_v2"
_ETH_RANGE = "eth_range_onset_long_dual_mtf_v2"


@pytest.mark.evidence
def test_v79_accepts_an_exact_open_lifecycle_contract() -> None:
    """A correctly routed, protected, and timed BTC lifecycle remains accepted."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)

    report = _report(checkpoint, config)

    assert report["accepted"] is True
    assert report["checks"]["position_protection"] == {
        "passed": True,
        "reasons": [],
        "open_positions": 1,
    }


@pytest.mark.evidence
@pytest.mark.parametrize("stop_price", [100.4, 95.0])
def test_v79_rejects_wrong_side_or_distance_for_an_open_stop(
    stop_price: float,
) -> None:
    """A stop must be adverse and match its configured distance envelope."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    reflection = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    reflection["protective_stop"]["trigger_price"] = stop_price

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_stop_contract_invalid:BTC" in report["reasons"]


@pytest.mark.evidence
@pytest.mark.parametrize("target_price", [None, 99.0, 110.0])
def test_v79_rejects_missing_wrong_side_or_distance_for_a_required_target(
    target_price: float | None,
) -> None:
    """A required BTC target must be favorable and match its fixed contract."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    reflection = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    reflection["target_order"] = _target(target_price)

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_target_contract_invalid:BTC" in report["reasons"]


@pytest.mark.evidence
def test_v79_rejects_an_unconfigured_target_on_a_no_target_route() -> None:
    """An ETH route configured without a target cannot silently add one."""
    config = _config()
    checkpoint = _open_checkpoint(config, _ETH_RANGE, "ETH", 99.4, 101.0)

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_target_contract_invalid:ETH" in report["reasons"]


@pytest.mark.evidence
def test_v79_rejects_exit_plan_drift_on_an_open_lifecycle() -> None:
    """The bound timer and controller plan must remain the configured plan."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    reflection = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    reflection["exit_plan"]["maximum_hold_seconds"] = 1

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_exit_plan_contract_invalid:BTC" in report["reasons"]


@pytest.mark.evidence
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_run_id", "unrelated-run"),
        ("entry_size", 0.2),
        ("entry_timestamp", 1_788_394_750_001),
    ],
)
def test_v79_rejects_open_reflection_not_bound_to_exact_entry_fill(
    field: str,
    value: object,
) -> None:
    """An open lifecycle must resolve to its exact fill and originating run."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    reflection = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    if field == "source_run_id":
        reflection[field] = value
    elif field == "entry_size":
        reflection["entry"]["size"] = value
    else:
        reflection["entry"]["venue_timestamp_ms"] = value

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_entry_fill_invalid:BTC" in report["reasons"]


@pytest.mark.evidence
def test_v79_rejects_open_position_projection_drift() -> None:
    """Execution, reflection, health, and marked position must describe one row."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    reflection = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    reflection["marked_economics"]["size_signed"] = 0.2

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_position_projection_invalid:BTC" in report["reasons"]


@pytest.mark.evidence
def test_v79_accepts_partial_entry_fills_for_one_open_lifecycle() -> None:
    """Partial entry fills reconcile to the journal's aggregate entry leg."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    execution = checkpoint["audit"]["execution"]
    first = deepcopy(execution["fill_details"][0])
    second = deepcopy(first)
    first.update({"size": 0.04, "fee_usd": 0.001728})
    second.update({"trade_id": 3, "size": 0.06, "fee_usd": 0.002592})
    execution.update(
        {
            "fills": 2,
            "current_run_fills": 2,
            "projected_fills": 2,
            "fill_details": [first, second],
            "fee_rate_bps": _metric_summary([4.32, 4.32]),
            "slippage_bps": _metric_summary([0.0, 0.0]),
            "acknowledgement_latency_ms": _metric_summary([11.0, 11.0]),
        }
    )

    report = _report(checkpoint, config)

    assert report["accepted"] is True


@pytest.mark.evidence
def test_v79_accepts_prior_run_entry_for_a_restarted_open_lifecycle() -> None:
    """A restart preserves an open lifecycle when entry provenance remains exact."""
    config = _config()
    checkpoint = _open_checkpoint(config, _BTC_SWEEP, "BTC", 99.4, 100.6)
    audit = checkpoint["audit"]
    prior_run = "compatible-prior-run"
    audit["execution"]["history_run_ids"] = [prior_run, audit["run"]["run_id"]]
    audit["execution"]["current_run_fills"] = 0
    audit["execution"]["fill_details"][0]["origin_run_id"] = prior_run
    audit["open_trade_reflections"]["trades"][0]["source_run_id"] = prior_run

    report = _report(checkpoint, config)

    assert report["accepted"] is True


@pytest.mark.evidence
def test_v79_rejects_phantom_open_execution_position_under_flat_health() -> None:
    """A position row cannot disappear behind otherwise-flat lifecycle health."""
    config = _config()
    checkpoint = _checkpoint(config)
    execution = checkpoint["audit"]["execution"]
    execution["open_lifecycles"] = 1
    execution["open_positions"] = [{"symbol": "BTC"}]

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "open_lifecycle_projection_mismatch" in report["reasons"]


def _config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(_CONFIG, mode="observe")


def _open_checkpoint(
    config: MultiAssetLiveConfig,
    strategy: str,
    symbol: str,
    stop_price: float,
    target_price: float | None,
) -> dict[str, object]:
    checkpoint = _checkpoint(config)
    audit = checkpoint["audit"]
    contract = next(
        provider.execution_for(symbol, "long")
        for provider in config.providers
        if provider.strategy_id == strategy
    )
    health = audit["health"]["assets"][symbol]
    order_ids = [11] + ([] if target_price is None else [12])
    health.update(
        {
            "final_state": "OPEN",
            "position_size_signed": 0.1,
            "open_order_ids": order_ids,
            "protected_if_open": True,
            "stop_oid": 11,
        }
    )
    checkpoint["lifecycle"]["asset_states"][symbol] = "OPEN"
    fill = audit["execution"]["fill_details"][0]
    fill.update(
        {
            "strategy_id": strategy,
            "symbol": symbol,
            "operation": "entry",
            "direction": "Open Long",
            "side": "B",
            "exit_controller_id": None,
            "exit_reason": None,
            "closed_pnl_usd": 0.0,
        }
    )
    audit["execution"].update(
        {
            "fills": 1,
            "current_run_fills": 1,
            "projected_fills": 1,
            "closed_trades": 0,
            "fees_usd": 0.0,
            "funding_usd": 0.0,
            "net_pnl_usd": 0.0,
            "wins": 0,
            "losses": 0,
            "fill_details": [fill],
            "fee_rate_bps": _single_metric_summary(4.32),
            "slippage_bps": _single_metric_summary(0.0),
            "acknowledgement_latency_ms": _single_metric_summary(11.0),
        }
    )
    audit["trade_reflections"] = {"closed_trades": 0, "trades": []}
    position = {
        "status": "provisional_open",
        "symbol": symbol,
        "side": "long",
        "size_signed": 0.1,
        "entry_price": 100.0,
        "target_order": _target(target_price),
    }
    audit["execution"].update({"open_lifecycles": 1, "open_positions": [position]})
    audit["open_trade_reflections"] = {
        "open_lifecycles": 1,
        "trades": [
            {
                "lifecycle_id": f"{symbol}:2",
                "source_run_id": audit["run"]["run_id"],
                "symbol": symbol,
                "strategy_id": strategy,
                "side": "long",
                "entry": {
                    "price": 100.0,
                    "size": 0.1,
                    "venue_timestamp_ms": 1_788_394_750_000,
                },
                "protective_stop": {"oid": 11, "trigger_price": stop_price},
                "target_order": _target(target_price),
                "marked_economics": dict(position),
                "exit_plan": {
                    "source": "bound_execution_plan",
                    "controller": "cohort_maximum_hold",
                    "maximum_hold_seconds": contract.maximum_hold_seconds,
                    "maximum_hold_policy": contract.maximum_hold_policy,
                    "hard_maximum_hold_seconds": contract.hard_maximum_hold_seconds,
                    "provider_recipe_exit_policy": contract.provider_recipe_exit_policy,
                    "profit_lock_policy": contract.profit_lock_policy,
                    "profit_lock_activation_bps": contract.profit_lock_activation_bps,
                    "profit_lock_floor_bps": contract.profit_lock_floor_bps,
                    "profit_lock_giveback_bps": contract.profit_lock_giveback_bps,
                    "opposite_intent_exit_scope": (
                        "selected_opposite_from_any_executable_provider_same_symbol"
                    ),
                    "opposite_intent_arbitration": "regime_then_priority",
                },
            }
        ],
    }
    return checkpoint


def _target(price: float | None) -> dict[str, object] | None:
    return None if price is None else {"oid": 12, "limit_price": price}


def _single_metric_summary(value: float) -> dict[str, object]:
    return {
        "status": "observed",
        "count": 1,
        "minimum": value,
        "median": value,
        "maximum": value,
        "mean": value,
    }


def _metric_summary(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    return {
        "status": "observed",
        "count": len(ordered),
        "minimum": ordered[0],
        "median": sum(ordered) / len(ordered),
        "maximum": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def _report(
    checkpoint: dict[str, object], config: MultiAssetLiveConfig
) -> dict[str, object]:
    return build_v79_poststart_acceptance(
        checkpoint,
        config,
        _epoch(),
        now_utc=_NOW,
    )
