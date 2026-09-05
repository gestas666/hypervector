"""V79 acceptance for exact closed entry/exit lifecycle reconciliation."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig
from hypervector.research.v79_poststart_acceptance import (
    build_v79_poststart_acceptance,
)
from test_v79_poststart_acceptance import _CONFIG, _RUN_ID, _checkpoint, _epoch

_NOW = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)
_STRATEGY = "hulk_expansion_short_tuned_v2"


def test_v79_accepts_a_reconciled_closed_lifecycle() -> None:
    """Exact entry, exit, cost, and terminal evidence remains accepted."""
    config, checkpoint = _closed_checkpoint()

    report = _report(checkpoint, config)

    assert report["accepted"] is True
    assert report["checks"]["closed_lifecycle_integrity"] == {
        "passed": True,
        "reasons": [],
        "closed_trades": 1,
    }


def test_v79_rejects_an_exit_fill_without_a_closed_lifecycle() -> None:
    """A close fill cannot be accepted without its resolved lifecycle."""
    config, checkpoint = _closed_checkpoint()
    checkpoint["audit"].pop("trade_reflections")

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_projection_mismatch" in report["reasons"]


def test_v79_rejects_declared_close_without_reflections_or_exit_fill() -> None:
    """A declared close cannot disappear when terminal fill projection is absent."""
    config, checkpoint = _closed_checkpoint()
    execution = checkpoint["audit"]["execution"]
    checkpoint["audit"].pop("trade_reflections")
    execution.update(
        {
            "fills": 1,
            "current_run_fills": 1,
            "projected_fills": 1,
            "fill_details": execution["fill_details"][:1],
            "fee_rate_bps": _metric_values([4.32]),
            "slippage_bps": _metric_values([0.0]),
            "acknowledgement_latency_ms": _metric_values([10.0]),
        }
    )

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_projection_mismatch" in report["reasons"]


def test_v79_rejects_missing_terminal_closed_pnl() -> None:
    """A terminal fill must carry explicit realized PnL even when it is zero."""
    config, checkpoint = _closed_checkpoint()
    exit_fill = checkpoint["audit"]["execution"]["fill_details"][1]
    exit_fill.pop("closed_pnl_usd")
    trade = checkpoint["audit"]["trade_reflections"]["trades"][0]
    trade["net_pnl_usd"] = -0.0086832
    checkpoint["audit"]["execution"]["net_pnl_usd"] = -0.0086832

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_invalid:BTC:10" in report["reasons"]


def test_v79_rejects_trade_source_that_differs_from_entry_origin() -> None:
    """A compatible run ID cannot impersonate the lifecycle's entry run."""
    config, checkpoint = _closed_checkpoint()
    execution = checkpoint["audit"]["execution"]
    execution["history_run_ids"] = ["compatible-prior-run", _RUN_ID]
    trade = checkpoint["audit"]["trade_reflections"]["trades"][0]
    trade["source_run_id"] = "compatible-prior-run"

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_invalid:BTC:10" in report["reasons"]


def test_v79_rejects_mixed_operations_for_one_exit_order() -> None:
    """Partial fills for one order cannot change terminal operation semantics."""
    config, checkpoint = _closed_checkpoint()
    execution = checkpoint["audit"]["execution"]
    first = deepcopy(execution["fill_details"][1])
    second = deepcopy(first)
    first.update({"size": 0.04, "fee_usd": 0.00174528, "closed_pnl_usd": -0.04})
    second.update(
        {
            "trade_id": 3,
            "operation": "target",
            "size": 0.06,
            "fee_usd": 0.00261792,
            "closed_pnl_usd": -0.06,
        }
    )
    execution.update(
        {
            "fills": 3,
            "current_run_fills": 3,
            "projected_fills": 3,
            "fill_details": [execution["fill_details"][0], first, second],
            "fee_rate_bps": _metric_values([4.32, 4.32, 4.32]),
            "slippage_bps": _metric_values([0.0, 0.0, 0.0]),
            "acknowledgement_latency_ms": _metric_values([10.0, 11.0, 11.0]),
        }
    )

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_invalid:BTC:10" in report["reasons"]


def test_v79_accepts_exact_partial_entry_and_exit_fills() -> None:
    """Valid partial fills aggregate without creating false lifecycle alarms."""
    config, checkpoint = _closed_checkpoint()
    execution = checkpoint["audit"]["execution"]
    entry = deepcopy(execution["fill_details"][0])
    exit_fill = deepcopy(execution["fill_details"][1])
    entries = _split_fill(entry, 0.04, 0.06, 3)
    exits = _split_fill(exit_fill, 0.04, 0.06, 4)
    execution.update(
        {
            "fills": 4,
            "current_run_fills": 4,
            "projected_fills": 4,
            "fill_details": [*entries, *exits],
            "fee_rate_bps": _metric_values([4.32] * 4),
            "slippage_bps": _metric_values([0.0] * 4),
            "acknowledgement_latency_ms": _metric_values([10.0, 10.0, 11.0, 11.0]),
        }
    )

    report = _report(checkpoint, config)

    assert report["accepted"] is True


@pytest.mark.parametrize(
    ("mutation",),
    [
        ("exit_size",),
        ("exit_before_entry",),
        ("net_pnl",),
        ("exit_reason",),
        ("profile_fingerprint",),
    ],
)
def test_v79_rejects_incoherent_closed_lifecycle_evidence(mutation: str) -> None:
    """One malformed lifecycle field must reject the continuous verdict."""
    config, checkpoint = _closed_checkpoint()
    trade = checkpoint["audit"]["trade_reflections"]["trades"][0]
    exit_fill = checkpoint["audit"]["execution"]["fill_details"][1]
    _mutate_closed_trade(trade, exit_fill, mutation)

    report = _report(checkpoint, config)

    assert report["accepted"] is False
    assert "closed_lifecycle_invalid:BTC:10" in report["reasons"]


def _closed_checkpoint() -> tuple[MultiAssetLiveConfig, dict[str, object]]:
    from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    checkpoint = _checkpoint(config)
    audit = checkpoint["audit"]
    entry_fill = _entry_fill()
    exit_fill = _exit_fill()
    audit["execution"].update(
        {
            "fills": 2,
            "current_run_fills": 2,
            "projected_fills": 2,
            "closed_trades": 1,
            "fees_usd": 0.0086832,
            "funding_usd": 0.0,
            "net_pnl_usd": -0.1086832,
            "wins": 0,
            "losses": 1,
            "fill_details": [entry_fill, exit_fill],
            "fee_rate_bps": _metric_summary(4.32, 4.32),
            "slippage_bps": _metric_summary(0.0, 0.0),
            "acknowledgement_latency_ms": _metric_summary(10.0, 11.0),
        }
    )
    audit["trade_reflections"] = {
        "closed_trades": 1,
        "trades": [_trade(audit["run"])],
    }
    return config, checkpoint


def _entry_fill() -> dict[str, object]:
    return {
        "trade_id": 1,
        "oid": 10,
        "symbol": "BTC",
        "origin_run_id": _RUN_ID,
        "strategy_id": _STRATEGY,
        "operation": "entry",
        "direction": "Open Short",
        "side": "A",
        "price": 100.0,
        "size": 0.1,
        "fee_usd": 0.00432,
        "closed_pnl_usd": 0.0,
        "expected_price": 100.0,
        "slippage_bps": 0.0,
        "acknowledgement_latency_ms": 10,
        "venue_timestamp_ms": 1_788_394_749_000,
    }


def _exit_fill() -> dict[str, object]:
    return {
        "trade_id": 2,
        "oid": 11,
        "symbol": "BTC",
        "origin_run_id": _RUN_ID,
        "strategy_id": _STRATEGY,
        "operation": "protective_stop",
        "exit_controller_id": _STRATEGY,
        "exit_reason": "protective_stop",
        "direction": "Close Short",
        "side": "B",
        "price": 101.0,
        "size": 0.1,
        "fee_usd": 0.0043632,
        "closed_pnl_usd": -0.1,
        "expected_price": 101.0,
        "slippage_bps": 0.0,
        "acknowledgement_latency_ms": 11,
        "venue_timestamp_ms": 1_788_394_750_000,
    }


def _trade(run: dict[str, object]) -> dict[str, object]:
    return {
        "lifecycle_id": "BTC:10",
        "source_run_id": run["run_id"],
        "source_profile_fingerprint": run["profile_fingerprint"],
        "symbol": "BTC",
        "strategy_id": _STRATEGY,
        "entry_strategy_id": _STRATEGY,
        "exit_controller_strategy_id": _STRATEGY,
        "cross_provider_exit": False,
        "side": "short",
        "entry_oid": 10,
        "exit_oid": 11,
        "entry": {
            "price": 100.0,
            "size": 0.1,
            "venue_timestamp_ms": 1_788_394_749_000,
        },
        "exit": {
            "price": 101.0,
            "size": 0.1,
            "venue_timestamp_ms": 1_788_394_750_000,
        },
        "exit_reason": "protective_stop",
        "holding_time_ms": 1_000,
        "fees_usd": 0.0086832,
        "funding_usd": 0.0,
        "net_pnl_usd": -0.1086832,
    }


def _mutate_closed_trade(
    trade: dict[str, object], exit_fill: dict[str, object], mutation: str
) -> None:
    if mutation == "exit_size":
        trade["exit"]["size"] = 0.09
    elif mutation == "exit_before_entry":
        timestamp = trade["entry"]["venue_timestamp_ms"] - 1
        trade["exit"]["venue_timestamp_ms"] = timestamp
        trade["holding_time_ms"] = -1
        exit_fill["venue_timestamp_ms"] = timestamp
    elif mutation == "net_pnl":
        trade["net_pnl_usd"] = 0.0
    elif mutation == "exit_reason":
        trade["exit_reason"] = "maximum_hold_seconds"
    elif mutation == "profile_fingerprint":
        trade["source_profile_fingerprint"] = "wrong-profile"
    else:
        raise AssertionError(f"unknown mutation {mutation}")


def _report(
    checkpoint: dict[str, object], config: MultiAssetLiveConfig
) -> dict[str, object]:
    return build_v79_poststart_acceptance(
        deepcopy(checkpoint),
        config,
        _epoch(),
        now_utc=_NOW,
    )


def _metric_summary(first: float, second: float) -> dict[str, object]:
    return _metric_values([first, second])


def _metric_values(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    median = (
        ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    return {
        "status": "observed",
        "count": count,
        "minimum": ordered[0],
        "median": median,
        "maximum": ordered[-1],
        "mean": sum(ordered) / count,
    }


def _split_fill(
    fill: dict[str, object], first_size: float, second_size: float, trade_id: int
) -> tuple[dict[str, object], dict[str, object]]:
    original_size = float(fill["size"])
    first = deepcopy(fill)
    second = deepcopy(fill)
    first["size"] = first_size
    second["size"] = second_size
    second["trade_id"] = trade_id
    for key in ("fee_usd", "closed_pnl_usd"):
        total = float(fill[key])
        first[key] = total * first_size / original_size
        second[key] = total * second_size / original_size
    return first, second
