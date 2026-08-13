"""Immutable evidence contracts for the Hulk live canary audit."""

from __future__ import annotations

import importlib

import pytest


def test_hulk_audit_attributes_complete_live_execution_evidence() -> None:
    """One stopped lifecycle retains execution quality and truthful exit facts."""
    report = _audit(_complete_rows())

    assert report["run"]["strategy_id"] == "hulk_expansion_short_robust_v3"
    assert report["experiment_contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }
    assert report["decisions"] == {
        "completed_bar_decisions": 1,
        "eligible_entries": 1,
        "entry_intents": 1,
    }
    assert report["execution"]["fills"] == 1
    assert report["execution"]["fill_fees_usd"] == pytest.approx(0.045)
    assert report["execution"]["closed_pnl_usd"] == pytest.approx(1.25)
    assert report["execution"]["funding_usd"] == pytest.approx(-0.01)
    assert report["latency_ms"]["median"] == 37.0
    assert report["slippage_bps"]["mean"] == pytest.approx(2.0)
    assert report["markout"]["actual_horizon_ms"]["mean"] == 7_300.0
    assert report["markout"]["target_horizon_ms"] == 5_000
    assert report["markout"]["recovered_after_restart"] == 1
    assert report["exits"]["reasons"] == {"target": 1}
    assert report["final_state"]["flat"] is True
    assert report["coverage"]["complete"] is True
    assert report["coverage"]["technical_gaps"] == []


def test_hulk_audit_selects_latest_live_run_from_mixed_observe_ledger() -> None:
    """Prior disarmed observations cannot contaminate one requested live run."""
    rows = [
        _row(
            1,
            "configuration_identity",
            {"strategy_name": "hulk_expansion_short_robust_v3"},
            run_id="observe-a",
            live=False,
        ),
        *_renumber(_flat_rows(run_id="live-a"), start=2),
    ]

    report = _audit(rows)

    assert report["run"]["run_id"] == "live-a"
    assert report["execution"]["fills"] == 0
    assert report["coverage"]["metrics"]["slippage"] == "not_applicable_no_fills"
    assert report["coverage"]["complete"] is True


def test_hulk_audit_surfaces_missing_fill_markout() -> None:
    """A filled run cannot look evidence-complete without its due markout."""
    rows = [row for row in _complete_rows() if row["event_type"] != "fill_markout"]
    rows = _renumber(rows)

    report = _audit(rows)

    assert report["coverage"]["complete"] is False
    assert "markout_missing_for_fills" in report["coverage"]["technical_gaps"]


def test_hulk_audit_rejects_disarmed_run_selection() -> None:
    """Observe rows cannot be published as live-canary evidence."""
    rows = [
        _row(
            1,
            "configuration_identity",
            {"strategy_name": "hulk_expansion_short_robust_v3"},
            run_id="observe-a",
            live=False,
        )
    ]

    with pytest.raises(ValueError, match="not an armed live run"):
        _audit(rows, run_id="observe-a")


def test_hulk_audit_preserves_mixed_bracket_exit() -> None:
    """The audit does not collapse a mixed target/stop close into a win."""
    rows = _flat_rows()
    rows.insert(
        -3,
        _row(
            2,
            "close",
            {"reason": "mixed_bracket_exit", "verified_flat": True, "oid": 201},
        ),
    )
    rows = _renumber(rows)

    report = _audit(rows)

    assert report["exits"]["reasons"] == {"mixed_bracket_exit": 1}


def test_hulk_audit_rejects_equal_count_slippage_for_the_wrong_fill() -> None:
    """An orphan quality row cannot satisfy exact owned-fill coverage."""
    rows = _complete_rows()
    quality = next(row for row in rows if row["event_type"] == "execution_quality")
    quality["payload"]["trade_id"] = 999

    report = _audit(rows)

    assert report["coverage"]["complete"] is False
    assert "slippage_missing_for_fills" in report["coverage"]["technical_gaps"]
    assert "slippage_without_run_fill" in report["coverage"]["technical_gaps"]
    assert report["coverage"]["metrics"]["slippage"] == "invalid_orphan_metrics"


def _audit(
    rows: list[dict[str, object]],
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    module = importlib.import_module("hypervector.research.hulk_smash_live_audit")
    return module.audit_hulk_smash_live_run(rows, run_id=run_id)


def _complete_rows() -> list[dict[str, object]]:
    identity = "0x" + "1" * 32
    rows = [
        _row(
            1,
            "configuration_identity",
            {
                "strategy_name": "hulk_expansion_short_robust_v3",
                "execution": {
                    "markout_horizon_ms": 5_000,
                    "fill_identity": "hyperliquid_tid",
                },
            },
        ),
        _row(
            2,
            "regime_decision",
            {"entry_allowed": True, "decision_action": "enter_short"},
        ),
        _row(
            3,
            "order_intent",
            {"operation": "entry", "client_order_id": identity, "mark_price": 100.0},
        ),
        _row(
            4,
            "order_acknowledgement",
            {
                "operation": "entry",
                "accepted": True,
                "oid": 101,
                "client_order_id": identity,
                "round_trip_latency_ms": 37,
            },
        ),
        _row(
            5,
            "fill",
            {
                "oid": 101,
                "trade_id": 10_001,
                "venue_timestamp_ms": 1_000,
                "price": 99.98,
                "size": 0.01,
                "side": "A",
                "crossed": True,
                "fee_usd": 0.045,
                "closed_pnl_usd": 1.25,
            },
        ),
        _row(
            6,
            "fee",
            {
                "source": "fill",
                "oid": 101,
                "trade_id": 10_001,
                "venue_timestamp_ms": 1_000,
                "fee_usd": 0.045,
            },
        ),
        _row(
            7,
            "execution_quality",
            {
                "oid": 101,
                "trade_id": 10_001,
                "fill_timestamp_ms": 1_000,
                "slippage_bps": 2.0,
            },
        ),
        _row(
            8,
            "position",
            {"size_signed": -0.01, "position_value_usd": 0.9998},
        ),
        _row(9, "liquidation_distance", {"distance_pct": 20.0}),
        _row(
            10,
            "fill_markout",
            {
                "oid": 101,
                "trade_id": 10_001,
                "fill_timestamp_ms": 1_000,
                "horizon_ms": 7_300,
                "target_horizon_ms": 5_000,
                "horizon_lateness_ms": 2_300,
                "recovered_after_restart": True,
                "markout_bps": 3.0,
            },
        ),
        _row(11, "funding", {"usdc_delta": -0.01}),
        _row(12, "close", {"reason": "target", "verified_flat": True, "oid": 202}),
        _row(13, "position", {"size_signed": 0.0, "position_value_usd": 0.0}),
        _row(
            14,
            "reconciliation",
            {"account_value_usd": 151.19, "open_order_ids": []},
        ),
        _row(15, "state_transition", {"state": "STOPPED"}),
    ]
    return rows


def _flat_rows(*, run_id: str = "run-a") -> list[dict[str, object]]:
    return [
        _row(
            1,
            "configuration_identity",
            {
                "strategy_name": "hulk_expansion_short_robust_v3",
                "execution": {
                    "markout_horizon_ms": 5_000,
                    "fill_identity": "hyperliquid_tid",
                },
            },
            run_id=run_id,
        ),
        _row(
            2,
            "position",
            {"size_signed": 0.0, "position_value_usd": 0.0},
            run_id=run_id,
        ),
        _row(
            3,
            "reconciliation",
            {"account_value_usd": 150.0, "open_order_ids": []},
            run_id=run_id,
        ),
        _row(4, "state_transition", {"state": "STOPPED"}, run_id=run_id),
    ]


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    run_id: str = "run-a",
    live: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": f"2026-08-01T12:00:{sequence:02d}+00:00",
        "execution_mode": "live" if live else "observe",
        "live_armed": live,
        "execution_authority": "hyperliquid_mainnet" if live else "none",
        "profile_id": "hulk_expansion_short_robust_v3_canary_v1",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": run_id,
        "payload": payload,
    }


def _renumber(
    rows: list[dict[str, object]],
    *,
    start: int = 1,
) -> list[dict[str, object]]:
    for sequence, row in enumerate(rows, start=start):
        row["sequence"] = sequence
        row["observed_at_utc"] = f"2026-08-01T12:00:{sequence:02d}+00:00"
    return rows
