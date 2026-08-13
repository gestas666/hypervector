"""Restart-continuity tests for the multi-asset live audit."""

from __future__ import annotations

import pytest

from cohort_live_audit_trade_fixture import traded_asset_rows
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from test_multi_asset_live_audit import (
    _RUN_ID,
    _SYMBOLS,
    _asset_rows,
    _cohort_rows_with_trade,
)


def test_restart_audit_separates_current_health_from_trade_history() -> None:
    """A restart retains prior fills without treating them as new-run activity."""
    asset_rows = {symbol: _asset_rows(symbol) for symbol in _SYMBOLS}
    asset_rows["BTC"] = _append_run(
        traded_asset_rows("prior-run"),
        asset_rows["BTC"],
    )

    report = audit_multi_asset_live_run(
        _with_prior_cohort_identity(_cohort_rows_with_trade()),
        asset_rows,
        run_id=_RUN_ID,
    )

    assert report["run"]["run_id"] == _RUN_ID
    assert report["runtime"]["stop_reasons"] == {"operator_stop": 4}
    assert report["execution"]["scope"] == "compatible_profile_history"
    assert report["execution"]["fills"] == 2
    assert report["execution"]["current_run_fills"] == 0
    assert report["execution"]["history_run_ids"] == ["prior-run", _RUN_ID]
    assert report["execution"]["closed_trades"] == 1
    assert report["execution"]["net_pnl_usd"] == pytest.approx(0.97)
    assert report["coverage"] == {"complete": True, "technical_gaps": []}
    assert report["health"]["assets"]["BTC"]["final_state"] == "STOPPED"


def test_open_position_costs_exclude_previous_closed_lifecycle() -> None:
    """Open economics exclude realized PnL and costs from an earlier lifecycle."""
    rows = _open_cohort_rows()
    current = traded_asset_rows(_RUN_ID)[:8]
    current[4]["payload"]["oid"] = 33
    current[5]["payload"].update(
        {"oid": 33, "trade_id": 303, "price": 105.0, "fee_usd": 0.01}
    )
    report = audit_multi_asset_live_run(
        _with_prior_cohort_identity(rows),
        {
            "BTC": _append_run(traded_asset_rows("prior-run"), current),
            **{symbol: _asset_rows(symbol) for symbol in _SYMBOLS if symbol != "BTC"},
        },
        run_id=_RUN_ID,
    )

    assert report["execution"]["open_positions"] == [_expected_open_position()]


def _with_prior_cohort_identity(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Prepend the compatible configuration identity that authored prior fills."""
    current = next(row for row in rows if row["event_type"] == "configuration_identity")
    prior = dict(current)
    prior["run_id"] = "prior-run"
    prior["observed_at_utc"] = "2026-08-01T15:59:58+00:00"
    combined = [prior, *[dict(row) for row in rows]]
    for sequence, row in enumerate(combined, start=1):
        row["sequence"] = sequence
    return combined


def _open_cohort_rows() -> list[dict[str, object]]:
    rows = _cohort_rows_with_trade()
    for row in rows:
        if row["event_type"] != "cohort_snapshot":
            continue
        btc = row["payload"]["assets"][0]
        btc.update(_open_asset_fields())
        row["payload"]["open_position_count"] = 1
        row["payload"]["recent_fills"].append(_open_fill())
    return rows


def _open_asset_fields() -> dict[str, object]:
    return {
        "state": "OPEN",
        "position_size_signed": 0.25,
        "position_side": "long",
        "entry_price": 105.0,
        "mark_price": 105.2,
        "liquidation_price": 84.0,
        "liquidation_distance_pct": 20.15,
        "margin_used_usd": 5.25,
        "position_value_usd": 26.30,
        "unrealized_pnl_usd": 0.05,
        "leverage": 5,
        "fees_net_usd": 0.03,
        "funding_net_usd": -0.01,
        "realized_pnl_usd": 1.0,
    }


def _open_fill() -> dict[str, object]:
    return {
        "symbol": "BTC",
        "trade_id": 303,
        "price": 105.0,
        "size": 0.25,
        "fee_usd": 0.01,
        "slippage_bps": 0.0,
        "acknowledgement_latency_ms": 40,
        "markout_bps": None,
    }


def _expected_open_position() -> dict[str, object]:
    return {
        "symbol": "BTC",
        "side": "long",
        "size_signed": 0.25,
        "entry_price": 105.0,
        "mark_price": 105.2,
        "market_reference_price": 105.2,
        "mark_price_source": "venue_position_value_div_size",
        "market_reference_skew_bps": 0.0,
        "liquidation_price": 84.0,
        "liquidation_distance_pct": pytest.approx(20.152091254752854),
        "margin_used_usd": 5.25,
        "position_value_usd": 26.30,
        "unrealized_pnl_usd": 0.05,
        "fees_usd": 0.01,
        "funding_usd": 0.0,
        "realized_pnl_usd": 0.0,
        "active_lifecycle_marked_net_pnl_usd": pytest.approx(0.04),
        "profile_history_fees_usd": 0.03,
        "profile_history_funding_usd": -0.01,
        "profile_history_realized_pnl_usd": 1.0,
        "cost_scope": "active_lifecycle",
        "leverage": 5,
        "status": "provisional_open",
    }


def _append_run(
    prior: list[dict[str, object]],
    current: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Append a current run while preserving one contiguous physical ledger."""
    return prior + [
        {**row, "sequence": len(prior) + offset}
        for offset, row in enumerate(current, start=1)
    ]
