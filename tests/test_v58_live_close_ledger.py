"""Generic authenticated accounting for exact V58 live closes."""

from __future__ import annotations

from importlib import import_module, util


_RUN_ID = "bidirectional-live-1787166474078"
_PROFILE_ID = "multi_asset_growth_first_5000_eight_asset_incremental_v58_xyz:brentoil"
_FINGERPRINT = "c" * 64
_SUCCESSOR_RUN_ID = "bidirectional-live-1787272893887"
_SUCCESSOR_PROFILE_ID = f"{_PROFILE_ID}_successor"
_SUCCESSOR_FINGERPRINT = "d" * 64


def test_brentoil_long_reconciles_exact_raw_cash_events() -> None:
    """A namespaced long must reconcile fills, fees, and funding exactly."""
    module_name = "hypervector.research.v58_live_close_ledger"
    assert util.find_spec(module_name) is not None, (
        "generic live-close ledger is missing"
    )
    module = import_module(module_name)

    result = module.reconcile_live_close_ledger(
        _ledger_rows(),
        _close(),
        run_id=_RUN_ID,
        profile_id=_PROFILE_ID,
        profile_fingerprint=_FINGERPRINT,
        symbol="xyz:BRENTOIL",
        side="long",
    )

    assert result.entry_oid == 520642502465
    assert result.exit_oid == 520700000001
    assert len(result.rows) == 6
    assert module.fill_time(module.fill_events(result.rows, result.exit_oid)) == (
        1787219115000
    )


def test_open_brentoil_entry_reconciles_before_exit_exists() -> None:
    """An open lifecycle must authenticate its entry fill and fee independently."""
    module = import_module("hypervector.research.v58_live_close_ledger")
    rows = _ledger_rows()[:2]

    result = module.reconcile_live_entry_ledger(
        rows,
        _close(),
        run_id=_RUN_ID,
        profile_id=_PROFILE_ID,
        profile_fingerprint=_FINGERPRINT,
        symbol="xyz:BRENTOIL",
        side="long",
    )

    assert result.entry_oid == 520642502465
    assert result.entry_fill_count == 1
    assert result.entry_fee_usd == 0.063447


def test_adopted_close_reconciles_entry_and_exit_across_exact_run_identities() -> None:
    """A restart may own the exit while retaining the original entry provenance."""
    module = import_module("hypervector.research.v58_live_close_ledger")
    rows = _ledger_rows()
    for row in rows[3:]:
        row["run_id"] = _SUCCESSOR_RUN_ID
        row["profile_id"] = _SUCCESSOR_PROFILE_ID
        row["profile_fingerprint"] = _SUCCESSOR_FINGERPRINT

    result = module.reconcile_live_close_ledger_epochs(
        rows,
        _close(),
        identities=(
            module.LiveLedgerIdentity(_RUN_ID, _PROFILE_ID, _FINGERPRINT),
            module.LiveLedgerIdentity(
                _SUCCESSOR_RUN_ID,
                _SUCCESSOR_PROFILE_ID,
                _SUCCESSOR_FINGERPRINT,
            ),
        ),
        symbol="xyz:BRENTOIL",
        side="long",
    )

    assert result.entry_oid == 520642502465
    assert result.exit_oid == 520700000001
    assert {row["run_id"] for row in result.rows} == {
        _RUN_ID,
        _SUCCESSOR_RUN_ID,
    }


def _close() -> dict[str, object]:
    """Return one internally reconciled BRENTOIL close reflection."""
    return {
        "lifecycle_id": "xyz:BRENTOIL:520642502465",
        "entry": {
            "price": 91.565,
            "size": 8.02,
            "venue_timestamp_ms": 1787215515053,
        },
        "exit": {
            "price": 92.0,
            "size": 8.02,
            "venue_timestamp_ms": 1787219115000,
        },
        "gross_market_pnl_usd": 3.4887,
        "fees_usd": 0.127184,
        "funding_usd": 0.007814,
    }


def _ledger_rows() -> list[dict[str, object]]:
    """Return exact raw entry, exit, fee, and funding events."""
    events = [
        (
            "fill",
            _fill(
                520642502465,
                1,
                1787215515053,
                91.565,
                "Open Long",
                0.0,
                0.063447,
            ),
        ),
        ("fee", _fee(520642502465, 1, 1787215515053, 0.063447)),
        ("funding", {"venue_timestamp_ms": 1787216400000, "usdc_delta": 0.007814}),
        (
            "fill",
            _fill(
                520700000001,
                2,
                1787219115000,
                92.0,
                "Close Long",
                3.4887,
                0.063737,
            ),
        ),
        ("fee", _fee(520700000001, 2, 1787219115000, 0.063737)),
        ("heartbeat", {}),
    ]
    return [
        _row(index, event_type, payload)
        for index, (event_type, payload) in enumerate(events, 1)
    ]


def _row(
    sequence: int, event_type: str, payload: dict[str, object]
) -> dict[str, object]:
    """Bind one event to the frozen asset-ledger identity."""
    return {
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-20T09:45:00+00:00",
        "profile_id": _PROFILE_ID,
        "profile_fingerprint": _FINGERPRINT,
        "run_id": _RUN_ID,
        "payload": payload,
    }


def _fill(
    oid: int,
    trade_id: int,
    timestamp_ms: int,
    price: float,
    direction: str,
    closed_pnl_usd: float,
    fee_usd: float,
) -> dict[str, object]:
    """Return one exact venue fill payload."""
    return {
        "oid": oid,
        "trade_id": trade_id,
        "venue_timestamp_ms": timestamp_ms,
        "price": price,
        "size": 8.02,
        "direction": direction,
        "closed_pnl_usd": closed_pnl_usd,
        "fee_usd": fee_usd,
    }


def _fee(
    oid: int, trade_id: int, timestamp_ms: int, fee_usd: float
) -> dict[str, object]:
    """Return one fill-bound fee payload."""
    return {
        "source": "fill",
        "oid": oid,
        "trade_id": trade_id,
        "venue_timestamp_ms": timestamp_ms,
        "fee_usd": fee_usd,
    }
