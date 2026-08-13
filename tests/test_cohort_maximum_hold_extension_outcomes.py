"""Counterfactual outcome evidence for extended maximum-hold lifecycles."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.cohort_maximum_hold_extension_outcomes import (
    build_maximum_hold_extension_outcomes,
)

_STRATEGY = "hype_breakout_onset_bidirectional_v1"


def test_resolved_extension_compares_actual_exit_with_soft_reference() -> None:
    """The report uses the runtime timer, exact costs, and completed candles."""
    report = build_maximum_hold_extension_outcomes(
        _cohort_rows(include_decision=True),
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "performance_gate": False,
        "balance_gate": False,
    }
    assert report["summary"]["resolved"] == 1
    assert report["summary"]["worse_than_soft_reference"] == 1
    outcome = report["latest_outcomes"][0]
    assert outcome["lifecycle_id"] == "HYPE:11"
    assert outcome["causal_decision_recorded"] is True
    assert outcome["opened_at_ms"] == 60_000
    assert outcome["soft_deadline_timestamp_ms"] == 180_000
    assert outcome["extension_duration_ms"] == 130_000
    assert outcome["soft_reference_price"] == pytest.approx(110.0)
    assert outcome["estimated_soft_exit_price"] == pytest.approx(109.89)
    assert outcome["funding_through_soft_usd"] == pytest.approx(-0.01)
    assert outcome["funding_during_extension_usd"] == pytest.approx(-0.02)
    assert outcome["actual_net_pnl_usd"] == pytest.approx(5.7713477)
    assert outcome["estimated_soft_net_pnl_usd"] == pytest.approx(9.7855495)
    assert outcome["actual_minus_soft_net_usd"] == pytest.approx(-4.0142018)
    path = outcome["path_since_soft_deadline"]
    assert path["status"] == "observed"
    assert path["completed_bars"] == 2
    assert path["first_timestamp_ms"] == 180_000
    assert path["last_timestamp_ms"] == 240_000
    trail = report["post_soft_trail_challenger"]
    assert trail["contract"]["execution_authority"] == "none"
    assert trail["summary_by_giveback_bps"]["30"]["triggered"] == 1
    assert trail["latest_results"][0]["lifecycle_id"] == "HYPE:11"


def test_plan_derived_extension_does_not_fabricate_a_decision_event() -> None:
    """Restart-carried plans remain distinguishable from first-class decisions."""
    report = build_maximum_hold_extension_outcomes(
        _cohort_rows(include_decision=False),
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    outcome = report["latest_outcomes"][0]
    assert outcome["causal_decision_recorded"] is False
    assert outcome["decision_outcome"] is None
    assert outcome["evidence_basis"] == (
        "persisted_runtime_plan_plus_resolved_execution"
    )


def test_fixed_timer_trade_is_not_mislabeled_as_an_extension() -> None:
    """Only an explicitly bound extension policy enters the challenger report."""
    assets = _asset_rows()
    plan = assets[0]["payload"]["execution_plan"]
    plan["maximum_hold_policy"] = "fixed"
    plan["hard_maximum_hold_seconds"] = None

    report = build_maximum_hold_extension_outcomes(
        _cohort_rows(include_decision=False),
        {"HYPE": assets},
        [_trade()],
    )

    assert report["summary"]["bound_extension_lifecycles"] == 0
    assert report["latest_outcomes"] == []


def test_explicit_soft_exit_is_not_mislabeled_as_an_extension() -> None:
    """Ordinary order latency after an exit decision is not extension evidence."""
    cohort = _cohort_rows(include_decision=True)
    cohort[-1]["payload"]["outcome"] = "exit"

    report = build_maximum_hold_extension_outcomes(
        cohort,
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    assert report["summary"]["bound_extension_lifecycles"] == 0
    assert report["latest_outcomes"] == []


def test_terminal_exit_does_not_overwrite_the_soft_extension_decision() -> None:
    """Outcome attribution keeps the causal soft choice and later exit separate."""
    cohort = _cohort_rows(include_decision=True)
    cohort.append(
        {
            "event_type": "maximum_hold_decision",
            "run_id": "run-1",
            "payload": {
                "decision_id": "HYPE:11:terminal_maximum_hold",
                "decision_stage": "terminal",
                "lifecycle_id": "HYPE:11",
                "outcome": "exit",
            },
        }
    )

    report = build_maximum_hold_extension_outcomes(
        cohort,
        {"HYPE": _asset_rows()},
        [_trade()],
    )

    outcome = report["latest_outcomes"][0]
    assert outcome["causal_decision_recorded"] is True
    assert outcome["decision_outcome"] == "extend"


def test_conflicting_persisted_plans_fail_instead_of_guessing() -> None:
    """A lifecycle cannot silently change its timer contract after restart."""
    assets = _asset_rows()
    conflict = deepcopy(assets[0])
    conflict["payload"]["execution_plan"]["maximum_hold_seconds"] = 180
    assets.append(conflict)

    with pytest.raises(ValueError, match="conflicting bound execution plan"):
        build_maximum_hold_extension_outcomes(
            _cohort_rows(include_decision=False),
            {"HYPE": assets},
            [_trade()],
        )


def _cohort_rows(*, include_decision: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "event_type": "market_candles",
            "run_id": "run-1",
            "payload": {
                "timeframe": "1m",
                "bars": {
                    "HYPE": [
                        _bar(120_000, 100.0, 111.0, 99.0, 110.0),
                        _bar(180_000, 110.0, 112.0, 108.0, 109.0),
                        _bar(240_000, 109.0, 111.0, 105.0, 106.0),
                    ]
                },
            },
        }
    ]
    if include_decision:
        rows.append(
            {
                "event_type": "maximum_hold_decision",
                "run_id": "run-1",
                "payload": {
                    "decision_id": "HYPE:11:soft_maximum_hold",
                    "lifecycle_id": "HYPE:11",
                    "outcome": "extend",
                },
            }
        )
    return rows


def _asset_rows() -> list[dict[str, object]]:
    return [
        {
            "event_type": "state_transition",
            "payload": {
                "state": "OPEN",
                "entry_oid": 11,
                "opened_at_ms": 60_000,
                "execution_plan": {
                    "strategy_id": _STRATEGY,
                    "maximum_hold_seconds": 120,
                    "maximum_hold_policy": "extend_while_regime_supported",
                    "hard_maximum_hold_seconds": 600,
                },
            },
        },
        _fill(11, 101, 70_000, 100.0, 1.0, 0.045),
        _funding(120_000, -0.01),
        _funding(240_000, -0.02),
        _fill(22, 202, 310_000, 105.894, 1.0, 0.0476523),
        {
            "event_type": "state_transition",
            "payload": {
                "state": "READY",
                "entry_oid": None,
                "opened_at_ms": None,
                "execution_plan": {
                    "strategy_id": _STRATEGY,
                    "maximum_hold_seconds": 120,
                    "maximum_hold_policy": "extend_while_regime_supported",
                    "hard_maximum_hold_seconds": 600,
                },
            },
        },
    ]


def _trade() -> dict[str, object]:
    return {
        "lifecycle_id": "HYPE:11",
        "symbol": "HYPE",
        "strategy_id": _STRATEGY,
        "side": "long",
        "entry_oid": 11,
        "exit_oid": 22,
        "entry": {
            "venue_timestamp_ms": 70_000,
            "price": 100.0,
            "size": 1.0,
        },
        "exit": {
            "venue_timestamp_ms": 310_000,
            "price": 105.894,
            "size": 1.0,
            "expected_reference_price": 106.0,
        },
        "fees_usd": 0.0926523,
        "funding_usd": -0.03,
        "net_pnl_usd": 5.7713477,
    }


def _fill(
    oid: int,
    trade_id: int,
    timestamp_ms: int,
    price: float,
    size: float,
    fee_usd: float,
) -> dict[str, object]:
    return {
        "event_type": "fill",
        "payload": {
            "oid": oid,
            "trade_id": trade_id,
            "venue_timestamp_ms": timestamp_ms,
            "price": price,
            "size": size,
            "fee_usd": fee_usd,
        },
    }


def _funding(timestamp_ms: int, delta: float) -> dict[str, object]:
    return {
        "event_type": "funding",
        "payload": {"venue_timestamp_ms": timestamp_ms, "usdc_delta": delta},
    }


def _bar(
    timestamp_ms: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }
