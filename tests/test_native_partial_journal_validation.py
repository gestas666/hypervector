"""Independently check partial-lifecycle accounting and ambiguous identity handling."""

from collections.abc import Mapping

import pytest
from test_asset_live_journal import _record

from hypervector.live.asset_live_journal import build_live_journal
from hypervector.live.asset_live_journal_orders import (
    accepted_entry_acks,
    close_fill_records,
    exit_order_ids,
    intent_for_ack,
    intent_for_oid,
    partial_exit_oids,
    weighted_exit_reference,
)

Record = dict[str, object]


def append(rows: list[Record], event: str, **body: object) -> Record:
    """Append one correctly sequenced synthetic ledger record."""
    row = _record(len(rows) + 1, event, body)
    rows.append(row)
    return row


def entered_lifecycle() -> list[Record]:
    """Build an independently specified two-unit long entry."""
    rows: list[Record] = []
    append(rows, "reconciliation", account_value_usd=1000.0)
    append(
        rows,
        "order_intent",
        operation="entry",
        client_order_id="entry",
        side="long",
        mark_price=100.0,
    )
    append(
        rows,
        "order_acknowledgement",
        operation="entry",
        client_order_id="entry",
        accepted=True,
        oid=1,
    )
    append(
        rows,
        "fill",
        oid=1,
        size=2.0,
        price=100.0,
        fee_usd=0.2,
        venue_timestamp_ms=1000,
        direction="Open Long",
        closed_pnl_usd=0.0,
    )
    return rows


def partial_lifecycle() -> list[Record]:
    """Reduce the specified entry by one half-unit."""
    rows = entered_lifecycle()
    append(
        rows,
        "order_intent",
        operation="reduce_only_close",
        client_order_id="partial",
        mark_price=100.5,
    )
    append(
        rows,
        "close",
        operation="reduce_only_close",
        client_order_id="partial",
        accepted=True,
        oid=2,
    )
    append(
        rows,
        "fill",
        oid=2,
        size=0.5,
        price=101.0,
        fee_usd=0.05,
        venue_timestamp_ms=2000,
        direction="Close Long",
        closed_pnl_usd=0.5,
    )
    append(rows, "close", oid=2, partial=True, verified_flat=False)
    return rows


def lifecycle() -> list[Record]:
    """Finish the independent partial lifecycle with a differently priced final exit."""
    rows = partial_lifecycle()
    append(
        rows,
        "order_intent",
        operation="reduce_only_close",
        client_order_id="final",
        mark_price=101.5,
    )
    append(
        rows, "close", operation="reduce_only_close", client_order_id="final", accepted=True, oid=3
    )
    append(
        rows,
        "fill",
        oid=3,
        size=1.5,
        price=102.0,
        fee_usd=0.15,
        venue_timestamp_ms=4000,
        direction="Close Long",
        closed_pnl_usd=3.0,
    )
    append(rows, "close", oid=3, verified_flat=True, reason="remaining")
    append(rows, "reconciliation", account_value_usd=1003.1)
    return rows


def body(row: Mapping[str, object]) -> dict[str, object]:
    """Narrow mutable synthetic payloads without casting runtime values."""
    value = row["payload"]
    assert isinstance(value, dict)
    return value


def test_multiple_exit_economics_have_independent_expected_values() -> None:
    """Weighted reference, realized gross, fees and holding time use all reductions."""
    rows = lifecycle()
    opened = build_live_journal(rows[:8])["open_lifecycles"][0]
    assert opened["realized_exit_pnl_usd"] == 0.5
    assert opened["fees_usd"] == 0.25
    trade = build_live_journal(rows)["trades"][0]
    assert trade["exit"]["size"] == 2.0
    assert trade["exit"]["price"] == 101.75
    assert trade["exit"]["expected_reference_price"] == 101.25
    assert trade["exit"]["slippage_bps"] == pytest.approx(-0.5 / 101.25 * 10000)
    assert trade["closed_pnl_before_friction_usd"] == 3.5
    assert trade["fees_usd"] == 0.4
    assert trade["net_pnl_usd"] == 3.1
    assert trade["holding_time_ms"] == 3000
    assert trade["account_value_change_usd"] == pytest.approx(3.1)


@pytest.mark.parametrize("size", [1.0, 1.6])
def test_flat_without_complete_quantity_cannot_be_counted_as_a_closed_trade(size: float) -> None:
    """Missing or excessive exit fills keep economics provisional."""
    rows = lifecycle()
    body(rows[10])["size"] = size
    report = build_live_journal(rows)
    assert report["trades"] == []
    assert report["open_lifecycles"][0]["status"] == "close_incomplete"
    assert "net_pnl_usd" not in report["open_lifecycles"][0]


def test_mixed_final_owned_orders_include_prior_partial_reduction() -> None:
    """A partial scheduled exit and subsequent bracket fills belong to one lifecycle."""
    rows = lifecycle()
    body(rows[11]).pop("oid")
    body(rows[11])["owned_oids"] = [3, 4]
    final = rows.pop(10)
    body(final)["size"] = 1.0
    rows.insert(10, final)
    extra = _record(1, "fill", {**body(final), "oid": 4, "size": 0.5})
    rows.insert(11, extra)
    for index, row in enumerate(rows, 1):
        row["sequence"] = index
    trade = build_live_journal(rows)["trades"][0]
    assert trade["exit_oids"] == [2, 3, 4] and trade["exit_oid"] is None
    assert trade["exit"]["expected_reference_price"] is None


def test_repeated_entry_acknowledgement_counts_once_and_conflicts_are_rejected() -> None:
    """A durable order remains one trade across restart acknowledgements."""
    rows = lifecycle()
    append(
        rows, "order_acknowledgement", **{**body(rows[2]), "operation": "entry_restart_recovery"}
    )
    assert len(accepted_entry_acks(rows)) == 1
    assert len(build_live_journal(rows)["trades"]) == 1
    body(rows[-1])["client_order_id"] = "foreign"
    with pytest.raises(ValueError, match="conflicting client identities"):
        accepted_entry_acks(rows)


@pytest.mark.parametrize("case", ["flat", "missing_intent", "wrong_intent", "invalid_oid"])
def test_partial_identity_requires_a_durable_close_request(case: str) -> None:
    """An arbitrary partial label cannot claim another order's economics."""
    rows = lifecycle()
    if case == "flat":
        body(rows[7])["verified_flat"] = True
    elif case == "missing_intent":
        body(rows[5])["client_order_id"] = "missing"
    elif case == "wrong_intent":
        body(rows[4])["operation"] = "target"
    else:
        body(rows[7])["oid"] = True
    with pytest.raises(ValueError, match="partial close"):
        partial_exit_oids(rows)


def test_missing_identity_and_reference_remain_unavailable() -> None:
    """Missing attribution inputs produce no invented decision prices or ownership."""
    rows = lifecycle()
    assert intent_for_ack(rows, rows[7]) is None
    assert intent_for_oid(rows, 999) is None
    assert weighted_exit_reference(rows, []) is None
    body(rows[11]).pop("oid")
    with pytest.raises(ValueError, match="owned_oids must be a list"):
        exit_order_ids(rows[11], rows)


@pytest.mark.parametrize("case", ["direction", "zero", "negative"])
def test_contradictory_owned_exit_fill_is_rejected(case: str) -> None:
    """Owned identity alone cannot validate an invalid fill."""
    rows = lifecycle()
    if case == "direction":
        body(rows[6])["direction"] = "Open Long"
        with pytest.raises(ValueError, match="wrong direction"):
            close_fill_records(rows, [2], "long")
    else:
        body(rows[6])["size"] = 0.0 if case == "zero" else -0.5
        with pytest.raises(ValueError, match="size must be positive"):
            weighted_exit_reference(rows, [rows[6]])
