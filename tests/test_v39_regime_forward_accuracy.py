"""Causal forward-score tests for exact v39 canonical regime telemetry."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from hypervector.research.v39_forward_evidence_contract import (
    PROFILE_FINGERPRINT,
    PROFILE_ID,
)
from hypervector.research.v39_regime_forward_accuracy import (
    build_v39_regime_forward_accuracy,
)

_RUN_ID = "v39-run"
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")
_START = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def test_excludes_unresolved_tail_and_reports_state_episode_metrics() -> None:
    """An unavailable future price cannot become a synthetic zero return."""
    rows = [_identity(), *_events((100.0, 101.0, 99.0, 100.0))]

    report = build_v39_regime_forward_accuracy(
        rows,
        run_id=_RUN_ID,
        horizons_minutes=(1,),
        range_thresholds_bps=(25.0,),
    )

    horizon = report["horizons"]["1m"]
    assert horizon["coverage"] == {
        "candidate_observations": 16,
        "resolved_observations": 12,
        "unresolved_tail_observations": 4,
        "missing_exact_future_observations": 0,
    }
    pooled = horizon["state_fields"]["state_1m"]["pooled"]
    assert pooled["TREND_UP"]["observations"] == 8
    assert pooled["TREND_UP"]["directional_accuracy_pct"] == pytest.approx(50.0)
    assert pooled["RANGE"]["observations"] == 4
    assert pooled["RANGE"]["quiet_rate_by_threshold_pct"] == {"25bps": 0.0}
    episodes = horizon["state_fields"]["state_1m"]["episode_onsets"]
    assert "TREND_UP" not in episodes
    assert episodes["RANGE"]["observations"] == 4
    episodes_by_symbol = horizon["state_fields"]["state_1m"]["episode_onsets_by_symbol"]
    assert episodes_by_symbol["BTC"]["RANGE"]["observations"] == 1
    assert episodes_by_symbol["ETH"]["RANGE"]["observations"] == 1
    clusters = horizon["state_fields"]["state_1m"]["episode_onset_clusters"]
    assert clusters["RANGE"]["observations"] == 1
    assert clusters["RANGE"]["asset_observations"] == 4
    assert report["schema_version"] == "v39_canonical_regime_forward_accuracy_v4"
    assert report["source"]["left_censored_initial_state_series"] == 16
    assert (
        report["interpretation"]["episode_onsets"]
        == "observed_state_change_after_prior_in_run"
    )
    assert any(
        "initial state per symbol and field is left-censored" in limitation
        for limitation in report["limitations"]
    )


def test_requires_an_exact_future_decision_timestamp() -> None:
    """A later quote cannot silently substitute for a missing horizon boundary."""
    rows = [_identity(), *_events((100.0, 99.0, 100.0), minutes=(0, 2, 3))]

    report = build_v39_regime_forward_accuracy(
        rows,
        run_id=_RUN_ID,
        horizons_minutes=(1,),
    )

    assert report["horizons"]["1m"]["coverage"] == {
        "candidate_observations": 12,
        "resolved_observations": 4,
        "unresolved_tail_observations": 4,
        "missing_exact_future_observations": 4,
    }


def test_rejects_conflicting_duplicate_symbol_decision() -> None:
    """Two different prices for one symbol/decision boundary are invalid."""
    rows = [_identity(), *_events((100.0, 101.0))]
    conflict = deepcopy(rows[1])
    conflict["payload"]["evaluations"][0]["reference_price"] = 999.0
    rows.append(conflict)

    with pytest.raises(ValueError, match="conflicting canonical regime duplicate"):
        build_v39_regime_forward_accuracy(rows, run_id=_RUN_ID)


def test_rejects_wrong_profile_or_future_decision_evidence() -> None:
    """The report binds exact v39 identity and receipt-causal observations."""
    wrong = [_identity(profile_id="wrong"), *_events((100.0, 101.0))]
    with pytest.raises(ValueError, match="exact v39 runtime identity"):
        build_v39_regime_forward_accuracy(wrong, run_id=_RUN_ID)

    future = [_identity(), *_events((100.0, 101.0))]
    future[1]["observed_at_utc"] = (_START - timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError, match="future canonical regime evidence"):
        build_v39_regime_forward_accuracy(future, run_id=_RUN_ID)


def _identity(*, profile_id: str = PROFILE_ID) -> dict[str, object]:
    return {
        "run_id": _RUN_ID,
        "event_type": "configuration_identity",
        "live_armed": True,
        "execution_mode": "live",
        "profile_id": profile_id,
        "profile_fingerprint": PROFILE_FINGERPRINT,
        "payload": {
            "profile_fingerprint": PROFILE_FINGERPRINT,
        },
    }


def _events(
    prices: tuple[float, ...],
    *,
    minutes: tuple[int, ...] | None = None,
) -> list[dict[str, object]]:
    offsets = minutes or tuple(range(len(prices)))
    return [
        _event(offset, price) for offset, price in zip(offsets, prices, strict=True)
    ]


def _event(minute: int, price: float) -> dict[str, object]:
    decision = _START + timedelta(minutes=minute)
    state = "TREND_UP" if minute < 2 else "RANGE"
    return {
        "run_id": _RUN_ID,
        "event_type": "canonical_regime_evaluations",
        "observed_at_utc": (decision + timedelta(seconds=2)).isoformat(),
        "payload": {
            "contract": {
                "configured_route": False,
                "execution_authority": "none",
                "intents_emitted": False,
            },
            "evaluations": [
                {
                    "symbol": symbol,
                    "strategy_id": "canonical_regime_telemetry_v1",
                    "decision_action": "regime_observation",
                    "backend_non_action_reason": "telemetry_only_no_execution_authority",
                    "decision_time_ms": int(decision.timestamp() * 1_000),
                    "reference_price": price,
                    "primary_regime": state,
                    "state_1m": state,
                    "state_5m": state,
                    "context_15m": state,
                }
                for symbol in _SYMBOLS
            ],
        },
    }
