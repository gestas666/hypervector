"""Causal contract for the staged SOL aligned-range live provider."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path

import pandas as pd

from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.live.sol_aligned_range_contract import (
    SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
)
from hypervector.live.sol_aligned_range_one_blocker_provider import (
    SolAlignedRangeOneBlockerCollector,
)

_BASE = pd.Timestamp("2026-08-05T03:00:00Z")
_BASE_MS = int(_BASE.timestamp() * 1_000)
_MINUTE_MS = 60_000
_SOURCE = "range_onset_bidirectional_v1"


def test_exact_blocker_emits_long_and_short_only_with_aligned_fresh_opi(
    tmp_path: Path,
) -> None:
    """The candidate preserves both sides and requires side-adjusted OPI > 0."""
    long = _collect(tmp_path / "long", minute=1, side="long", opi=0.20)
    short = _collect(tmp_path / "short", minute=1, side="short", opi=-0.20)

    assert [(row.strategy_id, row.side) for row in long.intents] == [
        (SOL_ALIGNED_RANGE_FIXED60_STRATEGY, "long")
    ]
    assert [(row.strategy_id, row.side) for row in short.intents] == [
        (SOL_ALIGNED_RANGE_FIXED60_STRATEGY, "short")
    ]
    assert long.evaluations[0].readiness.metrics["directional_opi"] == 0.20
    assert short.evaluations[0].readiness.metrics["directional_opi"] == 0.20


def test_opposed_missing_or_stale_pressure_withholds_entry(tmp_path: Path) -> None:
    """L2 alignment is an explicit causal condition, not display-only data."""
    opposed = _collect(tmp_path / "opposed", minute=1, side="long", opi=-0.20)
    missing = _collect(
        tmp_path / "missing",
        minute=1,
        side="long",
        opi=None,
    )
    stale = _collect(
        tmp_path / "stale",
        minute=1,
        side="long",
        opi=0.20,
        book_age_seconds=31,
    )

    assert opposed.intents == ()
    assert opposed.evaluations[0].reason == "order_pressure_opposed"
    assert missing.intents == ()
    assert missing.evaluations[0].reason == "order_pressure_unavailable"
    assert stale.intents == ()
    assert stale.evaluations[0].reason == "order_pressure_stale"


def test_nonexact_or_stale_signal_withholds_entry(tmp_path: Path) -> None:
    """The wrapper cannot broaden beyond the frozen one-blocker hypothesis."""
    root = tmp_path / "nonexact"
    root.mkdir()
    observed = _BASE + pd.Timedelta(minutes=1, seconds=5)
    _write_book(root / "sol.jsonl", observed, 0.20)
    nonexact = SolAlignedRangeOneBlockerCollector(
        source_collector=_source(
            (
                _evaluation(
                    1,
                    "long",
                    blockers=("awaiting_hourly_sma_cross", "another_blocker"),
                ),
            )
        ),
        cohort_ledger=root / "decisions.jsonl",
    )(
        _bars(),
        symbol="SOL",
        observed_at=observed,
        after_decision_time_ms=_BASE_MS,
    )
    stale = _collect(
        tmp_path / "stale-signal",
        minute=1,
        side="long",
        opi=0.20,
        observed_minute=2,
        observed_second=2,
    )

    assert nonexact.intents == ()
    assert nonexact.evaluations[0].reason == "canonical_exact_one_blocker_absent"
    assert stale.intents == ()
    assert stale.evaluations[0].reason == "candidate_decision_stale"


def test_routed_entry_enforces_seventy_five_minute_rearm(tmp_path: Path) -> None:
    """Only a recorded routed entry starts the candidate cadence clock."""
    root = tmp_path / "rearm"
    root.mkdir()
    ledger = root / "decisions.jsonl"
    collector = SolAlignedRangeOneBlockerCollector(
        source_collector=_source(
            (
                _evaluation(1, "long"),
                _evaluation(30, "short"),
                _evaluation(77, "short"),
            )
        ),
        cohort_ledger=ledger,
    )
    first_at = _BASE + pd.Timedelta(minutes=1, seconds=5)
    _write_book(root / "sol.jsonl", first_at, 0.20)
    first = collector(
        _bars(),
        symbol="SOL",
        observed_at=first_at,
        after_decision_time_ms=_BASE_MS,
    )
    _write_entry(ledger, first_at)
    blocked_at = _BASE + pd.Timedelta(minutes=30, seconds=5)
    _write_book(root / "sol.jsonl", blocked_at, -0.20)
    blocked = collector(
        _bars(),
        symbol="SOL",
        observed_at=blocked_at,
        after_decision_time_ms=_BASE_MS + _MINUTE_MS,
    )
    rearmed_at = _BASE + pd.Timedelta(minutes=77, seconds=5)
    _write_book(root / "sol.jsonl", rearmed_at, -0.20)
    rearmed = collector(
        _bars(),
        symbol="SOL",
        observed_at=rearmed_at,
        after_decision_time_ms=_BASE_MS + 30 * _MINUTE_MS,
    )

    assert [row.side for row in first.intents] == ["long"]
    assert blocked.intents == ()
    assert blocked.evaluations[0].reason == "fixed_horizon_rearm_active"
    assert [row.side for row in rearmed.intents] == ["short"]


def test_partial_trailing_ledger_append_cannot_hide_last_complete_book(
    tmp_path: Path,
) -> None:
    """A concurrent partial append is ignored while complete L2 remains usable."""
    root = tmp_path / "partial"
    root.mkdir()
    observed = _BASE + pd.Timedelta(minutes=1, seconds=5)
    path = root / "sol.jsonl"
    _write_book(path, observed, 0.20)
    with path.open("ab") as handle:
        handle.write(b'{"event_type":"book_observation"')

    result = SolAlignedRangeOneBlockerCollector(
        source_collector=_source((_evaluation(1, "long"),)),
        cohort_ledger=root / "decisions.jsonl",
    )(
        _bars(),
        symbol="SOL",
        observed_at=observed,
        after_decision_time_ms=_BASE_MS,
    )

    assert [row.side for row in result.intents] == ["long"]


def _collect(
    root: Path,
    *,
    minute: int,
    side: str,
    opi: float | None,
    book_age_seconds: int = 1,
    observed_minute: int | None = None,
    observed_second: int = 5,
) -> IntentBatch:
    root.mkdir(parents=True)
    cohort_ledger = root / "decisions.jsonl"
    observed = _BASE + pd.Timedelta(
        minutes=minute if observed_minute is None else observed_minute,
        seconds=observed_second,
    )
    if opi is not None:
        _write_book(root / "sol.jsonl", observed, opi, age_seconds=book_age_seconds)
    collector = SolAlignedRangeOneBlockerCollector(
        source_collector=_source((_evaluation(minute, side),)),
        cohort_ledger=cohort_ledger,
    )
    return collector(
        _bars(),
        symbol="SOL",
        observed_at=observed,
        after_decision_time_ms=_BASE_MS,
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
        assert symbol == "SOL"
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
        symbol="SOL",
        decision_time_ms=_BASE_MS + minute * _MINUTE_MS,
        reference_price=74.0,
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
        primary_regime="RANGE",
        state_1m="RANGE",
        state_5m="RANGE",
        context_15m="TREND_UP" if side == "long" else "TREND_DOWN",
        confidence=0.7,
    )


def _write_book(
    path: Path,
    observed: pd.Timestamp,
    opi: float,
    *,
    age_seconds: int = 1,
) -> None:
    recv_ts_ms = int((observed - pd.Timedelta(seconds=age_seconds)).timestamp() * 1_000)
    row = {
        "event_type": "book_observation",
        "observed_at_utc": observed.isoformat(),
        "payload": {
            "source": "hyperliquid_mainnet_l2_rest",
            "recv_ts_ms": recv_ts_ms,
            "exchange_ts_ms": recv_ts_ms - 100,
            "opi": opi,
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _write_entry(path: Path, observed_at: pd.Timestamp) -> None:
    row = {
        "event_type": "intent_routing",
        "observed_at_utc": observed_at.isoformat(),
        "payload": {
            "actions": [
                {
                    "action": "enter",
                    "strategy_id": SOL_ALIGNED_RANGE_FIXED60_STRATEGY,
                    "symbol": "SOL",
                }
            ]
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _bars() -> pd.DataFrame:
    return pd.DataFrame({"close": [74.0]}, index=[_BASE])
