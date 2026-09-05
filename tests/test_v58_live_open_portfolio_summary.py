"""Portfolio-level reconciliation for simultaneous V58 open lifecycles."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.v58_live_open_lifecycles import (
    extract_v58_live_open_lifecycles,
)
from test_v58_live_backend_context import _payload_with_open_eth


def test_two_open_lifecycles_reconcile_one_portfolio_summary() -> None:
    """Individual protected positions must add to one explicit exposure view."""
    audit = _two_open_audit()

    result = extract_v58_live_open_lifecycles(
        audit,
        run_id="bidirectional-live-1787065473571",
        symbols=("BTC", "ETH", "HYPE", "xyz:SPCX"),
    )

    summary = result["portfolio_summary"]
    assert summary["symbols"] == ["BTC", "ETH"]
    assert summary["open_lifecycles"] == 2
    assert summary["owned_protective_stops"] == 2
    assert summary["entry_notional_usd"] == pytest.approx(1729.37513)
    assert summary["current_position_value_usd"] == pytest.approx(1735.96013)
    assert summary["margin_used_usd"] == pytest.approx(350.0)
    assert summary["marked_net_pnl_usd"] == pytest.approx(25.731151)
    assert summary["estimated_exit_now_net_usd"] == pytest.approx(24.908896281277)
    assert summary["estimated_stop_net_usd"] == pytest.approx(-9.043299240000036)
    assert summary["marked_to_stop_giveback_usd"] == pytest.approx(33.95219552127704)
    assert summary["actual_exit_fill_claim"] is False
    assert summary["loss_ceiling_claim"] is False
    assert summary["joint_probability_claim"] is False
    assert summary["execution_authority"] == "none"


def _two_open_audit() -> dict[str, object]:
    payload = _payload_with_open_eth()
    audit = payload["audit"]
    _add_exact_exposure_fields(audit)
    _add_open_btc(audit, payload["lifecycle"])
    return audit


def _add_exact_exposure_fields(audit: dict[str, object]) -> None:
    position = audit["execution"]["open_positions"][0]
    position.update(
        {
            "position_value_usd": 745.96013,
            "margin_used_usd": 150.0,
            "leverage": 5,
        }
    )
    reflection = audit["open_trade_reflections"]["trades"][0]
    reflection["marked_economics"] = deepcopy(position)


def _add_open_btc(audit: dict[str, object], lifecycle: dict[str, object]) -> None:
    execution = audit["execution"]
    reflections = audit["open_trade_reflections"]
    execution["open_lifecycles"] = 2
    reflections["open_lifecycles"] = 2
    execution["fill_details"].append(_btc_fill())
    execution["open_positions"].append(_btc_position())
    reflections["trades"].append(_btc_reflection())
    audit["health"]["assets"]["BTC"] = {
        "final_state": "OPEN",
        "position_size_signed": -0.02,
        "open_order_ids": [520161249035],
    }
    lifecycle["asset_states"]["BTC"] = "OPEN"


def _btc_fill() -> dict[str, object]:
    return {
        "trade_id": 741233744669591,
        "oid": 520161209446,
        "origin_run_id": "bidirectional-live-1787065473571",
        "strategy_id": "btc_short_v1",
        "symbol": "BTC",
        "operation": "entry",
        "side": "A",
        "direction": "Open Short",
        "venue_timestamp_ms": 1787173019582,
        "price": 50_000.0,
        "size": 0.02,
        "fee_usd": 0.45,
        "expected_price": 50_010.0,
        "slippage_bps": -2.0,
        "acknowledgement_latency_ms": 500,
        "markout_bps": 3.0,
        "markout_horizon_ms": 5_000,
    }


def _btc_position() -> dict[str, object]:
    return {
        "status": "provisional_open",
        "symbol": "BTC",
        "side": "short",
        "size_signed": -0.02,
        "entry_price": 50_000.0,
        "mark_price": 49_500.0,
        "mark_price_source": "venue_position_value_div_size",
        "position_value_usd": 990.0,
        "margin_used_usd": 200.0,
        "leverage": 5,
        "unrealized_pnl_usd": 10.0,
        "fees_usd": 0.45,
        "funding_usd": -0.05,
        "active_lifecycle_marked_net_pnl_usd": 9.5,
    }


def _btc_reflection() -> dict[str, object]:
    return {
        "lifecycle_id": "BTC:520161209446",
        "source_run_id": "bidirectional-live-1787065473571",
        "strategy_id": "btc_short_v1",
        "symbol": "BTC",
        "side": "short",
        "entry": {
            "price": 50_000.0,
            "size": 0.02,
            "venue_timestamp_ms": 1787173019582,
        },
        "marked_economics": _btc_position(),
        "protective_stop": {"oid": 520161249035, "trigger_price": 50_400.0},
        "exit_plan": {
            "source": "bound_execution_plan",
            "maximum_hold_seconds": 86_400,
            "deadline_timestamp_ms": 1787259419582,
            "profit_lock_policy": "none",
            "opposite_intent_exit_scope": "same_symbol",
        },
        "path_since_entry": {
            "status": "observed",
            "completed_bars": 10,
            "first_timestamp_ms": 1787173020000,
            "last_timestamp_ms": 1787173560000,
            "highest_price": 50_100.0,
            "lowest_price": 49_400.0,
            "maximum_favorable_excursion_bps": 120.0,
            "maximum_adverse_excursion_bps": 20.0,
            "current_directional_return_bps": 100.0,
            "peak_giveback_bps": 20.0,
            "excursion_price_source": "completed_1m_candle_high_low",
        },
        "profit_protection": {
            "status": "open_profit_unprotected",
            "reported_marked_net_pnl_usd": 9.5,
            "estimated_exit_now_net_usd": 9.0,
            "estimated_stop_net_usd": -4.0,
            "marked_to_stop_giveback_usd": 13.0,
            "protected_profit_fraction": 0.0,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage",
        },
    }
