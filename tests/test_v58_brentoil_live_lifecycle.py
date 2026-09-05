"""Exact report-only capture of the live V58 BRENTOIL lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module, util

import pytest

from test_v58_live_close_ledger import _close, _ledger_rows


_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_RUN_ID = "bidirectional-live-1787166474078"
_ASSET_PROFILE = f"{_PROFILE}_xyz:brentoil"
_ASSET_FINGERPRINT = "c" * 64
_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_LIFECYCLE = "xyz:BRENTOIL:520642502465"
_STOP_OID = 520642541320
_ADOPTED_RUN_ID = "bidirectional-live-1787272047790"


def test_open_lifecycle_is_exactly_bound_and_protected() -> None:
    """An open report must bind entry evidence and full stop protection."""
    module_name = "hypervector.research.v58_brentoil_live_lifecycle"
    assert util.find_spec(module_name) is not None, "BRENTOIL reconciler is missing"
    module = import_module(module_name)

    report = module.build_v58_brentoil_lifecycle_report(
        _preregistration(),
        _checkpoint(),
        _venue(),
        _ledger_rows()[:2],
        _ledger_evidence(),
        datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )

    assert report["state"] == "open_protected"
    assert report["summary"] == {"open": 1, "resolved": 0}
    assert report["identity"]["lifecycle_id"] == _LIFECYCLE
    actual = report["actual_live_lifecycle"]
    assert actual["entry_oid"] == 520642502465
    assert actual["protective_stop_oid"] == _STOP_OID
    assert actual["protective_stop_trigger_price"] == 90.83248
    assert actual["actual_entry_fill_claimed"] is True
    assert actual["actual_exit_fill_claimed"] is False
    assert actual["funding_usd"] == 0.007814
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["automatic_live_change"] is False


def test_open_lifecycle_accepts_the_backend_checkpoint_contract() -> None:
    """The reconciler must accept the checkpoint's distinct safety schema."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    checkpoint = _checkpoint()
    checkpoint["checkpoint_contract"] = {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "balance_gate": False,
        "performance_gate": False,
    }

    report = module.build_v58_brentoil_lifecycle_report(
        _preregistration(),
        checkpoint,
        _venue(),
        _ledger_rows()[:2],
        _ledger_evidence(),
        datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )

    assert report["state"] == "open_protected"


def test_open_lifecycle_rejects_changed_protective_stop_identity() -> None:
    """A replaced or missing stop must fail instead of appearing protected."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    checkpoint = _checkpoint()
    trade = checkpoint["audit"]["open_trade_reflections"]["trades"][0]
    trade["protective_stop"]["oid"] = 999

    with pytest.raises(ValueError, match="protective stop identity differs"):
        module.build_v58_brentoil_lifecycle_report(
            _preregistration(),
            checkpoint,
            _venue(),
            _ledger_rows()[:2],
            _ledger_evidence(),
            datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
        )


def test_closed_lifecycle_reconciles_cash_exit_and_cleanup() -> None:
    """A resolved close must reconcile raw cash events and flat cleanup."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    report = module.build_v58_brentoil_lifecycle_report(
        _preregistration(),
        _closed_checkpoint(),
        _flat_venue(),
        _ledger_rows(),
        _ledger_evidence(rows=6),
        datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
    )

    assert report["state"] == "resolved"
    assert report["summary"] == {"open": 0, "resolved": 1}
    actual = report["actual_live_lifecycle"]
    assert actual["exit_reason"] == "maximum_hold_seconds"
    assert actual["entry_oid"] == 520642502465
    assert actual["exit_oid"] == 520700000001
    assert actual["exit_fill_time_ms"] == 1787219115000
    assert actual["fees_usd"] == 0.127184
    assert actual["funding_usd"] == 0.007814
    assert actual["net_pnl_usd"] == 3.36933
    assert report["cleanup"]["venue_flat_order_free"] is True


def test_closed_lifecycle_derives_gross_when_canonical_reflection_omits_it() -> None:
    """A canonical close may omit gross while retaining exact cash inputs."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    checkpoint = _closed_checkpoint()
    close = checkpoint["audit"]["trade_reflections"]["trades"][0]
    close.pop("gross_market_pnl_usd")

    report = module.build_v58_brentoil_lifecycle_report(
        _preregistration(),
        checkpoint,
        _flat_venue(),
        _ledger_rows(),
        _ledger_evidence(rows=6),
        datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
    )

    actual = report["actual_live_lifecycle"]
    assert actual["gross_market_pnl_usd"] == pytest.approx(3.4887)
    assert actual["net_pnl_usd"] == pytest.approx(3.36933)


def test_closed_lifecycle_reconciles_authenticated_adopted_epoch_funding() -> None:
    """An adopted epoch retaining the exact lifecycle must retain its funding."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    checkpoint = _closed_checkpoint()
    close = checkpoint["audit"]["trade_reflections"]["trades"][0]
    close["funding_usd"] = 0.010915
    close["net_pnl_usd"] = 3.372431
    rows = _ledger_rows() + _adopted_epoch_rows()

    report = module.build_v58_brentoil_lifecycle_report(
        _preregistration(),
        checkpoint,
        _flat_venue(),
        rows,
        _ledger_evidence(rows=9),
        datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
    )

    actual = report["actual_live_lifecycle"]
    assert actual["funding_usd"] == pytest.approx(0.010915)
    assert actual["net_pnl_usd"] == pytest.approx(3.372431)


def test_closed_lifecycle_rejects_missing_exit_fee_evidence() -> None:
    """A close without its exact fill-bound exit fee must remain unresolved."""
    module = import_module("hypervector.research.v58_brentoil_live_lifecycle")
    rows = [row for row in _ledger_rows() if not _is_exit_fee(row)]

    with pytest.raises(ValueError, match="fee identity differs"):
        module.build_v58_brentoil_lifecycle_report(
            _preregistration(),
            _closed_checkpoint(),
            _flat_venue(),
            rows,
            _ledger_evidence(rows=5),
            datetime(2026, 8, 20, 11, 0, tzinfo=UTC),
        )


def _preregistration() -> dict[str, object]:
    """Return the frozen current-live identity and exit contract."""
    return {
        "schema_version": 1,
        "mode": "v58_brentoil_live_lifecycle_preregistration_v1",
        "frozen_identity": {
            "profile_id": _PROFILE,
            "profile_fingerprint": _FINGERPRINT,
            "run_id": _RUN_ID,
            "asset_profile_id": _ASSET_PROFILE,
            "asset_profile_fingerprint": _ASSET_FINGERPRINT,
            "strategy_id": _STRATEGY,
            "route": f"{_STRATEGY}|xyz:BRENTOIL",
            "symbol": "xyz:BRENTOIL",
            "side": "long",
            "lifecycle_id": _LIFECYCLE,
            "entry_oid": 520642502465,
            "protective_stop_oid": _STOP_OID,
        },
        "frozen_exit_contract": {
            "protective_stop_trigger_price": 90.83248,
            "maximum_hold_seconds": 86400,
            "profit_lock_policy": "none",
            "provider_recipe_exit_policy": "ignore",
            "opposite_intent_exit_scope": (
                "selected_opposite_from_any_executable_provider_same_symbol"
            ),
        },
        "ledger_prefix": {
            "path": "/tmp/xyz:brentoil.jsonl",
            "bytes": 100,
            "sha256": "a" * 64,
            "rows": 2,
        },
        "contract": _report_only_contract(),
    }


def _checkpoint() -> dict[str, object]:
    """Return a compact exact-run checkpoint with one protected open lifecycle."""
    trade = _open_trade()
    return {
        "generated_at_utc": "2026-08-20T10:00:00+00:00",
        "checkpoint_contract": _checkpoint_contract(),
        "configuration_generation": {"matches_runtime": True},
        "lifecycle": {
            "state": "running_consistent",
            "faulted_assets": [],
            "asset_states": {"xyz:BRENTOIL": "OPEN"},
        },
        "audit": {
            "run": _run(),
            "health": {"assets": {"xyz:BRENTOIL": _open_health()}},
            "open_trade_reflections": {"open_lifecycles": 1, "trades": [trade]},
            "trade_reflections": {"trades": []},
        },
    }


def _closed_checkpoint() -> dict[str, object]:
    """Return the same lifecycle after an exact maximum-hold close."""
    checkpoint = _checkpoint()
    checkpoint["lifecycle"]["asset_states"]["xyz:BRENTOIL"] = "FLAT"
    checkpoint["audit"]["health"]["assets"]["xyz:BRENTOIL"] = _flat_health()
    checkpoint["audit"]["open_trade_reflections"] = {
        "open_lifecycles": 0,
        "trades": [],
    }
    close = _close()
    close.update(
        {
            "source_run_id": _RUN_ID,
            "source_profile_fingerprint": _FINGERPRINT,
            "strategy_id": _STRATEGY,
            "symbol": "xyz:BRENTOIL",
            "side": "long",
            "exit_reason": "maximum_hold_seconds",
            "exit_oid": 520700000001,
            "holding_time_ms": 3_599_947,
            "net_pnl_usd": 3.36933,
            "protective_stop": {"oid": _STOP_OID, "trigger_price": 90.83248},
        }
    )
    checkpoint["audit"]["trade_reflections"] = {"trades": [close]}
    return checkpoint


def _open_trade() -> dict[str, object]:
    """Return one actual open reflection matching the preregistration."""
    return {
        "lifecycle_id": _LIFECYCLE,
        "source_run_id": _RUN_ID,
        "strategy_id": _STRATEGY,
        "symbol": "xyz:BRENTOIL",
        "side": "long",
        "entry": _close()["entry"],
        "protective_stop": {"oid": _STOP_OID, "trigger_price": 90.83248},
        "target_order": None,
        "exit_plan": {
            "maximum_hold_seconds": 86400,
            "profit_lock_policy": "none",
            "provider_recipe_exit_policy": "ignore",
            "opposite_intent_exit_scope": (
                "selected_opposite_from_any_executable_provider_same_symbol"
            ),
        },
        "marked_economics": {
            "active_lifecycle_marked_net_pnl_usd": 0.5,
            "funding_usd": 0.007814,
        },
    }


def _run() -> dict[str, object]:
    """Return the exact aggregate runtime identity."""
    return {
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "run_id": _RUN_ID,
        "symbols": ["xyz:BRENTOIL"],
    }


def _open_health() -> dict[str, object]:
    """Return backend-authored protected open health."""
    return {
        "final_state": "OPEN",
        "faults": 0,
        "open_order_ids": [_STOP_OID],
        "position_size_signed": 8.02,
        "protected_if_open": True,
        "stop_oid": _STOP_OID,
    }


def _flat_health() -> dict[str, object]:
    """Return backend-authored flat cleanup health."""
    return {
        "final_state": "FLAT",
        "faults": 0,
        "open_order_ids": [],
        "position_size_signed": 0.0,
        "protected_if_open": True,
        "stop_oid": None,
    }


def _venue() -> dict[str, object]:
    """Return exact read-only venue protection evidence."""
    return {
        "observed_at_utc": "2026-08-20T10:00:00+00:00",
        "authority": {
            "execution_authority": "none",
            "execution_client_constructed": False,
        },
        "identity": {
            "active_profile_id": _PROFILE,
            "active_profile_fingerprint": _FINGERPRINT,
            "network": "mainnet",
        },
        "assets": [
            {
                "symbol": "xyz:BRENTOIL",
                "position": {"size_signed": 8.02},
                "open_orders": [{"oid": _STOP_OID, "size": 8.02, "reduce_only": True}],
                "protection": {
                    "status": "protected",
                    "full_reduce_only_stop_coverage": True,
                    "qualified_stop_order_ids": [_STOP_OID],
                },
                "ledger_reconciliation": {
                    "matches": True,
                    "orders_match": True,
                    "position_matches": True,
                    "venue_owned_order_ids": [_STOP_OID],
                },
            }
        ],
    }


def _flat_venue() -> dict[str, object]:
    """Return exact read-only flat and order-free venue evidence."""
    venue = _venue()
    asset = venue["assets"][0]
    asset["position"] = {"size_signed": 0.0}
    asset["open_orders"] = []
    asset["protection"] = {
        "status": "flat",
        "full_reduce_only_stop_coverage": True,
        "qualified_stop_order_ids": [],
    }
    asset["ledger_reconciliation"]["venue_owned_order_ids"] = []
    return venue


def _ledger_evidence(rows: int = 2) -> dict[str, object]:
    """Return one authenticated complete-prefix identity."""
    return {
        "path": "/tmp/xyz:brentoil.jsonl",
        "bytes": rows * 100,
        "sha256": "b" * 64,
        "rows": rows,
        "frozen_prefix_verified": True,
    }


def _adopted_epoch_rows() -> list[dict[str, object]]:
    """Return one exact adopted-open state and its unique funding settlement."""
    identity = {
        "profile_id": _ASSET_PROFILE,
        "profile_fingerprint": _ASSET_FINGERPRINT,
        "run_id": _ADOPTED_RUN_ID,
        "observed_at_utc": "2026-08-20T10:30:00+00:00",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
    }
    return [
        {
            **identity,
            "sequence": 7,
            "event_type": "configuration_identity",
            "payload": {
                "symbol": "xyz:BRENTOIL",
                "strategy_name": "multi_strategy_bidirectional_router",
            },
        },
        {
            **identity,
            "sequence": 8,
            "event_type": "state_transition",
            "payload": {
                "state": "OPEN",
                "entry_oid": 520642502465,
                "stop_oid": _STOP_OID,
                "target_oid": None,
                "position_size_signed": 8.02,
                "execution_plan": {"strategy_id": _STRATEGY},
            },
        },
        {
            **identity,
            "sequence": 9,
            "event_type": "funding",
            "payload": {
                "venue_timestamp_ms": 1787217300000,
                "usdc_delta": 0.003101,
            },
        },
    ]


def _report_only_contract() -> dict[str, object]:
    """Return the authority-none contract shared by fixtures."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }


def _checkpoint_contract() -> dict[str, object]:
    """Return the backend checkpoint's distinct report-only schema."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "balance_gate": False,
        "performance_gate": False,
    }


def _is_exit_fee(row: dict[str, object]) -> bool:
    """Return whether a row is the exact exit fee event."""
    payload = row.get("payload")
    return (
        row.get("event_type") == "fee"
        and isinstance(payload, dict)
        and payload.get("oid") == 520700000001
    )
