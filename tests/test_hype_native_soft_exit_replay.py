"""Exact production-policy replay tests for the restored HYPE route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.research.hype_native_soft_exit_replay import (
    build_hype_native_soft_exit_report,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_hype_native_reconstruction_candidate_v54.toml"
)
_OPENED_MS = 1_000_000
_SOFT_MS = _OPENED_MS + 28_800_000


def test_aligned_fresh_evidence_still_obeys_the_fixed_deadline(tmp_path: Path) -> None:
    """The final fixed contract must not silently retain extension behavior."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS, state="TREND_UP")

    report = build_hype_native_soft_exit_report(
        config_path=_CONFIG,
        ledger_path=ledger,
        opened_at_ms=_OPENED_MS,
        observed_ms=_SOFT_MS,
    )

    assert report["authority"] == "none"
    assert report["counterfactual_no_venue_order"] is True
    assert report["replay_observed_at_utc"] == _utc(_SOFT_MS)
    assert report["decision"]["outcome"] == "exit"
    assert report["decision"]["exit_reason"] == "maximum_hold_seconds"
    assert report["decision"]["structure_alignment_score"] == 1.0
    assert report["decision"]["maximum_hold_evidence_status"] == "not_applicable"
    assert report["selected_ledger_receipts_ms"] == {
        "provider": _SOFT_MS,
        "canonical": _SOFT_MS,
    }
    generator_files = report["input_evidence"]["generator_files"]
    assert len(generator_files) >= 5
    assert all(row["sha256"] for row in generator_files)
    expected = with_observer_ledger_root(
        load_multi_asset_live_config(_CONFIG, mode="observe"), ledger.parent
    )
    assert report["observer_profile_fingerprint"] == expected.profile_fingerprint


def test_opposed_evidence_uses_the_production_soft_exit(tmp_path: Path) -> None:
    """Fresh but opposed structure must produce the configured soft exit."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS, state="TREND_DOWN")

    report = build_hype_native_soft_exit_report(
        config_path=_CONFIG,
        ledger_path=ledger,
        opened_at_ms=_OPENED_MS,
        observed_ms=_SOFT_MS,
    )

    assert report["decision"]["outcome"] == "exit"
    assert report["decision"]["exit_reason"] == "maximum_hold_seconds"
    assert report["decision"]["structure_alignment_score"] == -1.0


def test_fixed_deadline_does_not_depend_on_extension_evidence_age(
    tmp_path: Path,
) -> None:
    """Stale structure cannot extend or otherwise alter the fixed deadline."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS - 60_001, state="TREND_UP")

    report = build_hype_native_soft_exit_report(
        config_path=_CONFIG,
        ledger_path=ledger,
        opened_at_ms=_OPENED_MS,
        observed_ms=_SOFT_MS,
    )

    assert report["decision"]["outcome"] == "exit"
    assert report["decision"]["exit_reason"] == "maximum_hold_seconds"
    assert report["decision"]["maximum_hold_evidence_status"] == "not_applicable"


def test_future_received_evidence_is_not_causally_available(tmp_path: Path) -> None:
    """A later ledger receipt cannot influence an earlier soft decision."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS + 1, state="TREND_UP")

    with pytest.raises(ValueError, match="provider evaluation is unavailable"):
        build_hype_native_soft_exit_report(
            config_path=_CONFIG,
            ledger_path=ledger,
            opened_at_ms=_OPENED_MS,
            observed_ms=_SOFT_MS,
        )


def test_evaluation_decision_cannot_follow_its_ledger_receipt(tmp_path: Path) -> None:
    """Malformed event ordering must abort rather than leak future evidence."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS - 1, state="TREND_UP")
    rows = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        evaluations = row["payload"].get("evaluations", [])
        for evaluation in evaluations:
            evaluation["decision_time_ms"] = _SOFT_MS
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="decision follows ledger receipt"):
        build_hype_native_soft_exit_report(
            config_path=_CONFIG,
            ledger_path=ledger,
            opened_at_ms=_OPENED_MS,
            observed_ms=_SOFT_MS,
        )


def test_unrelated_observer_identity_is_rejected(tmp_path: Path) -> None:
    """Provider payloads cannot alias a different observer configuration."""
    ledger = tmp_path / "decisions.jsonl"
    _write_evidence(ledger, observed_ms=_SOFT_MS, state="TREND_UP")
    rows = [
        json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
    ]
    rows[0]["profile_fingerprint"] = "wrong-observer"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    with pytest.raises(ValueError, match="observer profile fingerprint differs"):
        build_hype_native_soft_exit_report(
            config_path=_CONFIG,
            ledger_path=ledger,
            opened_at_ms=_OPENED_MS,
            observed_ms=_SOFT_MS,
        )


def _write_evidence(path: Path, *, observed_ms: int, state: str) -> None:
    rows = (
        _identity(path, observed_ms),
        _event(
            "intent_routing",
            observed_ms,
            _evaluation(
                "hype_native_breakout_onset_bidirectional_v2", state, observed_ms
            ),
        ),
        _event(
            "canonical_regime_evaluations",
            observed_ms,
            _evaluation("canonical_regime_telemetry_v1", state, observed_ms),
        ),
    )
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _identity(path: Path, observed_ms: int) -> dict[str, object]:
    config = with_observer_ledger_root(
        load_multi_asset_live_config(_CONFIG, mode="observe"), path.parent
    )
    return {
        "event_type": "configuration_identity",
        "observed_at_utc": _utc(observed_ms - 1),
        "profile_id": config.profile_id,
        "profile_fingerprint": config.profile_fingerprint,
        "run_id": "bidirectional-observe-test",
        "execution_mode": "observe",
        "execution_authority": "none",
        "payload": {
            "profile_fingerprint": config.profile_fingerprint,
            "config_source_path": str(_CONFIG),
        },
    }


def _event(
    kind: str, observed_ms: int, evaluation: dict[str, object]
) -> dict[str, object]:
    return {
        "event_type": kind,
        "observed_at_utc": _utc(observed_ms),
        "payload": {"evaluations": [evaluation]},
    }


def _evaluation(
    strategy_id: str,
    state: str,
    decision_time_ms: int,
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": "HYPE",
        "decision_time_ms": decision_time_ms,
        "reference_price": 59.0,
        "decision_action": "hold",
        "eligible": False,
        "reason": "test_evidence",
        "side": "long",
        "primary_regime": state,
        "state_1m": state,
        "state_5m": state,
        "context_15m": state,
        "readiness": {
            "side": "long",
            "conditions_met": 1,
            "conditions_required": 1,
            "blockers": [],
            "indicators": ["TEST EVIDENCE"],
            "metrics": {"structural_direction": "long"},
        },
    }


def _utc(value_ms: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value_ms / 1_000, tz=UTC).isoformat()
