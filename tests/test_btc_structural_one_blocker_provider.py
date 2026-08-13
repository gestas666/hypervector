"""Causal contract for the staged BTC structural one-blocker provider."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pandas as pd

from hypervector.live.btc_structural_contract import BTC_STRUCTURAL_FIXED60_STRATEGY
from hypervector.live.btc_structural_one_blocker_provider import (
    BtcStructuralOneBlockerCollector,
)
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

_BASE = pd.Timestamp("2026-08-04T20:00:00Z")
_BASE_MS = int(_BASE.timestamp() * 1_000)
_MINUTE_MS = 60_000
_SOURCE = "range_onset_bidirectional_v1"


def test_exact_structural_blocker_emits_both_directions() -> None:
    """The candidate preserves the canonical source's causal long/short side."""
    long = _collector((_evaluation(1, "long"),))(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )
    short = _collector((_evaluation(2, "short"),))(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=2, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )

    assert [(row.strategy_id, row.side) for row in long.intents] == [
        (BTC_STRUCTURAL_FIXED60_STRATEGY, "long")
    ]
    assert [(row.strategy_id, row.side) for row in short.intents] == [
        (BTC_STRUCTURAL_FIXED60_STRATEGY, "short")
    ]
    assert long.evaluations[0].readiness.metrics["opi_execution_gate"] is False
    assert long.evaluations[0].readiness.metrics["fixed_horizon_seconds"] == 3_600.0


def test_nonexact_or_stale_source_never_emits() -> None:
    """The wrapper cannot broaden beyond its frozen one-blocker hypothesis."""
    nonexact = _collector(
        (_evaluation(1, "long", blockers=("awaiting_hourly_sma_cross", "other")),)
    )(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )
    stale = _collector((_evaluation(1, "long"),))(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=2, seconds=2),
        after_decision_time_ms=_BASE_MS,
    )

    assert nonexact.intents == ()
    assert nonexact.evaluations[0].reason == "canonical_exact_one_blocker_absent"
    assert stale.intents == ()
    assert stale.evaluations[0].reason == "candidate_decision_stale"


def test_accepted_entry_enforces_seventy_five_minute_rearm(tmp_path: Path) -> None:
    """Only a routed entry starts the fixed-hold plus buffer cadence clock."""
    ledger = tmp_path / "decisions.jsonl"
    collector = _collector(
        (
            _evaluation(1, "long"),
            _evaluation(30, "short"),
            _evaluation(77, "short"),
        ),
        ledger,
    )
    first = collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )
    _write_entry(ledger, _BASE + pd.Timedelta(minutes=1, seconds=5))
    blocked = collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=30, seconds=5),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )
    rearmed = collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=77, seconds=5),
        after_decision_time_ms=_BASE_MS + 30 * _MINUTE_MS,
    )

    assert [row.side for row in first.intents] == ["long"]
    assert blocked.intents == ()
    assert blocked.evaluations[0].reason == "fixed_horizon_rearm_active"
    assert [row.side for row in rearmed.intents] == ["short"]


def test_startup_seed_is_visible_but_nonexecuting() -> None:
    """Retroactive readiness hydration cannot become a live candidate order."""
    collector = _collector(
        (
            _evaluation(1, "long"),
            _evaluation(2, "long"),
            _evaluation(3, "short"),
        )
    )
    activation = _BASE_MS + 2 * _MINUTE_MS
    collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=2),
        after_decision_time_ms=activation,
    )
    seed = collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=2),
        after_decision_time_ms=_BASE_MS,
    )
    live = collector(
        _bars(),
        symbol="BTC",
        observed_at=_BASE + pd.Timedelta(minutes=3, seconds=5),
        after_decision_time_ms=activation,
    )

    assert seed.intents == ()
    assert seed.evaluations[-1].eligible is True
    assert [row.side for row in live.intents] == ["short"]


def _collector(
    evaluations: tuple[ProviderEvaluation, ...],
    ledger: Path | None = None,
) -> BtcStructuralOneBlockerCollector:
    return BtcStructuralOneBlockerCollector(
        source_collector=_source(evaluations),
        cohort_ledger=ledger,
    )


def _source(
    evaluations: tuple[ProviderEvaluation, ...],
) -> Callable[..., IntentBatch]:
    def collect(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        assert symbol == "BTC"
        boundary = after_decision_time_ms or 0
        observed_ms = int(observed_at.timestamp() * 1_000)
        rows = tuple(
            row for row in evaluations if boundary < row.decision_time_ms <= observed_ms
        )
        latest = rows[-1].decision_time_ms if rows else boundary
        return IntentBatch((), latest, rows)

    return collect


def _evaluation(
    minute: int,
    side: str,
    *,
    blockers: tuple[str, ...] = ("awaiting_hourly_sma_cross",),
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=_SOURCE,
        symbol="BTC",
        decision_time_ms=_BASE_MS + minute * _MINUTE_MS,
        reference_price=64_000.0,
        decision_action="hold",
        eligible=False,
        reason="entry_condition_absent",
        side=None,
        readiness=SignalReadiness(
            side=side,
            conditions_met=2,
            conditions_required=3,
            blockers=blockers,
            indicators=("STRUCT " + side.upper(),),
            metrics={"structural_direction": side},
        ),
        primary_regime="TREND_UP" if side == "long" else "TREND_DOWN",
        state_1m="RANGE",
        state_5m="BREAKOUT",
        context_15m="TREND_UP" if side == "long" else "TREND_DOWN",
        confidence=0.7,
    )


def _bars() -> pd.DataFrame:
    return pd.DataFrame({"close": [64_000.0]}, index=[_BASE])


def _write_entry(path: Path, observed_at: pd.Timestamp) -> None:
    row = {
        "event_type": "intent_routing",
        "observed_at_utc": observed_at.isoformat(),
        "payload": {
            "actions": [
                {
                    "action": "enter",
                    "strategy_id": BTC_STRUCTURAL_FIXED60_STRATEGY,
                    "symbol": "BTC",
                }
            ]
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
