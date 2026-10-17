"""Immutable learning-audit tests for disarmed cohort observations."""

from __future__ import annotations

from datetime import datetime
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from cohort_observer_audit_assertions import assert_observer_audit_baseline
from hypervector.research.cohort_observer_audit import audit_cohort_observer_run

_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_HULK = "hulk_expansion_bidirectional_tuned_v2"
_RANGE = "range_onset_bidirectional_v1"
_RUN_ID = "observer-a"
_SCRIPT = Path("src/hypervector/operations/multi_asset_bidirectional_observer_audit.py")


def test_report_separates_setup_progression_from_unobserved_edge() -> None:
    """Readiness movement remains diagnostic when no outcomes or fills exist."""
    report = audit_cohort_observer_run(_observer_rows(), run_id=_RUN_ID)

    assert_observer_audit_baseline(report)


def test_readiness_preserves_historical_eligible_counts_by_side() -> None:
    """Later readiness rows must not erase the side of an eligible event."""
    report = audit_cohort_observer_run(_observer_rows(), run_id=_RUN_ID)
    route = f"{_HULK}|BTC"

    assert report["readiness"]["by_provider_symbol"][route].get("eligible_by_side") == {
        "long": 1,
        "short": 0,
    }


def test_identical_resume_configuration_identity_is_accepted() -> None:
    """A resumed frozen run may restate, but not change, its exact identity."""
    rows = _observer_rows()
    rows.append(
        _row(
            len(rows) + 1,
            "configuration_identity",
            _identity(),
            "2026-08-01T12:31:00+00:00",
        )
    )

    report = audit_cohort_observer_run(rows, run_id=_RUN_ID)

    assert report["run"]["run_id"] == _RUN_ID
    assert report["technical"]["complete"] is True


def test_conflicting_resume_configuration_identity_is_rejected() -> None:
    """A resumed run cannot mutate its frozen provider or risk contract."""
    rows = _observer_rows()
    changed = _identity()
    changed["position_policy"] = {"maximum_concurrent_positions": 3}
    rows.append(
        _row(
            len(rows) + 1,
            "configuration_identity",
            changed,
            "2026-08-01T12:31:00+00:00",
        )
    )

    with pytest.raises(ValueError, match="configuration identity"):
        audit_cohort_observer_run(rows, run_id=_RUN_ID)


def test_report_only_strategy_evidence_restatement_is_accepted() -> None:
    """Research annotations may advance without changing executable identity."""
    rows = _observer_rows()
    annotated = _identity()
    annotated["strategy_evidence"] = [{"status": "new_report_only_evidence"}]
    rows.append(
        _row(
            len(rows) + 1,
            "configuration_identity",
            annotated,
            "2026-08-01T12:31:00+00:00",
        )
    )

    report = audit_cohort_observer_run(rows, run_id=_RUN_ID)

    assert report["technical"]["complete"] is True


def test_data_defects_are_reported_without_success_shaping() -> None:
    """Coverage, duplicate, timing, and action defects remain explicit evidence."""
    rows = _observer_rows()
    first_routing = next(row for row in rows if row["event_type"] == "intent_routing")
    evaluations = first_routing["payload"]["evaluations"]
    assert isinstance(evaluations, list)
    evaluations.pop()
    duplicate = dict(evaluations[0])
    evaluations.append(duplicate)
    evaluations[1]["decision_time_ms"] = _milliseconds("2026-08-01T12:01:00+00:00")
    first_routing["payload"]["actions"] = [
        {
            "action": "enter",
            "strategy_id": _HULK,
            "symbol": "BTC",
            "side": "long",
        }
    ]
    candle_row = next(row for row in rows if row["event_type"] == "market_candles")
    candle_row["payload"]["bars"].pop("HYPE")

    report = audit_cohort_observer_run(rows, run_id=_RUN_ID)

    assert report["technical"]["complete"] is False
    assert report["technical"]["future_decisions"] == 1
    assert report["technical"]["duplicate_evaluations"] == 1
    assert report["signals"]["routed_actions"] == 1
    assert report["technical"]["technical_gaps"] == [
        "duplicate_evaluation_identity",
        "future_decision_timestamp",
        "initial_candle_coverage_incomplete",
        "initial_provider_coverage_incomplete",
        "observer_routed_action_present",
    ]


def test_restart_seed_duplicates_are_reported_but_not_actionable() -> None:
    """Repeated pre-activation readiness cannot masquerade as a new decision."""
    rows = _observer_rows()
    routings = [row for row in rows if row["event_type"] == "intent_routing"]
    initial = routings[0]["payload"]["evaluations"][0]
    initial["backend_non_action_reason"] = "pre_activation_readiness_seed"
    duplicate = dict(initial)
    duplicate["readiness"] = dict(initial["readiness"])
    routings[1]["payload"]["evaluations"].append(duplicate)

    technical = audit_cohort_observer_run(rows, run_id=_RUN_ID)["technical"]
    timing = technical["decision_timing_seconds"]

    assert technical["duplicate_evaluations"] == 0
    assert technical["preactivation_duplicate_evaluations"] == 1
    assert technical["complete"] is True
    assert timing["startup_seed_age_by_provider"][_HULK]["maximum"] == 1_802.0
    assert timing["steady_state_arrival_lag_by_provider"][_HULK]["maximum"] == 2.0


def test_runtime_separates_degraded_public_data_cycles() -> None:
    """Recoverable skipped cycles remain distinct from successful polls."""
    rows = _observer_rows()
    rows.append(
        _row(
            8,
            "heartbeat",
            {
                "status": "degraded",
                "source": "hyperliquid_public_l2",
                "reason": "transport_timeout_retry_exhausted",
                "orders_attempted": False,
            },
            "2026-08-01T12:30:18+00:00",
        )
    )
    rows.append(
        _row(9, "heartbeat", {"status": "running"}, "2026-08-01T12:30:33+00:00")
    )

    runtime = audit_cohort_observer_run(rows, run_id=_RUN_ID)["runtime"]

    assert runtime["poll_cycles"] == 4
    assert runtime["successful_poll_cycles"] == 3
    assert runtime["degraded_poll_cycles"] == 1
    assert runtime["degraded_sources"] == {"hyperliquid_public_l2": 1}
    assert runtime["degraded_reasons"] == {"transport_timeout_retry_exhausted": 1}
    assert runtime["first_degraded_observed_at_utc"] == "2026-08-01T12:30:18+00:00"
    assert runtime["last_degraded_observed_at_utc"] == "2026-08-01T12:30:18+00:00"
    assert runtime["successful_polls_since_last_degraded"] == 1
    assert runtime["latest_poll_status"] == "running"


def test_poll_gap_beyond_entry_delay_is_a_technical_gap() -> None:
    """A silent observer interval cannot support complete opportunity coverage."""
    rows = _observer_rows()
    identity = rows[0]["payload"]
    assert isinstance(identity, dict)
    identity["runtime"] = {"poll_seconds": 15.0}
    providers = identity["providers"]
    assert isinstance(providers, list)
    for provider in providers:
        assert isinstance(provider, dict)
        provider["maximum_entry_delay_seconds"] = 30

    technical = audit_cohort_observer_run(rows, run_id=_RUN_ID)["technical"]

    assert technical["complete"] is False
    assert technical["technical_gaps"] == ["observer_heartbeat_gap_exceeds_entry_delay"]


def test_complete_scheduled_decisions_override_a_long_heartbeat_interval() -> None:
    """Exact timely decision coverage must outrank a coarse heartbeat proxy."""
    rows = _observer_rows()
    identity = rows[0]["payload"]
    assert isinstance(identity, dict)
    providers = identity["providers"]
    assert isinstance(providers, list)
    for provider in providers:
        assert isinstance(provider, dict)
        provider["timeframe"] = "30m"
        provider["maximum_entry_delay_seconds"] = 30
    rows.append(
        _row(8, "heartbeat", {"status": "running"}, "2026-08-01T12:30:33+00:00")
    )

    technical = audit_cohort_observer_run(rows, run_id=_RUN_ID)["technical"]

    assert technical["complete"] is True
    assert technical["technical_gaps"] == []


def test_missing_scheduled_decision_keeps_runtime_coverage_incomplete() -> None:
    """Schedule-aware coverage must still fail closed on one omitted route row."""
    rows = _observer_rows()
    identity = rows[0]["payload"]
    assert isinstance(identity, dict)
    providers = identity["providers"]
    assert isinstance(providers, list)
    for provider in providers:
        assert isinstance(provider, dict)
        provider["timeframe"] = "30m"
        provider["maximum_entry_delay_seconds"] = 30
    routings = [row for row in rows if row["event_type"] == "intent_routing"]
    evaluations = routings[-1]["payload"]["evaluations"]
    assert isinstance(evaluations, list)
    evaluations.pop()
    rows.append(
        _row(8, "heartbeat", {"status": "running"}, "2026-08-01T12:30:33+00:00")
    )

    technical = audit_cohort_observer_run(rows, run_id=_RUN_ID)["technical"]

    assert technical["complete"] is False
    assert technical["technical_gaps"] == ["observer_heartbeat_gap_exceeds_entry_delay"]


def test_hold_direction_conflict_is_an_explicit_observer_gap() -> None:
    """A rejected stale direction remains auditable but invalidates parity."""
    rows = _observer_rows()
    routings = [row for row in rows if row["event_type"] == "intent_routing"]
    payload = routings[-1]["payload"]
    assert isinstance(payload, dict)
    evaluations = payload["evaluations"]
    assert isinstance(evaluations, list)
    evaluation = next(
        value
        for value in evaluations
        if value["strategy_id"] == _HULK and value["symbol"] == "ETH"
    )
    readiness = evaluation["readiness"]
    assert isinstance(readiness, dict)
    evaluation["side"] = "long"
    readiness["side"] = "short"

    report = audit_cohort_observer_run(rows, run_id=_RUN_ID)

    assert report["technical"]["complete"] is False
    assert report["technical"]["technical_gaps"] == [
        "provider_direction_telemetry_conflict"
    ]
    assert report["signal_outcomes"]["coverage"]["direction_conflicts"] == 1


def test_armed_rows_are_rejected_as_the_wrong_evidence_class() -> None:
    """The observer audit cannot launder armed execution records."""
    rows = _observer_rows()
    rows[-1]["live_armed"] = True
    rows[-1]["execution_authority"] = "hyperliquid_mainnet"

    with pytest.raises(ValueError, match="not a disarmed observer run"):
        audit_cohort_observer_run(rows, run_id=_RUN_ID)


def test_duplicate_provider_contract_is_rejected() -> None:
    """A set must not hide duplicate provider/symbol identity declarations."""
    rows = _observer_rows()
    identity = rows[0]["payload"]
    assert isinstance(identity, dict)
    providers = identity["providers"]
    assert isinstance(providers, list)
    providers.append({"strategy_id": _HULK, "symbols": ["BTC"]})

    with pytest.raises(ValueError, match="provider/symbol pairs must be unique"):
        audit_cohort_observer_run(rows, run_id=_RUN_ID)


def test_script_publishes_one_immutable_cohort_snapshot(tmp_path: Path) -> None:
    """The CLI fingerprints its source and refuses to overwrite evidence."""
    content = "".join(json.dumps(row) + "\n" for row in _observer_rows()).encode()
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_bytes(content)
    output = tmp_path / "observer-audit.json"
    module = _load_script()
    args = ["--decisions", str(ledger), "--run-id", _RUN_ID, "--out", str(output)]

    assert module.main(args) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evidence"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert report["observer_contract"]["execution_authority"] == "none"
    with pytest.raises(FileExistsError, match="observer audit output exists"):
        module.main(args)
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "private_key" not in source
    assert "create_armed" not in source
    assert "submit" not in source


def _observer_rows() -> list[dict[str, object]]:
    first = [
        _evaluation(provider, symbol, progressed=False)
        for provider in (_HULK, _RANGE)
        for symbol in _SYMBOLS
    ]
    second = [
        _evaluation(provider, symbol, progressed=provider == _HULK and symbol == "BTC")
        for provider in (_HULK, _RANGE)
        for symbol in _SYMBOLS
    ]
    for evaluation in second:
        evaluation["decision_time_ms"] = _milliseconds("2026-08-01T12:30:00+00:00")
    rows = [
        _row(1, "configuration_identity", _identity(), "2026-08-01T12:00:00+00:00"),
        _row(2, "market_candles", _candles(), "2026-08-01T12:00:01+00:00"),
        _row(
            3,
            "intent_routing",
            {"evaluations": first, "actions": [], "withheld": []},
            "2026-08-01T12:00:02+00:00",
        ),
        _row(4, "heartbeat", {"status": "running"}, "2026-08-01T12:00:03+00:00"),
        _row(5, "strategy_intent", _intent(), "2026-08-01T12:30:01+00:00"),
        _row(
            6,
            "intent_routing",
            {
                "evaluations": second,
                "actions": [],
                "withheld": [{**_intent(), "reason": "observe_mode_no_execution"}],
            },
            "2026-08-01T12:30:02+00:00",
        ),
        _row(7, "heartbeat", {"status": "running"}, "2026-08-01T12:30:03+00:00"),
    ]
    return rows


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    observed_at_utc: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": observed_at_utc,
        "execution_mode": "live",
        "effective_mode": "DISARMED",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "multi_asset_bidirectional_canary_v1",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": _RUN_ID,
        "payload": payload,
    }


def _identity() -> dict[str, object]:
    return {
        "symbol": "MULTI",
        "strategy_name": "multi_asset_bidirectional_cohort",
        "enabled_symbols": list(_SYMBOLS),
        "providers": [
            {"strategy_id": provider, "symbols": list(_SYMBOLS)}
            for provider in (_HULK, _RANGE)
        ],
        "position_policy": {"maximum_concurrent_positions": 4},
    }


def _candles() -> dict[str, object]:
    return {
        "timeframe": "1m",
        "bars": {
            symbol: [
                {
                    "timestamp_ms": _milliseconds("2026-08-01T11:59:00+00:00"),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10.0,
                }
            ]
            for symbol in _SYMBOLS
        },
    }


def _evaluation(
    provider: str,
    symbol: str,
    *,
    progressed: bool,
) -> dict[str, object]:
    required = 6 if provider == _HULK else 3
    met = required if progressed else (3 if provider == _HULK else 1)
    side = "long" if progressed else None
    blockers = (
        []
        if progressed
        else ["squeeze_not_armed" if provider == _HULK else "5m_regime_not_admitted"]
    )
    decision = (
        "2026-08-01T12:30:00+00:00" if progressed else "2026-08-01T12:00:00+00:00"
    )
    return {
        "strategy_id": provider,
        "symbol": symbol,
        "decision_time_ms": _milliseconds(decision),
        "reference_price": 100.0,
        "decision_action": "enter_long" if progressed else "hold",
        "eligible": progressed,
        "reason": "eligible" if progressed else "no_trigger",
        "side": side,
        "score": 8 if progressed else 3,
        "minimum_score": 8,
        "trigger": "expansion" if progressed else "none",
        "primary_regime": None,
        "state_1m": None,
        "state_5m": None,
        "context_15m": None,
        "confidence": None,
        "readiness": {
            "side": side,
            "conditions_met": met,
            "conditions_required": required,
            "readiness_fraction": met / required,
            "blockers": blockers,
            "indicators": [f"MET {met}/{required}"],
            "metrics": {"conditions_met": met},
        },
    }


def _intent() -> dict[str, object]:
    return {
        "strategy_id": _HULK,
        "symbol": "BTC",
        "side": "long",
        "decision_time_ms": _milliseconds("2026-08-01T12:30:00+00:00"),
        "reference_price": 100.0,
        "source_reason": "eligible",
    }


def _milliseconds(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("multi_asset_bidirectional_observer_audit", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load observer audit script: {_SCRIPT}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
