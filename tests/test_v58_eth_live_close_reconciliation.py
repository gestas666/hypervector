"""Exact post-close reconciliation for the first V58 ETH lifecycle."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from importlib import import_module, util
import json
from pathlib import Path

import pytest

from v58_eth_close_ledger_fixtures import (
    ActiveCloseFixture as _ActiveCloseFixture,
    ClosedContextFixture as _ClosedContextFixture,
    ProtectiveStopFixture as _ProtectiveStopFixture,
    protective_stop_context as _protective_stop_context,
    split_active_exit_fills as _split_active_exit_fills,
)
from v58_eth_close_source_fixtures import (
    flat_venue as _flat_venue,
    observer_resolution as _observer_resolution,
    preregistration as _preregistration,
    source_files as _source_files,
)


def test_active_close_reconciles_timing_economics_and_cleanup() -> None:
    """An active close must bind decision, submission, fill, and cleanup truth."""
    module_name = "hypervector.research.v58_eth_live_close_reconciliation"
    spec = util.find_spec(module_name)
    assert spec is not None, "V58 ETH live-close reconciler is missing"
    module = import_module(module_name)

    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        deepcopy(_ClosedContextFixture.value),
        deepcopy(_ActiveCloseFixture.rows),
        _flat_venue(),
        _observer_resolution(),
    )

    assert report["status"] == "reconciled"
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
        "approval_requested": False,
    }
    actual = report["actual_live_close"]
    assert actual["lifecycle_id"] == "ETH:520161109446"
    assert actual["exit_reason"] == "maximum_hold_seconds"
    assert actual["decision_time_ms"] == 1787216100000
    assert actual["submission_time_ms"] == 1787216101200
    assert actual["acknowledgement_time_ms"] == 1787216102200
    assert actual["fill_time_ms"] == 1787216102600
    assert actual["submission_to_fill_ms"] == 1400
    assert actual["fill_price"] == 2261.1
    assert actual["exit_slippage_bps"] == 1.25
    assert actual["entry_notional_usd"] == 729.37513
    assert actual["net_pnl_usd"] == 20.0
    assert actual["net_return_on_entry_notional_bps"] == (20.0 / 729.37513 * 10_000.0)
    assert report["cleanup"]["ledger_flat_order_free"] is True
    assert report["cleanup"]["venue_eth_flat_order_free"] is True
    observer = report["observer_comparison"]
    _assert_observer_identity(observer)
    assert observer["notional_usd"] == 750.0
    assert observer["net_return_bps"] == 240.0
    assert observer["simulated_net_pnl_usd"] == 18.0
    assert observer["actual_orders_or_fills_claimed"] is False
    assert report["strategy_change_supported"] is False


def _assert_observer_identity(observer: dict[str, object]) -> None:
    """Require the exact frozen observer lifecycle identity."""
    assert (
        observer["strategy_id"]
        == "eth_breakout_precompression_pullback_bidirectional_v1"
    )
    assert observer["symbol"] == "ETH"
    assert observer["side"] == "long"
    assert observer["decision_time_ms"] == 1787172900000


def test_close_accepts_explicit_no_approval_requested_contract() -> None:
    """The real preregistration's explicit no-approval field must remain frozen."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    preregistration = _preregistration()
    contract = preregistration["contract"]
    assert isinstance(contract, dict)
    contract["approval_requested"] = False

    report = module.build_v58_eth_live_close_reconciliation(
        preregistration,
        deepcopy(_ClosedContextFixture.value),
        deepcopy(_ActiveCloseFixture.rows),
        _flat_venue(),
        _observer_resolution(),
    )

    assert report["contract"]["approval_requested"] is False


def test_protective_stop_uses_resting_order_submission_and_fill_trigger() -> None:
    """A venue-native stop has a fill trigger and an earlier resting submission."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        _protective_stop_context(),
        deepcopy(_ProtectiveStopFixture.rows),
        _flat_venue(),
        _observer_resolution() | {"exit_reason": "protective_stop"},
    )

    actual = report["actual_live_close"]
    assert actual["exit_reason"] == "protective_stop"
    assert actual["decision_time_source"] == "venue_native_protective_stop_fill"
    assert actual["decision_time_ms"] == 1787173800000
    assert actual["submission_time_ms"] == 1787172921000
    assert actual["acknowledgement_time_ms"] == 1787172922000
    assert actual["fill_time_ms"] == 1787173800000


def test_close_rejects_ledger_from_a_different_profile_fingerprint() -> None:
    """Close evidence must match the preregistered runtime fingerprint exactly."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = deepcopy(_ActiveCloseFixture.rows)
    for row in rows:
        row["profile_fingerprint"] = "f" * 64

    with pytest.raises(ValueError, match="ledger profile identity differs"):
        module.build_v58_eth_live_close_reconciliation(
            _preregistration(),
            deepcopy(_ClosedContextFixture.value),
            rows,
            _flat_venue(),
            _observer_resolution(),
        )


def test_close_accepts_exact_eth_asset_profile_identity() -> None:
    """The aggregate V58 identity must bind its symbol-specific ETH ledger."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = deepcopy(_ActiveCloseFixture.rows)
    for row in rows:
        row["profile_id"] = (
            "multi_asset_growth_first_5000_eight_asset_incremental_v58_eth"
        )
        row["profile_fingerprint"] = (
            "b443e05b2c7d41a61ae0688f36ddc4e0295a56910e90485742d5014b98e0ed85"
        )

    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        deepcopy(_ClosedContextFixture.value),
        rows,
        _flat_venue(),
        _observer_resolution(),
    )

    assert report["status"] == "reconciled"


def test_close_rejects_reflected_funding_without_raw_ledger_support() -> None:
    """Reflected funding must reconcile to authenticated lifecycle events."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = [
        row
        for row in deepcopy(_ActiveCloseFixture.rows)
        if row.get("event_type") != "funding"
    ]

    with pytest.raises(ValueError, match="ledger funding differs"):
        module.build_v58_eth_live_close_reconciliation(
            _preregistration(),
            deepcopy(_ClosedContextFixture.value),
            rows,
            _flat_venue(),
            _observer_resolution(),
        )


def test_close_rejects_reflected_fees_without_raw_fill_fee_events() -> None:
    """Reflected fees must reconcile to authenticated entry and exit fee events."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = [
        row
        for row in deepcopy(_ActiveCloseFixture.rows)
        if row.get("event_type") != "fee"
    ]

    with pytest.raises(ValueError, match="ledger fee identity differs"):
        module.build_v58_eth_live_close_reconciliation(
            _preregistration(),
            deepcopy(_ClosedContextFixture.value),
            rows,
            _flat_venue(),
            _observer_resolution(),
        )


def test_close_rejects_reflected_entry_without_raw_fill() -> None:
    """The reflected entry leg must reconcile to authenticated raw fills."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = [
        row
        for row in deepcopy(_ActiveCloseFixture.rows)
        if not (
            row.get("event_type") == "fill"
            and row.get("payload", {}).get("oid") == 520161109446
        )
    ]

    with pytest.raises(ValueError, match="entry fill differs"):
        module.build_v58_eth_live_close_reconciliation(
            _preregistration(),
            deepcopy(_ClosedContextFixture.value),
            rows,
            _flat_venue(),
            _observer_resolution(),
        )


def test_close_accepts_split_exit_fills_under_one_order() -> None:
    """One close order may resolve through multiple exact venue fills."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        deepcopy(_ClosedContextFixture.value),
        _split_active_exit_fills(),
        _flat_venue(),
        _observer_resolution(),
    )

    actual = report["actual_live_close"]
    assert actual["exit_fill_count"] == 2
    assert actual["fill_time_ms"] == 1787216102601
    assert actual["net_pnl_usd"] == 20.0


def test_close_derives_missing_order_ids_from_lifecycle_and_exact_fills() -> None:
    """Production reflected legs omit OIDs but retain exact identity and fills."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    context = deepcopy(_ClosedContextFixture.value)
    close = context["actual_close_reconciliation"]
    assert isinstance(close, dict)
    for label in ("entry", "exit"):
        leg = close[label]
        assert isinstance(leg, dict)
        del leg["oid"]

    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        context,
        _split_active_exit_fills(),
        _flat_venue(),
        _observer_resolution(),
    )

    actual = report["actual_live_close"]
    assert actual["exit_fill_count"] == 2
    assert actual["fill_time_ms"] == 1787216102601


def test_close_accepts_venue_fill_before_client_acknowledgement() -> None:
    """Venue fill time may precede receipt of the filled order response."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = deepcopy(_ActiveCloseFixture.rows)
    acknowledgement = next(
        row
        for row in rows
        if row.get("event_type") == "close"
        and row.get("payload", {}).get("accepted") is True
    )
    acknowledgement["observed_at_utc"] = "2026-08-20T08:55:02.900000+00:00"

    report = module.build_v58_eth_live_close_reconciliation(
        _preregistration(),
        deepcopy(_ClosedContextFixture.value),
        rows,
        _flat_venue(),
        _observer_resolution(),
    )

    actual = report["actual_live_close"]
    assert actual["fill_time_ms"] == 1787216102600
    assert actual["acknowledgement_time_ms"] == 1787216102900


def test_close_rejects_fee_bound_to_the_wrong_fill_trade_id() -> None:
    """Correct fee dollars cannot be attributed to a different venue fill."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation")
    rows = deepcopy(_ActiveCloseFixture.rows)
    exit_fee = next(
        row
        for row in rows
        if row.get("event_type") == "fee"
        and row.get("payload", {}).get("oid") == 520200000000
    )
    payload = exit_fee["payload"]
    assert isinstance(payload, dict)
    payload["trade_id"] = 9999

    with pytest.raises(ValueError, match="fee identity differs"):
        module.build_v58_eth_live_close_reconciliation(
            _preregistration(),
            deepcopy(_ClosedContextFixture.value),
            rows,
            _flat_venue(),
            _observer_resolution(),
        )


def test_source_bound_loader_authenticates_frozen_prefixes(tmp_path: Path) -> None:
    """Publication inputs must preserve preregistered prefixes and exact outputs."""
    module_name = "hypervector.research.v58_eth_live_close_reconciliation_io"
    spec = util.find_spec(module_name)
    assert spec is not None, "V58 ETH close source-bound loader is missing"
    module = import_module(module_name)
    paths = _source_files(tmp_path)

    report = module.load_v58_eth_live_close_reconciliation(
        paths["preregistration"],
        expected_preregistration_sha256=paths["preregistration_sha256"],
        continuous_path=paths["continuous"],
        venue_path=paths["venue"],
        observer_status_path=paths["observer_status"],
        observer_provenance_path=paths["observer_provenance"],
        expected_observer_provenance_sha256=paths["observer_provenance_sha256"],
        generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )

    assert report["generated_at_utc"] == "2026-08-20T09:00:00+00:00"
    evidence = report["source_evidence"]
    assert evidence["live_eth_ledger"]["frozen_prefix_verified"] is True
    assert evidence["prospective_observer_ledger"]["frozen_prefix_verified"] is True
    assert evidence["live_eth_ledger"]["rows"] == len(_ActiveCloseFixture.rows) + 1
    assert report["actual_live_close"]["net_pnl_usd"] == 20.0


def test_source_bound_loader_rejects_changed_frozen_live_prefix(tmp_path: Path) -> None:
    """Mutated entry-era evidence must fail before close publication."""
    module = import_module("hypervector.research.v58_eth_live_close_reconciliation_io")
    paths = _source_files(tmp_path)
    prereg = json.loads(paths["preregistration"].read_text())
    live = Path(prereg["source_prefixes"]["live_eth_ledger"]["path"])
    raw = live.read_bytes()
    live.write_bytes(b"X" + raw[1:])

    with pytest.raises(ValueError, match="authenticated prefix"):
        module.load_v58_eth_live_close_reconciliation(
            paths["preregistration"],
            expected_preregistration_sha256=paths["preregistration_sha256"],
            continuous_path=paths["continuous"],
            venue_path=paths["venue"],
            observer_status_path=paths["observer_status"],
            observer_provenance_path=paths["observer_provenance"],
            expected_observer_provenance_sha256=paths["observer_provenance_sha256"],
            generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        )
