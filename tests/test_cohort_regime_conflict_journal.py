"""Causal evidence for regime-aware same-symbol routing conflicts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hypervector.research.cohort_regime_conflict_journal import (
    build_regime_conflict_journal,
)

_DECISION_MS = 1_785_600_000_000
_LOW_PRIORITY = "regime_selected"
_HIGH_PRIORITY = "static_selected"


def test_inactive_legacy_policy_is_explicitly_not_evaluated() -> None:
    """A preactivation ledger cannot masquerade as regime-routing evidence."""
    identity = _identity()
    identity["payload"].pop("routing_policy")

    report = build_regime_conflict_journal(_records(), identity)

    assert report["state"] == "not_active"
    assert report["conflicts"] == 0
    assert report["journal"] == []
    assert report["contract"]["execution_authority"] == "none"


def test_opposite_direction_conflict_compares_regime_and_static_paths() -> None:
    """Forward candles quantify the choice without inventing fills or PnL."""
    report = build_regime_conflict_journal(_records(), _identity())

    assert report["state"] == "active"
    assert report["conflicts"] == 1
    assert report["conflicts_changing_static_choice"] == 1
    assert report["directionally_comparable_conflicts"] == 1
    assert report["same_direction_provider_only"] == 0
    assert report["preactivation_conflicts_excluded"] == 0
    conflict = report["journal"][0]
    assert conflict["selected"]["strategy_id"] == _LOW_PRIORITY
    assert conflict["static_priority_choice"]["strategy_id"] == _HIGH_PRIORITY
    assert conflict["selection_changed"] is True
    assert conflict["comparison"] == "opposite_direction"
    five = conflict["horizons"]["5"]
    assert five["status"] == "resolved"
    assert five["regime_selected_return_bps"] == pytest.approx(500.0)
    assert five["static_priority_return_bps"] == pytest.approx(-500.0)
    assert five["regime_advantage_bps"] == pytest.approx(1_000.0)
    summary = report["horizons"]["5"]
    assert summary["resolved"] == 1
    assert summary["non_overlapping_resolved"] == 1
    assert summary["regime_preference_wins"] == 1
    assert summary["static_priority_wins"] == 0
    assert summary["ties"] == 0
    assert summary["mean_regime_advantage_bps"] == pytest.approx(1_000.0)
    assert report["contract"] == {
        "report_only": True,
        "counterfactual_only": True,
        "fills_assumed": False,
        "pnl_claimed": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def test_same_direction_provider_change_does_not_claim_directional_edge() -> None:
    """Execution-plan differences require fills and cannot be inferred from bars."""
    rows = _records()
    alternative = rows[1]["payload"]["withheld"][0]
    alternative["side"] = "long"

    report = build_regime_conflict_journal(rows, _identity())

    assert report["conflicts_changing_static_choice"] == 1
    assert report["directionally_comparable_conflicts"] == 0
    assert report["same_direction_provider_only"] == 1
    conflict = report["journal"][0]
    assert conflict["comparison"] == "same_direction_provider_only"
    assert conflict["horizons"] == {}
    assert report["horizons"]["5"]["resolved"] == 0


def test_right_edge_is_censored_without_using_partial_future_data() -> None:
    """A horizon remains unresolved until its complete candle path exists."""
    rows = _records(candle_count=5)

    report = build_regime_conflict_journal(rows, _identity())

    assert report["horizons"]["5"]["resolved"] == 1
    assert report["horizons"]["15"]["censored"] == 1
    assert report["journal"][0]["horizons"]["15"] == {"status": "censored"}


def test_preactivation_conflict_is_excluded() -> None:
    """Restart seed rows cannot become forward evidence."""
    rows = _records()
    identity = _identity()
    identity["observed_at_utc"] = _iso(_DECISION_MS)

    report = build_regime_conflict_journal(rows, identity)

    assert report["conflicts"] == 0
    assert report["preactivation_conflicts_excluded"] == 1


def test_conflict_requires_one_unambiguous_selected_intent() -> None:
    """Malformed routing telemetry fails instead of shaping a plausible report."""
    rows = _records()
    rows[1]["payload"]["actions"] = []

    with pytest.raises(ValueError, match="selected intent"):
        build_regime_conflict_journal(rows, _identity())


def test_ungated_standalone_action_does_not_require_regime_annotation() -> None:
    """A no-conflict route must not be parsed as regime-selection evidence."""
    rows = _records()
    action = rows[1]["payload"]["actions"][0]
    rows[1]["payload"]["withheld"] = []
    for key in (
        "regime_alignment_score",
        "regime_alignment_stance",
        "regime_decision_time_ms",
        "regime_alignment_basis",
    ):
        action[key] = None

    report = build_regime_conflict_journal(rows, _identity())

    assert report["conflicts"] == 0
    assert report["journal"] == []


def _records(*, candle_count: int = 60) -> list[dict[str, object]]:
    return [
        _row(1, "configuration_identity", _identity()["payload"]),
        _row(
            2,
            "intent_routing",
            {
                "evaluations": [],
                "actions": [_candidate(_LOW_PRIORITY, "long", 1.0, action="enter")],
                "withheld": [
                    {
                        **_candidate(_HIGH_PRIORITY, "short", -1.0),
                        "reason": "lower_regime_alignment",
                    }
                ],
            },
        ),
        _row(
            3,
            "market_candles",
            {
                "timeframe": "1m",
                "bars": {"BTC": _bars(candle_count)},
            },
        ),
    ]


def _identity() -> dict[str, object]:
    return _row(
        1,
        "configuration_identity",
        {
            "strategy_name": "multi_asset_bidirectional_cohort",
            "enabled_symbols": ["BTC"],
            "routing_policy": {
                "mode": "same_symbol_conflict_preference_v1",
                "alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
                "standalone_intents_ungated": True,
                "forced_regime_exit": False,
                "fallback": "provider_priority_then_decision_time",
            },
            "providers": [
                {
                    "strategy_id": _LOW_PRIORITY,
                    "symbols": ["BTC"],
                    "execution_symbols": ["BTC"],
                    "priority": 10,
                },
                {
                    "strategy_id": _HIGH_PRIORITY,
                    "symbols": ["BTC"],
                    "execution_symbols": ["BTC"],
                    "priority": 30,
                },
            ],
        },
    )


def _candidate(
    strategy_id: str,
    side: str,
    score: float,
    *,
    action: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "strategy_id": strategy_id,
        "symbol": "BTC",
        "side": side,
        "decision_time_ms": _DECISION_MS,
        "reference_price": 100.0,
        "regime_alignment_score": score,
        "regime_alignment_stance": (
            "directionally_supported" if score > 0.0 else "directionally_opposed"
        ),
        "regime_decision_time_ms": _DECISION_MS,
        "regime_alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
    }
    if action is not None:
        value["action"] = action
    return value


def _bars(count: int) -> list[dict[str, object]]:
    return [
        {
            "timestamp_ms": _DECISION_MS + offset * 60_000,
            "open": 100.0 + offset,
            "high": 102.0 + offset,
            "low": 99.0 + offset,
            "close": 101.0 + offset,
            "volume": 10.0,
        }
        for offset in range(count)
    ]


def _row(
    sequence: int,
    event_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    observed_ms = _DECISION_MS - 120_000 + sequence * 1_000
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": _iso(observed_ms),
        "execution_mode": "live",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "run_id": "regime-conflict-a",
        "payload": payload,
    }


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1_000, timezone.utc).isoformat()
