"""Tests for exact cross-process provider-evaluation parity."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import importlib

import pytest

Record = Mapping[str, object]


def _builder() -> Callable[..., dict[str, object]]:
    try:
        module = importlib.import_module(
            "hypervector.research.cohort_provider_evaluation_parity"
        )
    except ModuleNotFoundError:
        pytest.fail("cohort provider-evaluation parity is not implemented")
    return module.build_cohort_provider_evaluation_parity


def _row(*, live: bool, source: str, sma_gap: float = 35.0) -> dict[str, object]:
    authority = "automatic_execution" if live else "report_only"
    execution = "AUTOMATIC EXECUTION" if live else "REPORT ONLY"
    evaluation = {
        "strategy_id": "provider-v1",
        "symbol": "HYPE",
        "decision_time_ms": 123_000,
        "reference_price": 58.834,
        "decision_action": "hold",
        "eligible": False,
        "reason": "compression_absent",
        "side": "long",
        "target_anchor": None,
        "readiness": {
            "blockers": ["compression_absent", "pullback_absent"],
            "conditions_met": 2,
            "conditions_required": 5,
            "indicators": [f"EXIT 80BPS STOP [{execution}]"],
            "metrics": {
                "candidate_authority": authority,
                "entry_policy_authority": authority,
                "stop_bps": 80.0,
                "sma_gap_directional_bps": sma_gap,
            },
        },
    }
    return {
        "event_type": "intent_routing",
        "sequence": 1,
        "observed_at_utc": "2026-08-18T16:20:15+00:00",
        "execution_mode": "live" if live else "observe",
        "effective_mode": "LIVE ARMED" if live else "OBSERVE ONLY",
        "live_armed": live,
        "execution_authority": "hyperliquid_mainnet" if live else "none",
        "profile_id": f"{source}-profile",
        "profile_fingerprint": f"{source}-fingerprint",
        "run_fingerprint": f"{source}-run-fingerprint",
        "run_id": f"{source}-run",
        "payload": {"evaluations": [evaluation]},
    }


def _report(*, changed_stop: bool = False) -> dict[str, object]:
    rows = {
        "live": _row(live=True, source="live"),
        "observer_a": _row(live=False, source="observer-a", sma_gap=35.0 + 1e-12),
        "observer_b": _row(live=False, source="observer-b"),
    }
    if changed_stop:
        metrics = rows["observer_b"]["payload"]["evaluations"][0]["readiness"][
            "metrics"
        ]
        metrics["stop_bps"] = 60.0
    return _builder()(
        rows_by_source=rows,
        source_kinds={
            "live": "live",
            "observer_a": "observer",
            "observer_b": "observer",
        },
        provider_id="provider-v1",
        symbol="HYPE",
        decision_time_ms=123_000,
    )


def test_authority_only_differences_preserve_semantic_parity() -> None:
    """Expected authority labels and float noise must not create a mismatch."""
    report = _report()

    assert report["technical_assessment"] == {
        "semantic_parity_resolved": True,
        "compared_sources": 3,
        "semantic_mismatches": 0,
    }
    assert report["mismatches"] == []
    assert report["contract"]["execution_authority"] == "none"


def test_stop_difference_falsifies_semantic_parity() -> None:
    """A strategy-risk difference must be visible and fail the comparison."""
    report = _report(changed_stop=True)

    assert report["technical_assessment"]["semantic_parity_resolved"] is False
    assert report["mismatches"] == [
        {
            "source": "observer_b",
            "path": "readiness.metrics.stop_bps",
            "live": 80.0,
            "observed": 60.0,
        }
    ]
