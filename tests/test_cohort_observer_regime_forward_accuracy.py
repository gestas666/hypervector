"""Tests for route-specific observer regime forward accuracy."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_observer_regime_forward_accuracy import (
    build_observer_regime_forward_accuracy,
)

_RUN = "observer-a"
_STRATEGY = "range_onset_bidirectional_v1"


def _envelope(
    event_type: str, observed: str, payload: dict[str, object]
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "run_id": _RUN,
        "observed_at_utc": observed,
        "execution_mode": "observe",
        "effective_mode": "OBSERVE ONLY",
        "live_armed": False,
        "execution_authority": "none",
        "profile_id": "profile_a",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "payload": payload,
    }


def _identity() -> dict[str, object]:
    return _envelope(
        "configuration_identity",
        "1970-01-01T00:00:00+00:00",
        {
            "strategy_name": "multi_asset_bidirectional_cohort",
            "profile_fingerprint": "profile",
        },
    )


def _evaluation(
    timestamp_ms: int, price: float, state: str | None
) -> dict[str, object]:
    return {
        "strategy_id": _STRATEGY,
        "symbol": "SOL",
        "decision_time_ms": timestamp_ms,
        "reference_price": price,
        "eligible": False,
        "side": "long",
        "primary_regime": state,
        "state_1m": state,
        "state_5m": state,
        "context_15m": state,
        "readiness": {"side": "long", "blockers": ["waiting"], "metrics": {}},
    }


def _records(*, missing_states: bool = False) -> list[dict[str, object]]:
    states: list[str | None] = ["TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN"]
    if missing_states:
        states = [None] * 4
    rows = [_identity()]
    for timestamp_ms, price, state in zip(
        (60_000, 120_000, 180_000, 240_000),
        (100.0, 101.0, 99.0, 98.0),
        states,
        strict=True,
    ):
        rows.append(
            _envelope(
                "intent_routing",
                f"1970-01-01T00:{timestamp_ms // 60_000:02}:01+00:00",
                {"evaluations": [_evaluation(timestamp_ms, price, state)]},
            )
        )
    return rows


def _continued_records() -> list[dict[str, object]]:
    rows = _records()
    rows[0]["run_id"] = "observer-a-2"
    rows[0]["observed_at_utc"] = "1970-01-01T00:04:30+00:00"
    for minute, row in zip(range(5, 9), rows[1:], strict=True):
        row["run_id"] = "observer-a-2"
        row["observed_at_utc"] = f"1970-01-01T00:{minute:02}:01+00:00"
        payload = row["payload"]
        assert isinstance(payload, dict)
        evaluation = payload["evaluations"][0]
        evaluation["decision_time_ms"] = minute * 60_000
        evaluation["reference_price"] = 103.0 - minute
    return rows


def _canonical_records() -> list[dict[str, object]]:
    rows = _records(missing_states=True)
    for timestamp_ms, price, state in zip(
        (60_000, 120_000, 180_000, 240_000),
        (100.0, 101.0, 99.0, 98.0),
        ("TREND_UP", "TREND_UP", "TREND_DOWN", "TREND_DOWN"),
        strict=True,
    ):
        rows.append(
            _envelope(
                "canonical_regime_evaluations",
                f"1970-01-01T00:{timestamp_ms // 60_000:02}:02+00:00",
                {
                    "contract": {
                        "configured_route": False,
                        "execution_authority": "none",
                        "intents_emitted": False,
                    },
                    "evaluations": [
                        {
                            **_evaluation(timestamp_ms, price, state),
                            "strategy_id": "canonical_regime_telemetry_v1",
                            "symbol": "BTC",
                            "side": None,
                            "decision_action": "regime_observation",
                            "reason": "canonical_regime_observation",
                            "backend_non_action_reason": (
                                "telemetry_only_no_execution_authority"
                            ),
                        }
                    ],
                },
            )
        )
    return rows


def test_regime_accuracy_separates_repeated_rows_from_episode_onsets() -> None:
    report = build_observer_regime_forward_accuracy(
        _records(), run_id=_RUN, horizons_minutes=(1,)
    )
    route = report["horizons"]["1m"]["by_provider_symbol"][f"{_STRATEGY}|SOL"]
    primary = route["state_fields"]["primary_regime"]

    assert report["execution_authority"] == "none"
    assert route["coverage"] == {
        "candidate_observations": 4,
        "resolved_future_prices": 3,
        "unresolved_tail": 1,
        "missing_exact_future": 0,
        "complete_state_observations": 4,
    }
    assert primary["repeated"]["TREND_UP"]["observations"] == 2
    assert primary["repeated"]["TREND_UP"]["directional_accuracy_pct"] == 50.0
    assert primary["episode_onsets"]["TREND_DOWN"]["observations"] == 1
    assert primary["episode_onsets"]["TREND_DOWN"]["directional_accuracy_pct"] == 100.0


def test_regime_accuracy_extends_across_exact_compatible_restarts() -> None:
    """A report-only restart must not censor later regime outcomes."""
    report = build_observer_regime_forward_accuracy(
        [*_records(), *_continued_records()],
        run_id=_RUN,
        horizons_minutes=(1,),
    )
    route = report["horizons"]["1m"]["by_provider_symbol"][f"{_STRATEGY}|SOL"]

    assert report["source"]["compatible_run_ids"] == [_RUN, "observer-a-2"]
    assert route["coverage"]["candidate_observations"] == 8
    assert route["coverage"]["resolved_future_prices"] == 7


def test_missing_regime_telemetry_is_explicit_not_imputed() -> None:
    report = build_observer_regime_forward_accuracy(
        _records(missing_states=True), run_id=_RUN, horizons_minutes=(1,)
    )
    route = report["horizons"]["1m"]["by_provider_symbol"][f"{_STRATEGY}|SOL"]

    assert route["coverage"]["complete_state_observations"] == 0
    assert route["state_fields"]["primary_regime"] == {
        "repeated": {},
        "episode_onsets": {},
    }


def test_canonical_regime_accuracy_is_scored_by_symbol_without_route_authority() -> (
    None
):
    report = build_observer_regime_forward_accuracy(
        _canonical_records(), run_id=_RUN, horizons_minutes=(1,)
    )
    btc = report["canonical_horizons"]["1m"]["by_symbol"]["BTC"]

    assert btc["coverage"]["resolved_future_prices"] == 3
    primary = btc["state_fields"]["primary_regime"]
    assert primary["episode_onsets"]["TREND_DOWN"]["directional_accuracy_pct"] == 100.0
    assert report["canonical_source"] == {
        "strategy_id": "canonical_regime_telemetry_v1",
        "candidate_observations": 4,
        "symbols": 1,
        "configured_route": False,
        "execution_authority": "none",
    }


def test_regime_accuracy_rejects_live_authority() -> None:
    rows = _records()
    rows[0]["execution_mode"] = "live"
    rows[0]["effective_mode"] = "LIVE"
    rows[0]["live_armed"] = True
    rows[0]["execution_authority"] = "hyperliquid_mainnet"

    with pytest.raises(ValueError, match="report-only observe"):
        build_observer_regime_forward_accuracy(rows, run_id=_RUN, horizons_minutes=(1,))
