"""Exact venue-identity recovery for legacy Apex MM live fills."""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest

from hypervector.live.hyperliquid_protocol import SolFill


def _module() -> ModuleType:
    return importlib.import_module("hypervector.research.apex_mm_legacy_fill_recovery")


def _venue_fill(*, trade_id: int = 7_001, size: float = 0.00019) -> SolFill:
    return SolFill(
        oid=101,
        price=63_090.0,
        size=size,
        side="A",
        timestamp_ms=1_785_586_383_357,
        fee_usd=0.001726,
        fee_token="USDC",
        closed_pnl_usd=0.0,
        crossed=False,
        direction="Open Short",
        transaction_hash="0xabc",
        trade_id=trade_id,
    )


def _record(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    run_id: str = "run-a",
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "run_id": run_id,
        "payload": payload,
    }


def _legacy_rows() -> list[dict[str, object]]:
    fill = _venue_fill()
    identity = {
        "oid": fill.oid,
        "venue_timestamp_ms": fill.timestamp_ms,
        "price": fill.price,
        "size": fill.size,
        "side": fill.side,
        "direction": fill.direction,
        "closed_pnl_usd": fill.closed_pnl_usd,
        "crossed": fill.crossed,
        "transaction_hash": fill.transaction_hash,
        "fee_usd": fill.fee_usd,
        "fee_token": fill.fee_token,
    }
    return [
        _record(1, "fill", identity),
        _record(
            2,
            "fee",
            {
                "source": "fill",
                "oid": fill.oid,
                "venue_timestamp_ms": fill.timestamp_ms,
                "fee_usd": fill.fee_usd,
            },
        ),
        _record(
            3,
            "execution_quality",
            {
                "oid": fill.oid,
                "fill_timestamp_ms": fill.timestamp_ms,
                "fill_price": fill.price,
                "fill_size": fill.size,
            },
        ),
        _record(
            4,
            "fill_markout",
            {
                "oid": fill.oid,
                "fill_timestamp_ms": fill.timestamp_ms,
                "fill_price": fill.price,
                "fill_size": fill.size,
            },
        ),
        _record(5, "fill", identity, run_id="another-run"),
    ]


def test_exact_venue_match_enriches_linked_rows_without_mutating_ledger() -> None:
    """A unique venue match supplies one TID to every linked metric row."""
    rows = _legacy_rows()

    enriched, evidence = _module().recover_legacy_apex_fill_trade_ids(
        rows,
        venue_fills=[_venue_fill()],
        run_id="run-a",
    )

    assert "trade_id" not in rows[0]["payload"]
    assert [row["payload"]["trade_id"] for row in enriched[:4]] == [7_001] * 4
    assert "trade_id" not in enriched[4]["payload"]
    assert evidence["recovered_fill_count"] == 1
    assert evidence["venue_result_count"] == 1
    assert evidence["matches"] == [
        {
            "oid": 101,
            "trade_id": 7_001,
            "transaction_hash": "0xabc",
            "venue_timestamp_ms": 1_785_586_383_357,
        }
    ]
    assert len(evidence["venue_result_sha256"]) == 64


def test_recovery_refuses_a_missing_exact_venue_fill() -> None:
    """A timestamp/order approximation cannot become strategy evidence."""
    rows = _legacy_rows()
    rows[0]["payload"]["transaction_hash"] = "0xdifferent"

    with pytest.raises(
        ValueError,
        match="no exact venue fill matches legacy Apex fill sequence 1",
    ):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )


def test_recovery_refuses_ambiguous_exact_venue_fills() -> None:
    """Two venue TIDs for one legacy row remain unresolved evidence."""
    with pytest.raises(ValueError, match="multiple exact venue fills match"):
        _module().recover_legacy_apex_fill_trade_ids(
            _legacy_rows(),
            venue_fills=[_venue_fill(), _venue_fill(trade_id=7_002)],
            run_id="run-a",
        )


def test_recovery_refuses_conflicting_existing_trade_id() -> None:
    """Recovery cannot replace an identity already claimed by the ledger."""
    rows = _legacy_rows()
    rows[0]["payload"]["trade_id"] = 9_999

    with pytest.raises(ValueError, match="conflicting trade_id"):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )


def test_recovery_refuses_a_run_without_legacy_fills() -> None:
    """A legacy recovery artifact must recover at least one fill."""
    with pytest.raises(ValueError, match="run run-a has no Apex fills to recover"):
        _module().recover_legacy_apex_fill_trade_ids(
            [_record(1, "position", {"size_signed": 0.0})],
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )


def test_recovery_refuses_same_order_time_with_different_trade_ids() -> None:
    """Legacy linked metrics cannot guess between same-time partial fills."""
    rows = _legacy_rows()
    second = dict(rows[0]["payload"])
    second["size"] = 0.0002
    rows.append(_record(6, "fill", second))

    with pytest.raises(ValueError, match="metrics are ambiguous for oid/time"):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[
                _venue_fill(),
                _venue_fill(trade_id=7_002, size=0.0002),
            ],
            run_id="run-a",
        )


def test_recovery_refuses_an_orphan_linked_metric() -> None:
    """A metric cannot borrow identity from a different fill."""
    rows = _legacy_rows()
    rows.append(
        _record(
            6,
            "execution_quality",
            {"oid": 999, "fill_timestamp_ms": 123},
        )
    )

    with pytest.raises(ValueError, match="has no exact run fill"):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )


def test_recovery_refuses_malformed_linked_identity() -> None:
    """Boolean order IDs cannot enter exact identity matching."""
    rows = _legacy_rows()
    rows[2]["payload"]["oid"] = True

    with pytest.raises(ValueError, match="legacy Apex oid must be an integer"):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )


def test_recovery_refuses_a_non_object_payload() -> None:
    """Malformed append-only rows remain explicit audit failures."""
    rows = _legacy_rows()
    rows.append(_record(6, "position", {}))
    rows[-1]["payload"] = "invalid"

    with pytest.raises(ValueError, match="payload must be an object"):
        _module().recover_legacy_apex_fill_trade_ids(
            rows,
            venue_fills=[_venue_fill()],
            run_id="run-a",
        )
