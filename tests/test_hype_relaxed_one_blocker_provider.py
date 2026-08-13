"""Causal contract tests for the staged HYPE one-blocker candidate."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hype_relaxed_one_blocker_provider import (
    HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
    HypeRelaxedOneBlockerCollector,
    HypeRelaxedOneBlockerStateError,
)
from hypervector.live.sol_range_onset_controller import SolLiveDecision

_BASE = pd.Timestamp("2026-08-04T16:00:00Z")
_BASE_MS = int(_BASE.timestamp() * 1_000)
_MINUTE_MS = 60_000
_TARGET20_STRATEGY = "hype_breakout_relaxed_target20_60m_bidirectional_v3"
_MATCHED_FIXED60_STRATEGY = "hype_breakout_relaxed_fixed60_matched_bidirectional_v4"


def _decision(minute: int, state: str, side: str) -> SolLiveDecision:
    return SolLiveDecision(
        decision_time_ms=_BASE_MS + minute * _MINUTE_MS,
        reference_price=50.0 + minute / 10.0,
        long_entry=False,
        short_entry=False,
        long_exit=False,
        short_exit=False,
        primary_regime=state,
        state_1m="TREND_UP" if side == "long" else "TREND_DOWN",
        state_5m=state,
        context_15m="RANGE",
        confidence=0.65,
        structural_direction=side,
        regime_admitted=state == "BREAKOUT",
    )


def _builder(
    decisions: tuple[SolLiveDecision, ...],
) -> Callable[..., tuple[SolLiveDecision, ...]]:
    def build(
        raw_bars: pd.DataFrame,
        *,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> tuple[SolLiveDecision, ...]:
        del raw_bars
        boundary = after_decision_time_ms or 0
        observed_ms = int(observed_at.timestamp() * 1_000)
        return tuple(
            row for row in decisions if boundary < row.decision_time_ms <= observed_ms
        )

    return build


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [_BASE],
            "open": [50.0],
            "high": [51.0],
            "low": [49.0],
            "close": [50.5],
            "volume": [10.0],
        }
    )


def _collector(
    decisions: tuple[SolLiveDecision, ...],
    ledger: Path | None = None,
) -> HypeRelaxedOneBlockerCollector:
    return HypeRelaxedOneBlockerCollector(
        decision_builder=_builder(decisions),
        cohort_ledger=ledger,
    )


def test_exact_blocker_requires_seventy_five_minutes_between_accepted_entries(
    tmp_path: Path,
) -> None:
    """A completed 60m hold receives a 15m same-family re-entry buffer."""
    ledger = tmp_path / "decisions.jsonl"
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(30, "RANGE", "short"),
            _decision(62, "RANGE", "short"),
            _decision(77, "RANGE", "short"),
        ),
        ledger,
    )

    first = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=10),
        after_decision_time_ms=_BASE_MS,
    )
    _write_entry_action(ledger, _BASE + pd.Timedelta(minutes=1, seconds=10))
    blocked = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=30, seconds=10),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )
    still_blocked = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=62, seconds=11),
        after_decision_time_ms=_BASE_MS + 30 * _MINUTE_MS,
    )
    rearmed = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=77, seconds=11),
        after_decision_time_ms=_BASE_MS + 62 * _MINUTE_MS,
    )

    assert [(row.side, row.decision_time_ms) for row in first.intents] == [
        ("long", _BASE_MS + _MINUTE_MS)
    ]
    assert blocked.intents == ()
    assert blocked.evaluations[0].reason == "fixed_horizon_rearm_active"
    assert blocked.evaluations[0].readiness.blockers == ("fixed_horizon_rearm_active",)
    assert still_blocked.intents == ()
    assert still_blocked.evaluations[0].reason == "fixed_horizon_rearm_active"
    assert [(row.side, row.decision_time_ms) for row in rearmed.intents] == [
        ("short", _BASE_MS + 77 * _MINUTE_MS)
    ]
    metrics = rearmed.evaluations[0].readiness.metrics
    assert metrics["fixed_horizon_seconds"] == 3_600.0
    assert metrics["minimum_entry_spacing_seconds"] == 4_500.0
    assert all(
        row.strategy_id == HYPE_RELAXED_ONE_BLOCKER_STRATEGY
        for batch in (first, blocked, rearmed)
        for row in batch.evaluations
    )


def test_restart_recovers_rearm_clock_from_append_only_ledger(tmp_path: Path) -> None:
    """A backend restart cannot convert the candidate into minute-by-minute entry."""
    ledger = tmp_path / "decisions.jsonl"
    _write_entry_action(ledger, _BASE + pd.Timedelta(minutes=1, seconds=10))
    collector = _collector(
        (
            _decision(30, "RANGE", "short"),
            _decision(62, "RANGE", "short"),
            _decision(77, "RANGE", "short"),
        ),
        ledger,
    )

    blocked = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=30, seconds=10),
        after_decision_time_ms=_BASE_MS,
    )
    still_blocked = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=62, seconds=11),
        after_decision_time_ms=_BASE_MS + 30 * _MINUTE_MS,
    )
    rearmed = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=77, seconds=11),
        after_decision_time_ms=_BASE_MS + 62 * _MINUTE_MS,
    )

    assert blocked.intents == ()
    assert still_blocked.intents == ()
    assert [row.side for row in rearmed.intents] == ["short"]


def test_startup_readiness_seed_does_not_consume_rearm() -> None:
    """The poller's retroactive display seed remains non-executable and stateless."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "RANGE", "long"),
            _decision(3, "RANGE", "long"),
        )
    )
    activation = _BASE_MS + 2 * _MINUTE_MS
    collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=2),
        after_decision_time_ms=activation,
    )
    seed = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=2),
        after_decision_time_ms=_BASE_MS,
    )
    live = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=3, seconds=5),
        after_decision_time_ms=activation,
    )

    assert seed.intents == ()
    assert seed.evaluations[-1].eligible is True
    assert [row.decision_time_ms for row in live.intents] == [_BASE_MS + 3 * _MINUTE_MS]


def test_canonical_breakout_is_not_duplicated_by_relaxed_candidate() -> None:
    """The challenger handles only the exact canonical 5m blocker near-miss."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "BREAKOUT", "long"),
        )
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=2, seconds=5),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].reason == "canonical_exact_one_blocker_absent"


def test_unrouted_candidate_reoffers_on_the_next_fresh_bar() -> None:
    """Only accepted entry actions consume cadence; a conflict is not a trade."""
    collector = _collector(
        (
            _decision(1, "RANGE", "long"),
            _decision(2, "RANGE", "long"),
        )
    )

    first = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )
    second = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=2, seconds=5),
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )

    assert len(first.intents) == 1
    assert len(second.intents) == 1


def test_target20_collector_emits_an_independent_strategy_identity() -> None:
    """The target-first experiment must not masquerade as fixed-horizon V2."""
    collector = HypeRelaxedOneBlockerCollector(
        decision_builder=_builder((_decision(1, "RANGE", "long"),)),
        strategy_id=_TARGET20_STRATEGY,
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )

    assert [row.strategy_id for row in batch.intents] == [_TARGET20_STRATEGY]
    assert [row.strategy_id for row in batch.evaluations] == [_TARGET20_STRATEGY]


def test_matched_fixed60_collector_has_its_frozen_v4_identity() -> None:
    """Matched-exit evidence must not reuse the earlier V2 cadence journal."""
    collector = HypeRelaxedOneBlockerCollector(
        decision_builder=_builder((_decision(1, "RANGE", "long"),)),
        strategy_id=_MATCHED_FIXED60_STRATEGY,
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )

    assert [row.strategy_id for row in batch.intents] == [_MATCHED_FIXED60_STRATEGY]
    assert batch.evaluations[0].readiness.metrics["exit_policy"] == "fixed_60m"
    assert batch.evaluations[0].readiness.metrics["target_bps"] is None


def test_target20_rearm_ignores_fixed_horizon_v2_entry_history(tmp_path: Path) -> None:
    """Independent experiment identities must retain independent cadence clocks."""
    ledger = tmp_path / "decisions.jsonl"
    _write_entry_action(ledger, _BASE + pd.Timedelta(seconds=10))
    collector = HypeRelaxedOneBlockerCollector(
        decision_builder=_builder((_decision(1, "RANGE", "long"),)),
        cohort_ledger=ledger,
        strategy_id=_TARGET20_STRATEGY,
    )

    batch = collector(
        _bars(),
        symbol="HYPE",
        observed_at=_BASE + pd.Timedelta(minutes=1, seconds=5),
        after_decision_time_ms=_BASE_MS,
    )

    assert [row.strategy_id for row in batch.intents] == [_TARGET20_STRATEGY]


def test_malformed_recovery_ledger_fails_closed(tmp_path: Path) -> None:
    """Restart state corruption is an actionable technical failure, not a reset."""
    ledger = tmp_path / "decisions.jsonl"
    ledger.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(HypeRelaxedOneBlockerStateError, match="invalid JSON"):
        _collector((_decision(1, "RANGE", "long"),), ledger)


def _write_entry_action(
    path: Path,
    observed_at: pd.Timestamp,
    strategy_id: str = HYPE_RELAXED_ONE_BLOCKER_STRATEGY,
) -> None:
    record = {
        "event_type": "intent_routing",
        "observed_at_utc": observed_at.isoformat(),
        "payload": {
            "actions": [
                {
                    "action": "enter",
                    "strategy_id": strategy_id,
                    "symbol": "HYPE",
                    "side": "long",
                    "decision_time_ms": _BASE_MS + _MINUTE_MS,
                }
            ]
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
