"""Tests for exact-contract all-asset breakout forward evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_breakout_policy_contract import (
    breakout_policy_forward_spec,
)
from hypervector.research.cohort_breakout_policy_forward import (
    BreakoutPolicyForwardSpec,
    build_breakout_policy_forward_report,
)

_RUN_ID = "breakout-source-run"
_BREAKOUT = "hype_breakout_onset_bidirectional_v1"
_CANONICAL = "range_onset_bidirectional_v1"
_V11 = "configs/multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11.toml"
_V14 = "configs/multi_asset_bidirectional_hype75_all_asset_breakout_canary_v14.toml"


def test_supported_soft_boundary_extends_then_exits_when_support_is_lost() -> None:
    """The counterfactual must use the same causal 0.50 support threshold as live."""
    records = [_identity()]
    records.extend(
        _routing(time_ms, provider_state=state, canonical_state=state, entry=entry)
        for time_ms, state, entry in (
            (60_000, "TREND_UP", "long"),
            (120_000, "TREND_UP", None),
            (180_000, "TREND_UP", None),
            (240_000, "RANGE", None),
        )
    )
    records.append(
        _candles(
            _bar(60_000, high=100.8, low=99.9, close=100.5),
            _bar(120_000, high=101.2, low=100.0, close=101.0),
            _bar(180_000, high=101.1, low=100.8, close=101.0),
        )
    )

    report = build_breakout_policy_forward_report(records, spec=_spec())

    lifecycle = report["lifecycles"][0]
    assert lifecycle["status"] == "resolved"
    assert lifecycle["exit_reason"] == "maximum_hold_seconds"
    assert lifecycle["exit_time_ms"] == 240_000
    assert lifecycle["soft_decision"] == {
        "decision_time_ms": 180_000,
        "outcome": "extend",
        "structure_alignment_score": pytest.approx(1.0),
        "structure_alignment_threshold": 0.5,
    }
    assert lifecycle["terminal_structure_alignment_score"] == pytest.approx(0.0)
    assert report["contract"]["execution_authority"] == "none"
    assert report["contract"]["counterfactual_fill_claimed_as_actual"] is False


def test_hard_deadline_exits_even_while_structure_remains_supported() -> None:
    """Support may extend the soft timer but cannot bypass the hard cap."""
    records = [_identity()]
    records.extend(
        _routing(
            time_ms,
            provider_state="TREND_UP",
            canonical_state="TREND_UP",
            entry="long" if time_ms == 60_000 else None,
            reference=100.0 + time_ms / 120_000,
        )
        for time_ms in (60_000, 120_000, 180_000, 240_000, 300_000)
    )
    records.append(
        _candles(
            *(
                _bar(time_ms, high=103.0, low=99.9, close=101.0)
                for time_ms in (60_000, 120_000, 180_000, 240_000)
            )
        )
    )

    report = build_breakout_policy_forward_report(records, spec=_spec())

    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "hard_maximum_hold_seconds"
    assert lifecycle["exit_time_ms"] == 300_000
    assert lifecycle["soft_decision"]["outcome"] == "extend"


def test_protective_stop_precedes_any_timer_decision() -> None:
    """The 80-bps venue barrier remains the first modeled lifecycle defense."""
    records = [
        _identity(),
        _routing(
            60_000,
            provider_state="TREND_UP",
            canonical_state="TREND_UP",
            entry="long",
        ),
        _candles(_bar(60_000, high=100.2, low=99.1, close=99.4)),
    ]

    report = build_breakout_policy_forward_report(records, spec=_spec())

    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "protective_stop"
    assert lifecycle["exit_price"] == pytest.approx(99.2)
    assert lifecycle["gross_return_bps"] == pytest.approx(-80.0)
    assert lifecycle["estimated_net_return_bps"] == pytest.approx(-93.0)


def test_opposite_eligible_onset_closes_without_same_cycle_reversal() -> None:
    """The live enter-and-close router consumes an opposite onset as a close."""
    records = [
        _identity(),
        _routing(
            60_000,
            provider_state="TREND_UP",
            canonical_state="TREND_UP",
            entry="long",
        ),
        _routing(
            180_000,
            provider_state="TREND_DOWN",
            canonical_state="TREND_DOWN",
            entry="short",
            reference=99.5,
        ),
        _candles(
            _bar(60_000, high=100.2, low=99.8, close=100.0),
            _bar(120_000, high=100.1, low=99.6, close=99.7),
        ),
    ]

    report = build_breakout_policy_forward_report(
        records,
        spec=_spec(soft_hold_minutes=3),
    )

    assert report["summary"]["eligible_signals"] == 2
    assert report["summary"]["opposite_close_signals"] == 1
    assert len(report["lifecycles"]) == 1
    lifecycle = report["lifecycles"][0]
    assert lifecycle["exit_reason"] == "opposite_strategy_intent"
    assert lifecycle["exit_time_ms"] == 180_000
    assert lifecycle["side"] == "long"


def test_spec_factory_binds_v11_observer_to_unchanged_v14_breakout_contract() -> None:
    """The audit may widen authority only when the observed strategy bytes agree."""
    source = load_multi_asset_live_config(_V11, mode="observe")
    candidate = load_multi_asset_live_config(_V14, mode="observe")
    identity = _identity()
    identity["observed_at_utc"] = "1970-01-01T00:00:01+00:00"
    identity["payload"] = {"profile_fingerprint": source.profile_fingerprint}

    spec = breakout_policy_forward_spec(
        source,
        candidate,
        [identity],
        run_id=_RUN_ID,
    )

    assert spec.source_strategy_id == _BREAKOUT
    assert spec.source_run_id == _RUN_ID
    assert spec.cutoff_time_ms == 1_000
    assert spec.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert spec.source_execution_symbols == ("HYPE",)
    assert spec.competing_execution_providers_by_symbol == {
        "BTC": ("hulk_expansion_bidirectional_tuned_v2",)
    }
    assert spec.stop_bps == 80.0
    assert spec.soft_hold_minutes == 480
    assert spec.hard_hold_minutes == 1_440
    assert spec.maximum_entry_delay_seconds == 60
    assert spec.modeled_round_trip_friction_bps == 13.0
    assert spec.notional_usd_by_symbol == {
        "BTC": 25.0,
        "ETH": 25.0,
        "SOL": 75.0,
        "HYPE": 75.0,
    }


def test_unresolved_lifecycle_prevents_inventing_a_later_flat_entry() -> None:
    """Missing candles cannot be converted into an assumed close and fresh trade."""
    records = [
        _identity(),
        _routing(
            60_000,
            provider_state="TREND_UP",
            canonical_state="TREND_UP",
            entry="long",
        ),
        _routing(
            360_000,
            provider_state="TREND_DOWN",
            canonical_state="TREND_DOWN",
            entry="short",
        ),
        _candles(_bar(60_000, high=100.1, low=99.9, close=100.0)),
    ]

    report = build_breakout_policy_forward_report(records, spec=_spec())

    assert report["summary"]["eligible_signals"] == 2
    assert report["summary"]["lifecycles"] == 1
    assert report["summary"]["pending"] == 1
    assert report["lifecycles"][0]["status"] == "pending"


def test_summary_excludes_conflicts_and_seed_rows_from_other_process_runs() -> None:
    """Generation counters must describe only the source run bound by the spec."""
    prior_identity = _event(
        1,
        "configuration_identity",
        {},
        observed_at_utc="1969-12-31T23:58:00+00:00",
        run_id="prior-run",
    )
    prior_conflict = _event(
        2,
        "intent_routing",
        {
            "evaluations": [
                {
                    "strategy_id": "prior_provider",
                    "symbol": "BTC",
                    "decision_time_ms": 0,
                    "reference_price": 100.0,
                    "eligible": False,
                    "side": "long",
                    "readiness": {
                        "side": "short",
                        "blockers": ["prior"],
                        "metrics": {},
                    },
                }
            ]
        },
        observed_at_utc="1969-12-31T23:58:01+00:00",
        run_id="prior-run",
    )
    records = [
        prior_identity,
        prior_conflict,
        _identity(),
        _routing(
            60_000,
            provider_state="TREND_UP",
            canonical_state="TREND_UP",
            entry="long",
        ),
        _candles(_bar(60_000, high=100.1, low=99.9, close=100.0)),
    ]

    report = build_breakout_policy_forward_report(records, spec=_spec())

    assert report["summary"]["direction_conflicts"] == 0
    assert report["summary"]["preactivation_annotations_excluded"] == 0


def test_lifecycle_retains_breakout_relation_for_aligned_vs_fade_analysis() -> None:
    """Entry attribution must survive policy replay without becoming an entry gate."""
    routing = _routing(
        60_000,
        provider_state="TREND_UP",
        canonical_state="TREND_UP",
        entry="long",
    )
    provider = routing["payload"]["evaluations"][0]
    provider["confidence"] = 0.75
    provider["readiness"]["metrics"].update(
        {
            "breakout_side": "short",
            "breakout_side_relation": "opposed",
            "confidence": 0.75,
            "entry_feature_status": "measured",
        }
    )
    records = [
        _identity(),
        routing,
        _candles(_bar(60_000, high=100.1, low=99.0, close=99.2)),
    ]

    report = build_breakout_policy_forward_report(records, spec=_spec())

    assert report["lifecycles"][0]["entry_attribution"] == {
        "breakout_side": "short",
        "breakout_side_relation": "opposed",
        "confidence": 0.75,
        "entry_feature_status": "measured",
    }


def test_report_discloses_unmodeled_executable_provider_contention() -> None:
    """A competing eligible provider must prevent an exact-router claim."""
    routing = _routing(
        60_000,
        provider_state="TREND_UP",
        canonical_state="TREND_UP",
        entry="long",
    )
    routing["payload"]["evaluations"].append(
        _evaluation(
            "hulk_expansion_bidirectional_tuned_v2", 60_000, "TREND_UP", "long", 100.0
        )
    )
    records = [
        _identity(),
        routing,
        _candles(_bar(60_000, high=100.1, low=99.0, close=99.2)),
    ]
    spec = replace(
        _spec(),
        competing_execution_providers_by_symbol={
            "HYPE": ("hulk_expansion_bidirectional_tuned_v2",)
        },
    )

    report = build_breakout_policy_forward_report(records, spec=spec)

    assert report["summary"]["competing_executable_eligible_signals"] == 1
    assert report["summary"]["router_contention_status"] == "not_modeled"
    assert report["contract"]["cross_provider_router_contention_modeled"] is False


def _spec(*, soft_hold_minutes: int = 2) -> BreakoutPolicyForwardSpec:
    return BreakoutPolicyForwardSpec(
        source_strategy_id=_BREAKOUT,
        source_run_id=_RUN_ID,
        cutoff_time_ms=1,
        symbols=("HYPE",),
        source_execution_symbols=("HYPE",),
        competing_execution_providers_by_symbol={},
        stop_bps=80.0,
        soft_hold_minutes=soft_hold_minutes,
        hard_hold_minutes=4,
        maximum_entry_delay_seconds=60,
        modeled_round_trip_friction_bps=13.0,
        notional_usd_by_symbol={"HYPE": 75.0},
    )


def _identity() -> dict[str, object]:
    return _event(
        1,
        "configuration_identity",
        {},
        observed_at_utc="1970-01-01T00:00:00+00:00",
    )


def _routing(
    time_ms: int,
    *,
    provider_state: str,
    canonical_state: str,
    entry: str | None,
    reference: float = 100.0,
) -> dict[str, object]:
    evaluations = [
        _evaluation(
            _BREAKOUT,
            time_ms,
            provider_state,
            entry,
            reference,
        ),
        _evaluation(
            _CANONICAL,
            time_ms,
            canonical_state,
            None,
            reference,
        ),
    ]
    return _event(
        time_ms // 60_000 + 1,
        "intent_routing",
        {"evaluations": evaluations, "actions": [], "withheld": []},
        observed_at_utc=f"1970-01-01T00:{time_ms // 60_000:02d}:00.500000+00:00",
    )


def _evaluation(
    strategy_id: str,
    time_ms: int,
    state: str,
    entry: str | None,
    reference: float,
) -> dict[str, object]:
    structural = (
        "long"
        if state == "TREND_UP"
        else "short"
        if state == "TREND_DOWN"
        else "neutral"
    )
    side = entry or (structural if structural != "neutral" else None)
    return {
        "strategy_id": strategy_id,
        "symbol": "HYPE",
        "decision_time_ms": time_ms,
        "reference_price": reference,
        "eligible": entry is not None,
        "side": side,
        "primary_regime": state,
        "state_1m": state,
        "state_5m": state,
        "context_15m": state,
        "readiness": {
            "side": side,
            "blockers": [] if entry else ["not_onset"],
            "metrics": {"structural_direction": structural},
        },
    }


def _candles(*bars: dict[str, object]) -> dict[str, object]:
    return _event(
        99,
        "market_candles",
        {"timeframe": "1m", "bars": {"HYPE": list(bars)}},
        observed_at_utc="1970-01-01T00:10:00+00:00",
    )


def _bar(
    timestamp_ms: int,
    *,
    high: float,
    low: float,
    close: float,
) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp_ms,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
    }


def _event(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    observed_at_utc: str,
    run_id: str = _RUN_ID,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "event_type": event_type,
        "run_id": run_id,
        "observed_at_utc": observed_at_utc,
        "payload": payload,
    }
