"""Tests for exact-policy prospective eligible-signal evidence."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvent,
    EligiblePolicyFundingEvidence,
)
from hypervector.research.cohort_eligible_policy_forward import (
    EligiblePolicyForwardSpec,
    build_eligible_policy_forward_report,
    eth_transfer_forward_spec,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


RUN_ID = "live-run-eth"
STRATEGY_ID = "eth_breakout_precompression_pullback_bidirectional_v1"
CANDIDATE_ID = "eth_breakout_precompression_pullback_bidirectional_v1_eligible_forward"


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    observed_at_utc: str,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "run_id": RUN_ID,
        "observed_at_utc": observed_at_utc,
        "payload": payload,
    }


def _identity() -> dict[str, object]:
    return _event(
        1,
        "configuration_identity",
        {},
        observed_at_utc="1970-01-01T00:00:00+00:00",
    )


def _snapshot() -> dict[str, object]:
    return _event(
        2,
        "cohort_snapshot",
        {
            "open_position_count": 1,
            "assets": [
                {
                    "symbol": "ETH",
                    "state": "FLAT",
                    "position_side": None,
                    "execution_plan": None,
                }
            ],
        },
        observed_at_utc="1970-01-01T00:00:59+00:00",
    )


def _routing() -> dict[str, object]:
    evaluation = {
        "strategy_id": STRATEGY_ID,
        "symbol": "ETH",
        "decision_time_ms": 60_000,
        "reference_price": 100.0,
        "eligible": True,
        "side": "long",
        "readiness": {
            "side": "long",
            "blockers": [],
            "metrics": {
                "stop_bps": 60.0,
                "maximum_hold_seconds": 43_200,
            },
        },
    }
    return _event(
        3,
        "intent_routing",
        {
            "evaluations": [evaluation],
            "actions": [],
            "withheld": [
                {
                    "strategy_id": STRATEGY_ID,
                    "symbol": "ETH",
                    "reason": "provider_symbol_observe_only",
                }
            ],
        },
        observed_at_utc="1970-01-01T00:01:00.500000+00:00",
    )


def _candles(*bars: dict[str, object]) -> dict[str, object]:
    return _event(
        4,
        "market_candles",
        {"timeframe": "1m", "bars": {"ETH": list(bars)}},
        observed_at_utc="1970-01-01T00:02:00+00:00",
    )


def _bar(
    timestamp_ms: int,
    *,
    open_price: float = 100.0,
    high: float = 100.1,
    low: float = 99.9,
    close: float = 100.0,
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


def _spec() -> EligiblePolicyForwardSpec:
    return EligiblePolicyForwardSpec(
        source_strategy_id=STRATEGY_ID,
        candidate_strategy_id=CANDIDATE_ID,
        symbol="ETH",
        source_run_id=RUN_ID,
        cutoff_time_ms=1,
        stop_bps=60.0,
        maximum_hold_minutes=720,
        modeled_round_trip_friction_bps=13.0,
        notional_usd=25.0,
        maximum_positions=4,
    )


def test_stop_touch_resolves_exact_candidate_before_maximum_hold() -> None:
    records = [
        _identity(),
        _snapshot(),
        _routing(),
        _candles(_bar(60_000, low=99.3, close=99.5)),
    ]

    report = build_eligible_policy_forward_report(records, spec=_spec())

    assert report["state"] == "descriptive_resolved_forward_evidence"
    assert report["summary"] == {
        "eligible_signals": 1,
        "selected_non_overlapping": 1,
        "overlapping_excluded": 0,
        "resolved": 1,
        "pending": 0,
        "missing_data": 0,
        "wins": 0,
        "losses": 1,
        "total_estimated_net_before_funding_bps": pytest.approx(-73.0),
        "profit_factor_before_funding": 0.0,
        "total_estimated_net_after_funding_bps": None,
        "profit_factor_after_funding": None,
    }
    execution = report["latest_executions"][0]
    assert execution["exit_reason"] == "protective_stop"
    assert execution["gross_return_bps"] == pytest.approx(-60.0)
    assert execution["net_return_bps"] == pytest.approx(-73.0)
    assert execution["simulated_net_pnl_usd"] == pytest.approx(-0.1825)
    assert report["portfolio_journal"]["summary"]["deployable_resolved"] == 1
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["funding_included"] is False


def test_resolved_candidate_includes_complete_official_funding_evidence() -> None:
    """A covered counterfactual reports after-funding economics explicitly."""
    records = [
        _identity(),
        _snapshot(),
        _routing(),
        _candles(_bar(60_000, low=99.3, close=99.5)),
    ]
    funding = EligiblePolicyFundingEvidence(
        symbol="ETH",
        requested_start_ms=1,
        requested_end_ms=120_000,
        events=(
            EligiblePolicyFundingEvent(
                timestamp_ms=90_000,
                funding_rate=0.00001,
            ),
        ),
    )

    report = build_eligible_policy_forward_report(
        records,
        spec=_spec(),
        funding_evidence=funding,
    )

    execution = report["latest_executions"][0]
    assert execution["funding_bps"] == pytest.approx(-0.1)
    assert execution["net_return_before_funding_bps"] == pytest.approx(-73.0)
    assert execution["net_return_bps"] == pytest.approx(-73.1)
    assert execution["net_return_scope"] == "modeled_friction_and_official_funding"
    assert execution["simulated_net_pnl_usd"] == pytest.approx(-0.18275)
    assert report["summary"]["total_estimated_net_after_funding_bps"] == (
        pytest.approx(-73.1)
    )
    assert report["summary"]["total_estimated_net_before_funding_bps"] == (
        pytest.approx(-73.0)
    )
    assert report["summary"]["profit_factor_after_funding"] == 0.0
    assert report["contract"]["funding_included"] is True
    assert report["contract"]["funding_source"] == "hl_funding_history"
    assert any(
        "official funding settlements are included" in limitation
        for limitation in report["limitations"]
    )
    assert not any(
        "excludes subsequently realized funding" in limitation
        for limitation in report["limitations"]
    )


def test_stop_resolution_excludes_candles_after_the_exit() -> None:
    records = [
        _identity(),
        _snapshot(),
        _routing(),
        _candles(
            _bar(60_000, high=100.1, low=99.3, close=99.5),
            _bar(120_000, high=110.0, low=99.5, close=109.0),
        ),
    ]

    report = build_eligible_policy_forward_report(records, spec=_spec())

    execution = report["latest_executions"][0]
    assert execution["mfe_bps"] == pytest.approx(10.0)
    assert execution["mae_bps"] == pytest.approx(-70.0)


def test_unfinished_path_stays_pending_without_claiming_funding() -> None:
    records = [
        _identity(),
        _snapshot(),
        _routing(),
        _candles(_bar(60_000, high=100.2, low=99.9, close=100.1)),
    ]

    report = build_eligible_policy_forward_report(records, spec=_spec())

    assert report["state"] == "awaiting_exact_policy_resolution"
    assert report["summary"]["resolved"] == 0
    assert report["summary"]["pending"] == 1
    attempt = report["latest_attempts"][0]
    assert attempt["status"] == "exit_pending"
    assert attempt["current_estimated_net_before_funding_bps"] == pytest.approx(-3.0)
    assert attempt["remaining_ms"] == 719 * 60_000
    assert attempt["funding_bps"] is None
    assert report["portfolio_journal"]["summary"]["pending"] == 1


def test_pending_candidate_reports_only_funding_observed_through_latest_bar() -> None:
    """Pending after-funding mark uses only fully covered settlements."""
    funding = EligiblePolicyFundingEvidence(
        symbol="ETH",
        requested_start_ms=1,
        requested_end_ms=120_000,
        events=(
            EligiblePolicyFundingEvent(
                timestamp_ms=90_000,
                funding_rate=0.00001,
            ),
        ),
    )
    records = [
        _identity(),
        _snapshot(),
        _routing(),
        _candles(_bar(60_000, high=100.2, low=99.9, close=100.1)),
    ]

    report = build_eligible_policy_forward_report(
        records,
        spec=_spec(),
        funding_evidence=funding,
    )

    attempt = report["latest_attempts"][0]
    assert attempt["funding_bps"] == pytest.approx(-0.1)
    assert attempt["current_estimated_net_before_funding_bps"] == pytest.approx(-3.0)
    assert attempt["current_estimated_net_after_funding_bps"] == pytest.approx(-3.1)


def test_eth_spec_is_derived_from_the_exact_runtime_profile() -> None:
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/evidence_routed_hype75_eth_observer.toml",
        mode="observe",
    )
    identity = _identity()
    identity["observed_at_utc"] = "1970-01-01T00:00:01+00:00"
    identity["payload"] = {"profile_fingerprint": config.profile_fingerprint}

    spec = eth_transfer_forward_spec(config, [identity], run_id=RUN_ID)

    assert spec.source_strategy_id == STRATEGY_ID
    assert spec.candidate_strategy_id == CANDIDATE_ID
    assert spec.symbol == "ETH"
    assert spec.source_run_id == RUN_ID
    assert spec.stop_bps == 60.0
    assert spec.maximum_hold_minutes == 720
    assert spec.modeled_round_trip_friction_bps == 13.0
    assert spec.notional_usd == 25.0
    assert spec.maximum_positions == 4


def test_unrelated_noneligible_direction_conflict_does_not_hide_eth_evidence() -> None:
    routing = _routing()
    routing["payload"]["evaluations"].append(
        {
            "strategy_id": "unrelated_provider",
            "symbol": "BTC",
            "decision_time_ms": 60_000,
            "reference_price": 50_000.0,
            "eligible": False,
            "side": "long",
            "readiness": {
                "side": "short",
                "blockers": ["not_ready"],
                "metrics": {},
            },
        }
    )
    records = [
        _identity(),
        _snapshot(),
        routing,
        _candles(_bar(60_000, low=99.3, close=99.5)),
    ]

    report = build_eligible_policy_forward_report(records, spec=_spec())

    assert report["summary"]["eligible_signals"] == 1
    assert report["summary"]["resolved"] == 1
