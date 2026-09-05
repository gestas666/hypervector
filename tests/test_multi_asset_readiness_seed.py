"""Production-path readiness seeding for schedule-aware providers."""

from __future__ import annotations

import pandas as pd

from hypervector.live.directional_range_onset_provider import (
    ETH_RANGE_LONG_STRATEGY,
)
from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
    Hip3CashOpenGapCollector,
)
from hypervector.live.multi_asset_readiness_seed import collect_readiness_seed
from hypervector.live.multi_asset_signal_source import IntentBatch, ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    cash_session_bar_opens,
    spcx_cash_open_live_config,
)


class _CashBarSource:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame
        self.calls = 0

    def completed_bars(
        self, *, observed_at_ms: int, minimum_start_ms: int
    ) -> pd.DataFrame:
        del observed_at_ms, minimum_start_ms
        self.calls += 1
        return self._frame.copy()


def _prior_cash_sessions() -> pd.DataFrame:
    config = spcx_cash_open_live_config()
    start = pd.Timestamp("2026-08-20T13:30:00Z")
    end = pd.Timestamp("2026-08-21T20:00:00Z")
    index = cash_session_bar_opens(
        int(start.timestamp() * 1_000),
        int(end.timestamp() * 1_000),
        config,
    )
    frame = pd.DataFrame(100.0, index=index, columns=["open", "high", "low", "close"])
    frame["gap_before_bars"] = 0
    frame["public_trade_count"] = 1
    return frame


def test_spcx_readiness_seed_reaches_prior_session_across_weekend() -> None:
    """A Monday pre-open startup must seed from Friday without retro-routing."""
    source = _CashBarSource(_prior_cash_sessions())
    collector = Hip3CashOpenGapCollector(source=source)
    observed = pd.Timestamp("2026-08-24T12:00:05Z")
    activation_ms = int(observed.timestamp() * 1_000)

    seed = collect_readiness_seed(
        collector,
        pd.DataFrame(),
        HIP3_SPCX_CASH_OPEN_STRATEGY,
        "xyz:SPCX",
        observed,
        activation_ms,
        100.0,
    )

    assert seed is not None
    assert seed.decision_time_ms == int(
        pd.Timestamp("2026-08-21T20:00:00Z").timestamp() * 1_000
    )
    assert seed.backend_non_action_reason == "pre_activation_readiness_seed"
    assert seed.reason == "cash_session_close"
    assert source.calls == 1


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
        ETH_RANGE_LONG_STRATEGY,
        "ETH",
        observed,
        activation_ms,
        100.0,
    )

    assert seed is not None
    assert seed.decision_time_ms == exit_row.decision_time_ms
    assert seed.exit_sides == frozenset({"long"})
    assert seed.exit_reason == "opposite_range_onset"
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
        ETH_RANGE_LONG_STRATEGY,
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
        strategy_id=ETH_RANGE_LONG_STRATEGY,
        symbol="ETH",
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="close_long" if exit_long else "hold",
        eligible=False,
        reason="opposite_range_onset" if exit_long else "range_onset_absent",
        side="short" if exit_long else None,
        readiness=SignalReadiness(
            None,
            0,
            1,
            ("range_onset_absent",),
            ("RANGE ONSET NO",),
        ),
        exit_sides=exit_sides,
        exit_reason="opposite_range_onset" if exit_long else None,
    )
