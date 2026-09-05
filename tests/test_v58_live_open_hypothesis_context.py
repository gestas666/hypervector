"""Current-live lifecycle projection into the V58 hypothesis ledger."""

from __future__ import annotations

from copy import deepcopy

import pytest

import hypervector.research.v58_current_investigation as investigation


_STRATEGY = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_ROUTE = f"{_STRATEGY}|xyz:SP500"


def test_open_sp500_supersedes_current_state_without_erasing_gap_history() -> None:
    """An exact live open must be current while older censored evidence remains."""
    assert hasattr(investigation, "attach_live_open_lifecycles_to_ledger")
    report = _report()

    investigation.attach_live_open_lifecycles_to_ledger(report, _live_open())

    row = report["hypothesis_ledger"][0]
    assert row["watch_state"] == "open_protected"
    assert row["evidence_state"] == "open_exact_live_lifecycle"
    assert row["technical_complete"] is True
    assert row["pending_lifecycles"] == 1
    assert row["historical_capture_state"] == {
        "watch_state": "CENSORED_AWAIT_NEW_EVIDENCE_OR_LIFECYCLE",
        "evidence_state": "technically_censored",
        "technical_complete": False,
        "pending_lifecycles": 1,
        "resolved_lifecycles": 0,
    }
    assert row["recovery_disposition"] == "OPEN_LIFECYCLE_CENSORED_DECISION_GAP"
    current = row["current_live_lifecycle"]
    assert current["lifecycle_id"] == "xyz:SP500:520755869955"
    assert current["protective_stop_oid"] == 520755909739
    assert current["profit_lock_policy"] == "completed_bar_trailing"
    assert current["entry_execution_quality"]["slippage_bps"] == -0.39
    assert current["actual_completed_path"]["maximum_favorable_excursion_bps"] == (
        57.07
    )
    assert current["profit_protection_estimate"]["marked_to_stop_giveback_usd"] == (
        22.08
    )
    assert current["profit_lock_challenger"]["policies"]["a25"]["status"] == (
        "triggered_before_current_boundary"
    )
    assert current["actual_exit_fill_claim"] is False
    assert row["next_action"] == (
        "reconcile_authoritative_close_then_compare_frozen_exit_alternatives"
    )
    assert row["minimum_additional_evidence"] == {
        "diagnostic_update": (
            "one technically complete authoritative close with exact exit fill, "
            "fees, funding, completed-path MFE/MAE/giveback, and frozen "
            "profit-lock comparisons"
        ),
        "live_change": (
            "a preregistered source-compatible sample covering both configured "
            "sides with positive after-cost and largest-winner-removed results"
        ),
    }
    assert report["change_proposals"] == []


def test_closed_sp500_persists_as_resolved_current_run_evidence() -> None:
    """The live SP500 outcome must remain after it leaves the open-position set."""
    assert hasattr(investigation, "attach_live_closed_lifecycles_to_ledger")
    report = _report()

    investigation.attach_live_closed_lifecycles_to_ledger(report, _live_closed())

    row = report["hypothesis_ledger"][0]
    assert row["watch_state"] == "resolved_review_due"
    assert row["evidence_state"] == "resolved_exact_live_lifecycle"
    assert row["pending_lifecycles"] == 0
    assert row["resolved_lifecycles"] == 1
    resolved = row["current_run_resolved_lifecycles"][0]
    assert resolved["lifecycle_id"] == "xyz:SP500:520755869955"
    assert resolved["net_pnl_usd"] == 3.5
    assert resolved["actual_exit_fill_claim"] is True
    assert resolved["completed_hold_capture"]["maximum_favorable_excursion_bps"] == (
        57.07
    )
    assert (
        resolved["profit_lock_challenger"]["policies"]["a25"]["estimated_net_pnl_usd"]
        == 5.44
    )
    assert row["historical_capture_state"]["evidence_state"] == ("technically_censored")


def test_open_sp500_rejects_profit_lock_challenger_with_authority() -> None:
    """An open diagnostic cannot smuggle execution authority into the ledger."""
    live_open = deepcopy(_live_open())
    trade = live_open["trades"][0]
    trade["profit_lock_challenger"]["execution_authority"] = "live"

    with pytest.raises(ValueError, match="lock challenger has authority"):
        investigation.attach_live_open_lifecycles_to_ledger(_report(), live_open)


def test_open_lifecycle_preserves_route_specific_evidence_requirement() -> None:
    """A stronger route-specific falsifier must outrank the generic fallback."""
    report = _report()
    row = report["hypothesis_ledger"][0]
    row["next_action"] = "preserve_route_specific_action"
    row["minimum_additional_evidence"] = "preserve_route_specific_falsifier"

    investigation.attach_live_open_lifecycles_to_ledger(report, _live_open())

    assert row["next_action"] == "preserve_route_specific_action"
    assert row["minimum_additional_evidence"] == ("preserve_route_specific_falsifier")


def _report() -> dict[str, object]:
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "automatic_live_change": False,
            "runtime_strategy_changed": False,
        },
        "hypothesis_ledger": [
            {
                "route": _ROUTE,
                "symbol": "xyz:SP500",
                "status": "being_tested",
                "watch_state": "CENSORED_AWAIT_NEW_EVIDENCE_OR_LIFECYCLE",
                "evidence_state": "technically_censored",
                "technical_complete": False,
                "pending_lifecycles": 1,
                "resolved_lifecycles": 0,
                "recovery_disposition": "OPEN_LIFECYCLE_CENSORED_DECISION_GAP",
            }
        ],
        "change_proposals": [],
    }


def _live_open() -> dict[str, object]:
    return {
        "execution_authority": "none",
        "actual_exit_fills_claimed": False,
        "open_lifecycles": 1,
        "trades": [_open_trade()],
    }


def _open_trade() -> dict[str, object]:
    return {
        "lifecycle_id": "xyz:SP500:520755869955",
        "strategy_id": _STRATEGY,
        "symbol": "xyz:SP500",
        "side": "short",
        "actual_entry_fill_claim": True,
        "actual_exit_fill_claim": False,
        "entry_price": 7692.4,
        "entry_size": 0.223,
        "entry_time_ms": 1787225415947,
        "marked_net_pnl_usd": -0.638811,
        "protective_stop_oid": 520755909739,
        "protective_stop_trigger_price": 7753.9392,
        "maximum_hold_seconds": 86400,
        "deadline_timestamp_ms": 1787311800000,
        "profit_lock_policy": "completed_bar_trailing",
        "entry_execution_quality": {
            "measurement_scope": "actual_venue_entry_fill",
            "slippage_bps": -0.39,
        },
        "actual_completed_path": {
            "measurement_scope": "actual_fill_completed_candle_path",
            "continuous_path_claim": False,
            "maximum_favorable_excursion_bps": 57.07,
            "maximum_adverse_excursion_bps": 6.63,
            "current_directional_return_bps": 48.75,
            "peak_giveback_bps": 8.32,
        },
        "profit_protection_estimate": {
            "actual_exit_fill_claim": False,
            "marked_to_stop_giveback_usd": 22.08,
            "method": "measured_entry_fee_rate_no_future_funding_or_slippage",
        },
        "profit_lock_challenger": {
            "status": "observed",
            "execution_authority": "none",
            "actual_exit_fill_claim": False,
            "policies": {"a25": {"status": "triggered_before_current_boundary"}},
        },
    }


def _live_closed() -> dict[str, object]:
    return {
        "execution_authority": "none",
        "closed_lifecycles": 1,
        "trades": [
            {
                "lifecycle_id": "xyz:SP500:520755869955",
                "strategy_id": _STRATEGY,
                "symbol": "xyz:SP500",
                "side": "short",
                "actual_entry_fill_claim": True,
                "actual_exit_fill_claim": True,
                "entry_price": 7692.4,
                "entry_time_ms": 1787225415947,
                "exit_price": 7675.0,
                "exit_time_ms": 1787230000000,
                "exit_reason": "completed_bar_profit_lock",
                "net_pnl_usd": 3.5,
                "fees_usd": 0.3,
                "funding_usd": 0.0,
                "technical_complete": True,
                "completed_hold_capture": {
                    "status": "resolved",
                    "completed_bars": 76,
                    "maximum_favorable_excursion_bps": 57.07,
                    "maximum_adverse_excursion_bps": 6.63,
                    "peak_giveback_bps": 8.32,
                },
                "profit_lock_challenger": {
                    "status": "eligible",
                    "execution_authority": "none",
                    "actual_exit_fill_claim": True,
                    "policies": {
                        "a25": {
                            "status": "triggered",
                            "actual_net_pnl_usd": 3.5,
                            "estimated_net_pnl_usd": 5.44,
                            "estimated_minus_actual_net_usd": 1.94,
                        }
                    },
                },
            }
        ],
    }
