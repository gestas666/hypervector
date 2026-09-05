"""Exact current-run closed lifecycle extraction for V58 research."""

from __future__ import annotations

from importlib import util

import pytest

from hypervector.research.v58_live_backend_context import (
    LiveBackendContext,
    live_backend_context_payload,
)


_RUN = "bidirectional-live-1787166474078"
_PROFILE = "8" * 64
_STRATEGY = "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
_ROUTE = f"{_STRATEGY}|xyz:SP500"


def test_extracts_exact_current_run_close_and_excludes_prior_run() -> None:
    """Only the active run's source-profile-bound closes may persist."""
    module_name = "hypervector.research.v58_live_closed_lifecycles"
    assert util.find_spec(module_name) is not None, "closed extractor is missing"
    module = __import__(module_name, fromlist=["extract_v58_live_closed_lifecycles"])
    audit = _audit()
    prior = dict(audit["trade_reflections"]["trades"][0])
    prior["lifecycle_id"] = "xyz:SP500:111"
    prior["source_run_id"] = "prior-run"
    audit["trade_reflections"]["trades"].append(prior)
    audit["trade_reflections"]["closed_trades"] = 2

    result = module.extract_v58_live_closed_lifecycles(
        audit, run_id=_RUN, profile_fingerprint=_PROFILE, routes=(_ROUTE,)
    )

    assert result["closed_lifecycles"] == 1
    assert result["execution_authority"] == "none"
    assert result["trades"][0]["lifecycle_id"] == "xyz:SP500:520755869955"
    assert result["trades"][0]["actual_exit_fill_claim"] is True
    assert result["trades"][0]["technical_complete"] is True
    assert result["trades"][0]["completed_hold_capture"] == _hold_capture()
    challenger = result["trades"][0]["profit_lock_challenger"]
    assert challenger["execution_authority"] == "none"
    assert challenger["actual_exit_fill_claim"] is True
    assert challenger["policies"] == _profit_lock_result()["policies"]


def test_rejects_current_run_close_with_wrong_profile() -> None:
    """A close from the active run cannot carry another profile fingerprint."""
    module_name = "hypervector.research.v58_live_closed_lifecycles"
    assert util.find_spec(module_name) is not None, "closed extractor is missing"
    module = __import__(module_name, fromlist=["extract_v58_live_closed_lifecycles"])
    audit = _audit()
    audit["trade_reflections"]["trades"][0]["source_profile_fingerprint"] = "7" * 64

    with pytest.raises(ValueError, match="profile fingerprint"):
        module.extract_v58_live_closed_lifecycles(
            audit, run_id=_RUN, profile_fingerprint=_PROFILE, routes=(_ROUTE,)
        )


def test_rejects_close_when_profit_lock_actual_net_differs() -> None:
    """A counterfactual cannot detach from its authoritative actual result."""
    module = __import__(
        "hypervector.research.v58_live_closed_lifecycles",
        fromlist=["extract_v58_live_closed_lifecycles"],
    )
    audit = _audit()
    audit["profit_lock_challenger"]["latest_results"][0]["actual_net_pnl_usd"] = 4.5

    with pytest.raises(ValueError, match="actual net differs"):
        module.extract_v58_live_closed_lifecycles(
            audit, run_id=_RUN, profile_fingerprint=_PROFILE, routes=(_ROUTE,)
        )


def test_rejects_close_without_resolved_excursion_capture() -> None:
    """An unresolved closed path cannot be labeled technically complete."""
    module = __import__(
        "hypervector.research.v58_live_closed_lifecycles",
        fromlist=["extract_v58_live_closed_lifecycles"],
    )
    audit = _audit()
    audit["trade_reflections"]["trades"][0]["completed_hold_capture"]["status"] = (
        "unavailable"
    )

    with pytest.raises(ValueError, match="hold capture is unresolved"):
        module.extract_v58_live_closed_lifecycles(
            audit, run_id=_RUN, profile_fingerprint=_PROFILE, routes=(_ROUTE,)
        )


def test_live_backend_payload_preserves_extracted_closes() -> None:
    """The validated close collection must reach the continuous report payload."""
    module_name = "hypervector.research.v58_live_closed_lifecycles"
    module = __import__(module_name, fromlist=["extract_v58_live_closed_lifecycles"])
    closed = module.extract_v58_live_closed_lifecycles(
        _audit(), run_id=_RUN, profile_fingerprint=_PROFILE, routes=(_ROUTE,)
    )
    context = LiveBackendContext(
        profile_id="v58",
        profile_fingerprint=_PROFILE,
        run_id=_RUN,
        lifecycle_state="running_consistent",
        backend_process_health="healthy",
        heartbeat_status="running",
        checkpoint_age_seconds=1.0,
        backend_event_age_seconds=1.0,
        last_event_type="heartbeat",
        last_observed_at_utc="2026-08-20T00:00:00+00:00",
        runtime_fault_exception_type=None,
        ledger_asset_states={"xyz:SP500": "FLAT"},
        ledger_last_snapshot_flat_order_free=True,
        evidence={"sha256": "a" * 64},
        closed_lifecycles=closed,
    )

    payload = live_backend_context_payload(context)

    assert payload["closed_lifecycles"] == closed
    assert payload["closed_lifecycles"]["execution_authority"] == "none"


def _audit() -> dict[str, object]:
    return {
        "coverage": {"complete": True, "technical_gaps": []},
        "profit_lock_challenger": {
            "schema_version": 1,
            "mode": "cohort_profit_lock_challenger_v1",
            "scope": "compatible_profile_history",
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "automatic_strategy_changes": False,
                "runtime_strategy_changed": False,
                "automatic_promotion": False,
                "performance_gate": False,
                "balance_gate": False,
                "portfolio_pnl_claimed": False,
            },
            "latest_results": [_profit_lock_result()],
        },
        "trade_reflections": {
            "schema_version": 1,
            "mode": "cohort_trade_reflections",
            "scope": "compatible_profile_history",
            "closed_trades": 1,
            "contract": {
                "report_only": True,
                "execution_authority": "none",
                "automatic_strategy_changes": False,
                "runtime_strategy_changed": False,
            },
            "trades": [_trade()],
        },
    }


def _trade() -> dict[str, object]:
    return {
        "lifecycle_id": "xyz:SP500:520755869955",
        "strategy_id": _STRATEGY,
        "symbol": "xyz:SP500",
        "side": "short",
        "source_run_id": _RUN,
        "source_profile_fingerprint": _PROFILE,
        "entry_oid": 520755869955,
        "exit_oid": 520800000001,
        "entry": {
            "price": 7692.4,
            "size": 0.223,
            "venue_timestamp_ms": 1787225415947,
        },
        "exit": {
            "price": 7675.0,
            "size": 0.223,
            "venue_timestamp_ms": 1787230000000,
        },
        "exit_reason": "completed_bar_profit_lock",
        "net_pnl_usd": 3.5,
        "fees_usd": 0.3,
        "funding_usd": 0.0,
        "completed_hold_capture": _hold_capture(),
    }


def _hold_capture() -> dict[str, object]:
    return {
        "status": "resolved",
        "completed_bars": 76,
        "maximum_favorable_excursion_bps": 57.07,
        "maximum_adverse_excursion_bps": 6.63,
        "peak_giveback_bps": 8.32,
        "realized_net_return_bps": 20.1,
    }


def _profit_lock_result() -> dict[str, object]:
    return {
        "lifecycle_id": "xyz:SP500:520755869955",
        "source_run_id": _RUN,
        "source_profile_fingerprint": _PROFILE,
        "strategy_id": _STRATEGY,
        "symbol": "xyz:SP500",
        "side": "short",
        "status": "eligible",
        "completed_bars_expected": 76,
        "completed_bars_observed": 76,
        "actual_net_pnl_usd": 3.5,
        "policies": {
            policy_id: {
                "status": "triggered",
                "actual_net_pnl_usd": 3.5,
                "estimated_net_pnl_usd": 5.44,
                "estimated_minus_actual_net_usd": 1.94,
            }
            for policy_id in (
                "a25_floor15_trail10",
                "a40_floor15_trail20",
                "a60_floor15_trail30",
            )
        },
    }
