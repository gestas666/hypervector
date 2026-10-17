"""Conservative label construction from maker fill-assumption challengers."""

from __future__ import annotations


import pandas as pd

from hypervector.ml.feature_matrix import FEATURE_NAMES, build_feature_matrix
from hypervector.research.maker_replay_models import (
    FillRule,
    LifecycleStatus,
    MakerReplayLifecycle,
    MakerReplayReport,
)
from hypervector.research.replay_labels import (
    attach_runtime_features,
    build_conservative_replay_labels,
)


def _lifecycle(status: LifecycleStatus, outcome: str | None) -> MakerReplayLifecycle:
    return MakerReplayLifecycle(
        lifecycle_id=0,
        direction="long",
        signal_time_utc="2026-01-01T00:01:00+00:00",
        submitted_time_utc="2026-01-01T00:01:01+00:00",
        entry_time_utc=(
            "2026-01-01T00:01:02+00:00"
            if status in {"open", "target_completed"}
            else None
        ),
        outcome_time_utc=outcome,
        status=status,
        entry_price=100.0 if status in {"open", "target_completed"} else None,
        exit_price=100.2 if status == "target_completed" else None,
        quantity=28.0 if status in {"open", "target_completed"} else None,
        fees=0.0 if status == "target_completed" else None,
        net_pnl=5.6 if status == "target_completed" else None,
    )


def _report(rule: FillRule, lifecycle: MakerReplayLifecycle) -> MakerReplayReport:
    return MakerReplayReport(
        fill_rule=rule,
        snapshots=1,
        market_trade_prints=1 if rule == "trade-through" else 0,
        submitted_entries=1,
        entry_fills=int(lifecycle.entry_time_utc is not None),
        expired_entries=int(lifecycle.status == "expired"),
        canceled_entries=int(lifecycle.status == "canceled"),
        pending_orders=int(lifecycle.status == "pending"),
        completed_trades=int(lifecycle.status == "target_completed"),
        open_positions=int(lifecycle.status == "open"),
        initial_equity=100.0,
        final_equity=105.6 if lifecycle.status == "target_completed" else 100.0,
        submission_times_utc=(lifecycle.submitted_time_utc,),
        trades=(),
        lifecycles=(lifecycle,),
        limitations=(),
    )


def _reports(
    statuses: tuple[LifecycleStatus, LifecycleStatus, LifecycleStatus],
) -> dict[str, MakerReplayReport]:
    rules: tuple[FillRule, ...] = ("touch", "through", "trade-through")
    outcomes = (
        "2026-01-01T00:02:00+00:00",
        "2026-01-01T00:02:01+00:00",
        "2026-01-01T00:02:02+00:00",
    )
    return {
        rule: _report(rule, _lifecycle(status, outcome))
        for rule, status, outcome in zip(rules, statuses, outcomes, strict=True)
    }


def test_agreed_completed_target_becomes_positive_label() -> None:
    result = build_conservative_replay_labels(
        _reports(("target_completed", "target_completed", "target_completed"))
    )

    assert result.nominal_signals == 1
    assert result.resolved_signals == 1
    assert result.rows.iloc[0]["label"] == 1
    assert result.rows.iloc[0]["outcome_ts_ms"] == 1_767_225_722_000


def test_agreed_expiration_becomes_resolved_zero_label() -> None:
    result = build_conservative_replay_labels(
        _reports(("expired", "expired", "expired"))
    )

    assert result.resolved_signals == 1
    assert result.rows.iloc[0]["label"] == 0


def test_open_or_pending_lifecycle_remains_unresolved() -> None:
    result = build_conservative_replay_labels(_reports(("open", "open", "open")))

    assert result.rows.empty
    assert result.unresolved_signals == 1
    assert result.disagreement_signals == 0


def test_fill_assumption_outcome_disagreement_is_not_labeled() -> None:
    result = build_conservative_replay_labels(
        _reports(("target_completed", "expired", "expired"))
    )

    assert result.rows.empty
    assert result.unresolved_signals == 1
    assert result.disagreement_signals == 1


def test_runtime_features_use_last_completed_bar_at_signal_time() -> None:
    timestamps = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0, 101.0, 102.0, 500.0],
            "high": [101.0, 102.0, 103.0, 501.0],
            "low": [99.0, 100.0, 101.0, 499.0],
            "close": [100.0, 101.0, 102.0, 500.0],
            "volume": [1.0] * 4,
        }
    )
    signal_time = timestamps[2]
    labels = pd.DataFrame(
        {
            "signal_ts_ms": [int(signal_time.timestamp() * 1_000)],
            "outcome_ts_ms": [int(timestamps[3].timestamp() * 1_000)],
            "label": [1],
        }
    )

    attached = attach_runtime_features(labels, bars)
    expected = build_feature_matrix(bars.iloc[:2]).iloc[-1]

    assert attached.loc[0, FEATURE_NAMES].tolist() == expected[FEATURE_NAMES].tolist()
