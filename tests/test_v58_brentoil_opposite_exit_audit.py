"""Source-bound audit of opposite-exit handling for the live V58 BRENTOIL route."""

from __future__ import annotations

import importlib

import pytest


_RUN = "bidirectional-live-1787166474078"
_SUCCESSOR_RUN = "bidirectional-live-1787272893887"
_PROFILE = "multi_asset_growth_first_5000_eight_asset_incremental_v58"
_FINGERPRINT = "8a04636c9ff60a7eae141381cb540d7c6ceed081097cda7d5e465d48faa5022b"
_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_SYMBOL = "xyz:BRENTOIL"
_LIFECYCLE = "xyz:BRENTOIL:520642502465"
_OPENED_AT_MS = 1_787_215_500_000


def test_audit_proves_no_eligible_opposite_exit_was_missed() -> None:
    """A same-side repeat must not be misreported as a missed close."""
    module = importlib.import_module(
        "hypervector.research.v58_brentoil_opposite_exit_audit"
    )

    report = module.build_v58_brentoil_opposite_exit_audit(
        _checkpoint(),
        (
            _routing(_OPENED_AT_MS, "long", eligible=True, action="enter"),
            _routing(
                _OPENED_AT_MS + 900_000,
                "long",
                eligible=True,
                withheld="same_direction_position_open",
            ),
            _routing(_OPENED_AT_MS + 1_800_000, "short", eligible=False),
        ),
        {"path": "/tmp/decisions.jsonl", "bytes": 100, "sha256": "a" * 64},
    )

    audit = report["opposite_exit_audit"]
    assert audit["post_entry_evaluations"] == 3
    assert audit["eligible_same_side_evaluations"] == 2
    assert audit["eligible_opposite_evaluations"] == 0
    assert audit["routed_opposite_exit_actions"] == 0
    assert audit["same_side_position_withheld"] == 1
    assert audit["missed_eligible_opposite_exit"] is False
    assert audit["status"] == "no_eligible_opposite_exit_observed"
    assert report["contract"]["execution_authority"] == "none"


def test_audit_rejects_an_unrouted_eligible_opposite_exit() -> None:
    """An eligible opposite without an exit action is a material contradiction."""
    module = importlib.import_module(
        "hypervector.research.v58_brentoil_opposite_exit_audit"
    )

    with pytest.raises(ValueError, match="eligible opposite exit was not routed"):
        module.build_v58_brentoil_opposite_exit_audit(
            _checkpoint(),
            (_routing(_OPENED_AT_MS, "short", eligible=True),),
            {"path": "/tmp/decisions.jsonl", "bytes": 100, "sha256": "b" * 64},
        )


def test_audit_preserves_source_run_after_successor_runtime_adoption() -> None:
    """A successor process must audit the inherited lifecycle across both runs."""
    module = importlib.import_module(
        "hypervector.research.v58_brentoil_opposite_exit_audit"
    )
    checkpoint = _checkpoint()
    checkpoint["audit"]["run"]["run_id"] = _SUCCESSOR_RUN

    report = module.build_v58_brentoil_opposite_exit_audit(
        checkpoint,
        (
            _routing(_OPENED_AT_MS, "long", eligible=False),
            _routing(
                _OPENED_AT_MS + 900_000,
                "long",
                eligible=False,
                run_id=_SUCCESSOR_RUN,
            ),
        ),
        {"path": "/tmp/decisions.jsonl", "bytes": 100, "sha256": "c" * 64},
    )

    assert report["identity"]["run_id"] == _SUCCESSOR_RUN
    assert report["identity"]["source_run_id"] == _RUN
    assert report["opposite_exit_audit"]["post_entry_evaluations"] == 2


def _checkpoint() -> dict[str, object]:
    return {
        "generated_at_utc": "2026-08-20T22:15:30+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "backend_process_health": "healthy",
            "faulted_assets": [],
            "asset_states": {_SYMBOL: "OPEN"},
        },
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": _FINGERPRINT,
            "runtime_profile_fingerprint": _FINGERPRINT,
        },
        "audit": {
            "run": {
                "run_id": _RUN,
                "profile_id": _PROFILE,
                "profile_fingerprint": _FINGERPRINT,
            },
            "open_trade_reflections": {
                "trades": [
                    {
                        "symbol": _SYMBOL,
                        "side": "long",
                        "strategy_id": _STRATEGY,
                        "source_run_id": _RUN,
                        "lifecycle_id": _LIFECYCLE,
                        "entry": {"price": 91.565, "venue_timestamp_ms": 1},
                        "protective_stop": {"oid": 2, "trigger_price": 90.83248},
                        "exit_plan": {
                            "opened_at_ms": _OPENED_AT_MS,
                            "maximum_hold_seconds": 86_400,
                            "maximum_hold_policy": "fixed",
                            "provider_recipe_exit_policy": "ignore",
                            "profit_lock_policy": "none",
                            "opposite_intent_exit_scope": (
                                "selected_opposite_from_any_executable_provider_same_symbol"
                            ),
                        },
                        "path_since_entry": {
                            "maximum_favorable_excursion_bps": 105.8,
                            "maximum_adverse_excursion_bps": 73.9,
                            "peak_giveback_bps": 114.0,
                            "current_directional_return_bps": -8.2,
                        },
                    }
                ]
            },
        },
    }


def _routing(
    decision_time_ms: int,
    side: str,
    *,
    eligible: bool,
    action: str | None = None,
    withheld: str | None = None,
    run_id: str = _RUN,
) -> dict[str, object]:
    actions = []
    if action is not None:
        actions.append(
            {
                "action": action,
                "strategy_id": _STRATEGY,
                "symbol": _SYMBOL,
                "side": side,
                "decision_time_ms": decision_time_ms,
            }
        )
    withheld_rows = []
    if withheld is not None:
        withheld_rows.append(
            {
                "strategy_id": _STRATEGY,
                "symbol": _SYMBOL,
                "side": side,
                "decision_time_ms": decision_time_ms,
                "reason": withheld,
            }
        )
    return {
        "event_type": "intent_routing",
        "run_id": run_id,
        "profile_id": _PROFILE,
        "profile_fingerprint": _FINGERPRINT,
        "payload": {
            "evaluations": [
                {
                    "strategy_id": _STRATEGY,
                    "symbol": _SYMBOL,
                    "decision_time_ms": decision_time_ms,
                    "eligible": eligible,
                    "side": side,
                }
            ],
            "actions": actions,
            "withheld": withheld_rows,
        },
    }
