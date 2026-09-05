"""Bounded rolling checkpoints for the disarmed cohort observer."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from hypervector.research.cohort_observer_checkpoint import (
    build_observer_checkpoint,
    publish_observer_checkpoint,
)
from test_multi_asset_observer_audit import (
    _evaluation,
    _milliseconds,
    _observer_rows,
)

_RUN_ID = "observer-a"
_SOURCE = "hypervelocity_source_follow_bidirectional_5m_v1"
_HYPE_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_GENERATED_AT = datetime(2026, 8, 1, 12, 31, tzinfo=timezone.utc)


def test_checkpoint_reports_setup_process_without_fake_outcomes() -> None:
    """Observer analysis retains ten-pair evidence and no execution results."""
    checkpoint = build_observer_checkpoint(
        _ten_pair_rows(),
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    assert checkpoint["mode"] == "multi_asset_bidirectional_observer_checkpoint"
    assert checkpoint["checkpoint_contract"] == {
        "report_only": True,
        "final": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "performance_gate": False,
    }
    assert checkpoint["observer"]["state"] == "setup_process_observation"
    assert checkpoint["audit"]["technical"]["complete"] is True
    assert checkpoint["audit"]["technical"]["expected_provider_symbols"] == 10
    assert checkpoint["audit"]["readiness"]["evaluations"] == 20
    assert checkpoint["audit"]["signals"]["strategy_intents"] == 1
    regime = checkpoint["audit"]["regime_forward_accuracy"]
    assert regime["mode"] == "cohort_observer_route_regime_forward_accuracy"
    assert regime["execution_authority"] == "none"
    routes = regime["horizons"]["5m"]["by_provider_symbol"]
    assert len(routes) == 10
    assert all(
        route["coverage"]["complete_state_observations"] == 0
        for route in routes.values()
    )
    assert checkpoint["audit"]["canonical_regime_telemetry"] == {
        "schema_version": 1,
        "strategy_id": "canonical_regime_telemetry_v1",
        "contract": {
            "execution_authority": "none",
            "intents_emitted": False,
            "configured_route": False,
        },
        "evaluations": 0,
        "symbols": 0,
        "by_symbol": {},
    }
    scorecard = checkpoint["audit"]["strategy_scorecard"]
    assert scorecard["contract"] == {
        "report_only": True,
        "performance_gate": False,
        "balance_gate": False,
        "trade_count_gate": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "execution_authority": "none",
    }
    assert len(scorecard["by_provider_symbol"]) == 10
    assert all(
        record["strategy_edge_identifiable"] is False
        and record["execution_outcomes_identifiable"] is False
        and record["performance_gate"] is False
        and record["execution_effect"] == "report_only"
        for record in scorecard["by_provider_symbol"].values()
    )
    assert "execution" not in checkpoint["audit"]
    serialized = json.dumps(checkpoint, sort_keys=True)
    assert "closed_trades" not in serialized
    assert "net_pnl_usd" not in serialized


def test_checkpoint_reports_preheartbeat_startup_without_crashing() -> None:
    """A new observer remains explicitly unpolled before its first heartbeat."""
    checkpoint = build_observer_checkpoint(
        _ten_pair_rows()[:2],
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )

    runtime = checkpoint["audit"]["runtime"]
    assert runtime["poll_cycles"] == 0
    assert runtime["successful_poll_cycles"] == 0
    assert runtime["degraded_poll_cycles"] == 0
    assert runtime["successful_polls_since_last_degraded"] == 0
    assert runtime["latest_poll_status"] == "not_observed"
    assert checkpoint["audit"]["technical"]["complete"] is False


def test_checkpoint_marks_a_freshly_republished_stale_source() -> None:
    """Checkpoint liveness cannot mask a stopped observer producer."""
    generated_at = datetime(2026, 8, 1, 12, 35, tzinfo=timezone.utc)

    checkpoint = build_observer_checkpoint(
        _ten_pair_rows(),
        run_id=_RUN_ID,
        generated_at=generated_at,
    )

    assert checkpoint["observer"] == {
        "state": "stale_source",
        "run_id": _RUN_ID,
        "last_observed_at_utc": "2026-08-01T12:30:03+00:00",
        "source_age_seconds": 297.0,
        "stale_after_seconds": 90.0,
    }


def test_publish_replaces_one_checkpoint_and_discloses_incomplete_tail(
    tmp_path: Path,
) -> None:
    """An active append is truncated explicitly while latest remains bounded."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text(
        "".join(json.dumps(row) + "\n" for row in _ten_pair_rows()),
        encoding="utf-8",
    )
    with ledger.open("ab") as stream:
        stream.write(b'{"sequence":8')
    destination = tmp_path / "runtime" / "latest.json"

    first = publish_observer_checkpoint(
        ledger,
        destination,
        run_id=_RUN_ID,
        generated_at=_GENERATED_AT,
    )
    second_time = datetime(2026, 8, 2, 12, 31, tzinfo=timezone.utc)
    second = publish_observer_checkpoint(
        ledger,
        destination,
        run_id=_RUN_ID,
        generated_at=second_time,
    )

    assert first["evidence"]["incomplete_tail_dropped"] is True
    assert first["evidence"]["dropped_tail_bytes"] == len(b'{"sequence":8')
    assert second["generated_at_utc"] == second_time.isoformat()
    assert json.loads(destination.read_text(encoding="utf-8")) == second
    assert [path.name for path in destination.parent.iterdir()] == [destination.name]


def _ten_pair_rows() -> list[dict[str, object]]:
    rows = _observer_rows()
    identity = rows[0]["payload"]
    assert isinstance(identity, dict)
    providers = identity["providers"]
    assert isinstance(providers, list)
    providers.append({"strategy_id": _SOURCE, "symbols": ["BTC"]})
    providers.append({"strategy_id": _HYPE_BREAKOUT, "symbols": ["HYPE"]})
    for row in rows:
        if row["event_type"] != "intent_routing":
            continue
        payload = row["payload"]
        assert isinstance(payload, dict)
        evaluations = payload["evaluations"]
        assert isinstance(evaluations, list)
        source = _evaluation(_SOURCE, "BTC", progressed=False)
        source["decision_time_ms"] = _milliseconds(
            "2026-08-01T12:30:00+00:00"
            if row["sequence"] == 6
            else "2026-08-01T12:00:00+00:00"
        )
        evaluations.append(source)
        hype = _evaluation(_HYPE_BREAKOUT, "HYPE", progressed=False)
        hype["decision_time_ms"] = source["decision_time_ms"]
        evaluations.append(hype)
    return rows
