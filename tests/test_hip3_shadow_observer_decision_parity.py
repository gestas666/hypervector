"""Observer-versus-archive HIP-3 decision parity tests."""

from __future__ import annotations

import importlib
from typing import Callable

import pytest


def test_matching_observer_and_archive_entries_resolve_pressure_parity() -> None:
    build = _builder()

    report = build(
        signal_parity_report=_signal_report(entry_side="long"),
        observer_rows=(
            _observer_row(2_700_000, eligible=False, side=None),
            _observer_row(3_600_000, eligible=True, side="long"),
        ),
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "promotion_authority": "none",
        "runtime_strategy_changed": False,
    }
    assert report["source"] == {
        "archive_pressure_source": "hyperliquid_ws_l2Book",
        "observer_pressure_source": "hyperliquid_mainnet_l2_rest",
    }
    assert report["technical_assessment"] == {
        "archive_entry_events": 1,
        "comparison_decisions": 2,
        "non_vacuous_entry_comparison": True,
        "observer_archive_pressure_decision_parity_resolved": True,
        "observer_entry_events": 1,
        "pressure_decision_mismatches": 0,
    }
    assert report["decision_diagnostics"] == []


def test_live_rest_entry_absent_from_archive_pressure_is_explicit_mismatch() -> None:
    report = _builder()(
        signal_parity_report=_signal_report(entry_side=None),
        observer_rows=(
            _observer_row(2_700_000, eligible=False, side=None),
            _observer_row(3_600_000, eligible=True, side="long"),
        ),
    )

    assert report["technical_assessment"] == {
        "archive_entry_events": 0,
        "comparison_decisions": 2,
        "non_vacuous_entry_comparison": True,
        "observer_archive_pressure_decision_parity_resolved": False,
        "observer_entry_events": 1,
        "pressure_decision_mismatches": 1,
    }
    assert report["decision_diagnostics"] == [
        {
            "decision_time_ms": 3_600_000,
            "reason": "entry_decision_mismatch",
            "archive_eligible": False,
            "archive_side": None,
            "archive_imbalance_10": 0.4,
            "archive_pressure_exchange_ts_ms": 3_599_000,
            "observer_eligible": True,
            "observer_side": "long",
            "observer_imbalance_10": 0.65,
            "observer_pressure_exchange_ts_ms": 3_596_000,
        }
    ]


def test_ineligible_observer_decision_cannot_carry_an_entry_side() -> None:
    with pytest.raises(ValueError, match="ineligible observer decision has side"):
        _builder()(
            signal_parity_report=_signal_report(entry_side=None),
            observer_rows=(
                _observer_row(2_700_000, eligible=False, side="long"),
                _observer_row(3_600_000, eligible=False, side=None),
            ),
        )


def test_history_incomplete_pressure_row_is_censored_before_freshness_validation() -> (
    None
):
    incomplete = _observer_row(2_700_000, eligible=False, side=None)
    decision = incomplete["decision"]
    assert isinstance(decision, dict)
    decision.update(
        {
            "pressure_fresh": False,
            "pressure_scan_complete": False,
            "pressure_state_history_complete": False,
        }
    )

    report = _builder()(
        signal_parity_report=_signal_report(entry_side="long"),
        observer_rows=(
            incomplete,
            _observer_row(3_600_000, eligible=True, side="long"),
        ),
    )

    assert report["technical_assessment"]["comparison_decisions"] == 1
    assert (
        report["technical_assessment"][
            "observer_archive_pressure_decision_parity_resolved"
        ]
        is True
    )


def _builder() -> Callable[..., dict[str, object]]:
    module = importlib.import_module(
        "hypervector.research.hip3_shadow_observer_decision_parity"
    )
    return module.build_hip3_shadow_observer_decision_parity


def _signal_report(*, entry_side: str | None) -> dict[str, object]:
    event = {
        "bar_open_ms": 2_700_000,
        "decision_time_ms": 3_600_000,
        "side": entry_side,
    }
    events = [] if entry_side is None else [event]
    return {
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "promotion_authority": "none",
            "runtime_strategy_changed": False,
        },
        "scope": {
            "symbol": "xyz:SKHX",
            "provider_id": "hip3_skhx_test_v1",
            "profile_id": "skhx_test_v1",
            "timeframe": "15m",
        },
        "source": {"pressure_source": "hyperliquid_ws_l2Book"},
        "coverage": {
            "decision_start_ms": 2_700_000,
            "decision_end_ms": 3_600_000,
        },
        "reconstructed_entry_events": {"trade": events, "venue": events},
        "reconstructed_pressure_decisions": [
            {
                "decision_time_ms": 2_700_000,
                "fresh": True,
                "imbalance_10": 0.0,
                "last_exchange_ts_ms": 2_699_000,
            },
            {
                "decision_time_ms": 3_600_000,
                "fresh": True,
                "imbalance_10": 0.4,
                "last_exchange_ts_ms": 3_599_000,
            },
        ],
        "technical_assessment": {
            "prospective_signal_source_parity_resolved": True,
        },
    }


def _observer_row(
    decision_time_ms: int, *, eligible: bool, side: str | None
) -> dict[str, object]:
    return {
        "event_type": "skhx_hip3_breakout_shadow_decision",
        "execution_authority": "none",
        "intents": [],
        "report_only": True,
        "runtime_strategy_changed": False,
        "decision": {
            "decision_time_ms": decision_time_ms,
            "eligible": eligible,
            "execution_authority": "none",
            "pressure_fresh": True,
            "decision_imbalance_10": 0.65 if eligible else 0.0,
            "pressure_exchange_ts_ms": decision_time_ms - 4_000,
            "pressure_scan_complete": True,
            "pressure_source": "hyperliquid_mainnet_l2_rest",
            "pressure_state_history_complete": True,
            "profile_id": "skhx_test_v1",
            "prospective": True,
            "provider_id": "hip3_skhx_test_v1",
            "side": side,
            "symbol": "xyz:SKHX",
        },
    }
