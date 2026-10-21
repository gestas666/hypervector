"""Production-path readiness seeding for completed-bar providers."""

from __future__ import annotations

import pandas as pd

from hypervector.live.multi_asset_readiness_seed import collect_readiness_seed
from hypervector.live.provider_evaluation import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness

# A registered synthetic 1m provider (tests/synthetic_live_providers.py).
_STRATEGY = "test_long_target_1m"


def test_readiness_seed_preserves_a_missed_exit_over_a_later_hold() -> None:
    """Restart recovery must not discard a one-shot exit before the latest row."""
    observed = pd.Timestamp("2026-08-24T12:00:05Z")
    activation_ms = int(observed.timestamp() * 1_000)
    exit_row = _evaluation(activation_ms - 60_000, exit_long=True)
    hold_row = _evaluation(activation_ms - 30_000, exit_long=False)

    def collector(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del symbol, observed_at, after_decision_time_ms
        return IntentBatch((), hold_row.decision_time_ms, (exit_row, hold_row))

    seed = collect_readiness_seed(
        collector,
        pd.DataFrame(),
        _STRATEGY,
        "ETH",
        observed,
        activation_ms,
        100.0,
    )

    assert seed is not None
    assert seed.decision_time_ms == exit_row.decision_time_ms
    assert seed.exit_sides == frozenset({"long"})
    assert seed.exit_reason == "opposite_signal"
    assert seed.readiness.metrics["pre_activation_scan_start_ms"] == (
        exit_row.decision_time_ms
    )
    assert seed.readiness.metrics["pre_activation_scan_end_ms"] == (
        hold_row.decision_time_ms
    )


def test_readiness_seed_excludes_rows_after_a_delayed_startup() -> None:
    """Startup latency must not turn fresh decisions into historical seed rows."""
    activation = pd.Timestamp("2026-08-24T12:00:05Z")
    observed = activation + pd.Timedelta(minutes=8)
    activation_ms = int(activation.timestamp() * 1_000)
    before = _evaluation(activation_ms - 60_000, exit_long=False)
    after = _evaluation(activation_ms + 7 * 60_000, exit_long=False)

    def collector(
        _bars: pd.DataFrame,
        *,
        symbol: str,
        observed_at: pd.Timestamp,
        after_decision_time_ms: int | None,
    ) -> IntentBatch:
        del symbol
        lower = -1 if after_decision_time_ms is None else after_decision_time_ms
        upper = int(observed_at.timestamp() * 1_000)
        rows = tuple(
            row for row in (before, after) if lower < row.decision_time_ms <= upper
        )
        latest = rows[-1].decision_time_ms if rows else lower
        return IntentBatch((), latest, rows)

    seed = collect_readiness_seed(
        collector,
        pd.DataFrame(),
        _STRATEGY,
        "ETH",
        observed,
        activation_ms,
        100.0,
    )

    assert seed is not None
    assert seed.decision_time_ms == before.decision_time_ms
    assert seed.readiness.metrics["pre_activation_scan_end_ms"] == (
        before.decision_time_ms
    )


def _evaluation(decision_time_ms: int, *, exit_long: bool) -> ProviderEvaluation:
    exit_sides = frozenset({"long"}) if exit_long else frozenset()
    return ProviderEvaluation(
        strategy_id=_STRATEGY,
        symbol="ETH",
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="close_long" if exit_long else "hold",
        eligible=False,
        reason="opposite_signal" if exit_long else "signal_absent",
        side="short" if exit_long else None,
        readiness=SignalReadiness(
            None,
            0,
            1,
            ("signal_absent",),
            ("SIGNAL NO",),
        ),
        exit_sides=exit_sides,
        exit_reason="opposite_signal" if exit_long else None,
    )
