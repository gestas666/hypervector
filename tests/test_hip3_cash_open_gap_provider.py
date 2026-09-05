"""Exact SPCX cash-open provider behavior and target propagation."""

from __future__ import annotations

import pandas as pd

from hypervector.live.hip3_cash_open_gap_provider import (
    HIP3_SPCX_CASH_OPEN_STRATEGY,
    Hip3CashOpenGapCollector,
)
from hypervector.research.hip3_cash_open_gap_reversal_signals import (
    Hip3CashOpenGapReversalConfig,
)


class _Source:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls = 0

    def completed_bars(
        self, *, observed_at_ms: int, minimum_start_ms: int
    ) -> pd.DataFrame:
        del observed_at_ms, minimum_start_ms
        self.calls += 1
        return self.frame.copy()


def test_provider_emits_exact_short_and_prior_close_target() -> None:
    """A completed positive gap must fade short with an absolute target."""
    collector = Hip3CashOpenGapCollector(source=_Source(_opening_frame(30.0)))

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:05Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-17T13:30:00Z").timestamp() * 1_000
        ),
    )

    assert batch.latest_decision_time_ms == int(
        pd.Timestamp("2026-08-17T13:45:00Z").timestamp() * 1_000
    )
    assert len(batch.intents) == 1
    assert batch.intents[0].strategy_id == HIP3_SPCX_CASH_OPEN_STRATEGY
    assert batch.intents[0].side == "short"
    assert batch.intents[0].target_anchor == 100.0
    assert batch.evaluations[0].target_anchor == 100.0
    assert batch.evaluations[0].readiness.metrics["public_trade_count"] == 1
    assert "SOURCE WS TRADES 1" in batch.evaluations[0].readiness.indicators


def test_provider_bootstrap_and_subthreshold_gap_do_not_retro_enter() -> None:
    """Startup and a measured no-entry session must remain non-executable."""
    collector = Hip3CashOpenGapCollector(source=_Source(_opening_frame(5.0)))

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:05Z"),
        after_decision_time_ms=None,
    )

    assert batch.intents == ()
    assert batch.evaluations[-1].eligible is False
    assert (
        batch.evaluations[-1].backend_non_action_reason == "activation_readiness_seed"
    )
    assert batch.evaluations[-1].reason == "cash_open_gap_below_threshold"
    assert batch.evaluations[-1].readiness.blockers == ("gap_below_threshold",)


def test_provider_readiness_does_not_report_inapplicable_gap_failure() -> None:
    """An overnight row must identify timing, not claim a failed open reversal."""
    collector = Hip3CashOpenGapCollector(
        source=_Source(_opening_frame(5.0, end="2026-08-17T14:00:00Z"))
    )

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T14:00:05Z"),
        after_decision_time_ms=None,
    )
    evaluation = batch.evaluations[-1]

    assert evaluation.readiness.blockers == ("not_cash_open_decision",)


def test_provider_emits_authoritative_cash_close_exit() -> None:
    """The completed cash-close bar must request a symmetric recipe exit."""
    frame = _opening_frame(30.0, end="2026-08-17T20:00:00Z")
    collector = Hip3CashOpenGapCollector(source=_Source(frame))
    prior = int(pd.Timestamp("2026-08-17T19:45:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T20:00:05Z"),
        after_decision_time_ms=prior,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].exit_sides == frozenset({"long", "short"})
    assert batch.evaluations[0].exit_reason == "cash_session_close"


def test_provider_attributes_source_recovery_exit_separately() -> None:
    """A post-gap recovery exit must not be labeled as a cash close."""
    frame = _opening_frame(30.0, end="2026-08-17T14:00:00Z")
    frame.loc[pd.Timestamp("2026-08-17T13:45:00Z"), "gap_before_bars"] = 1
    collector = Hip3CashOpenGapCollector(source=_Source(frame))
    prior = int(pd.Timestamp("2026-08-17T13:45:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T14:00:05Z"),
        after_decision_time_ms=prior,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].reason == "source_recovery"
    assert batch.evaluations[0].exit_reason == "source_recovery"
    readiness = batch.evaluations[0].readiness
    assert readiness.blockers == ("cash_open_trade_gap",)
    assert readiness.metrics["gap_before_bars"] == 1
    assert "SOURCE GAPS 1" in readiness.indicators


def test_provider_withholds_a_gap_affected_opening_entry() -> None:
    """An unresolved opening bar cannot emit an otherwise eligible fade."""
    frame = _opening_frame(30.0)
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    frame.loc[opening, "gap_before_bars"] = 1
    collector = Hip3CashOpenGapCollector(source=_Source(frame))
    prior = int(pd.Timestamp("2026-08-17T13:30:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:05Z"),
        after_decision_time_ms=prior,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].eligible is False
    assert batch.evaluations[0].exit_reason == "source_recovery"
    assert batch.evaluations[0].readiness.blockers == ("cash_open_trade_gap",)


def test_provider_withholds_a_gap_affected_prior_close_target() -> None:
    """An unresolved prior close cannot become an executable target anchor."""
    frame = _opening_frame(30.0)
    prior_close = pd.Timestamp("2026-08-14T19:45:00Z")
    frame.loc[prior_close, "gap_before_bars"] = 1
    collector = Hip3CashOpenGapCollector(source=_Source(frame))
    prior = int(pd.Timestamp("2026-08-17T13:30:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:05Z"),
        after_decision_time_ms=prior,
    )

    assert batch.intents == ()
    assert batch.evaluations[0].eligible is False
    assert batch.evaluations[0].target_anchor is None
    assert batch.evaluations[0].readiness.blockers == ("prior_close_unavailable",)


def test_provider_does_not_rescan_an_already_completed_boundary() -> None:
    """The 15m source must be read once, not on every backend poll cycle."""
    source = _Source(_opening_frame(5.0))
    collector = Hip3CashOpenGapCollector(source=source)
    boundary = int(pd.Timestamp("2026-08-17T13:45:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:20Z"),
        after_decision_time_ms=boundary,
    )

    assert batch.intents == ()
    assert batch.latest_decision_time_ms == boundary
    assert batch.evaluations == ()
    assert source.calls == 0


def test_provider_does_not_advance_or_reread_source_overnight() -> None:
    """Wall-clock 15-minute ticks after cash close are not strategy decisions."""
    source = _Source(_opening_frame(5.0, end="2026-08-17T20:00:00Z"))
    collector = Hip3CashOpenGapCollector(source=source)
    cash_close_boundary = int(pd.Timestamp("2026-08-17T20:00:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T23:00:05Z"),
        after_decision_time_ms=cash_close_boundary,
    )

    assert batch == type(batch)((), cash_close_boundary, ())
    assert source.calls == 0


def test_provider_does_not_reread_source_between_completed_bars() -> None:
    """Backend polls within one completed bar retain the cash-session cursor."""
    source = _Source(_opening_frame(5.0))
    collector = Hip3CashOpenGapCollector(source=source)
    boundary = int(pd.Timestamp("2026-08-17T13:45:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:50:05Z"),
        after_decision_time_ms=boundary,
    )

    assert batch == type(batch)((), boundary, ())
    assert source.calls == 0


def test_provider_retains_cursor_when_latest_scheduled_bar_is_missing() -> None:
    """A sparse source cannot manufacture advancement at the wall boundary."""
    source = _Source(_opening_frame(5.0))
    collector = Hip3CashOpenGapCollector(source=source)
    boundary = int(pd.Timestamp("2026-08-17T13:45:00Z").timestamp() * 1_000)

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T14:00:05Z"),
        after_decision_time_ms=boundary,
    )

    assert batch == type(batch)((), boundary, ())
    assert source.calls == 1


def test_provider_readiness_uses_the_bound_gap_threshold() -> None:
    """Readiness telemetry must describe the collector's actual parameters."""
    collector = Hip3CashOpenGapCollector(
        source=_Source(_opening_frame(30.0)),
        config=Hip3CashOpenGapReversalConfig(gap_threshold_bps=50.0),
    )

    batch = collector(
        pd.DataFrame(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-17T13:45:05Z"),
        after_decision_time_ms=None,
    )

    readiness = batch.evaluations[0].readiness
    assert batch.evaluations[0].reason == "cash_open_gap_below_threshold"
    assert readiness.blockers == ("gap_below_threshold",)
    assert readiness.metrics["gap_threshold_bps"] == 50.0
    assert "THRESHOLD 50.00 BPS" in readiness.indicators


def _opening_frame(
    gap_bps: float, *, end: str = "2026-08-17T13:45:00Z"
) -> pd.DataFrame:
    index = pd.date_range("2026-08-14T00:00:00Z", end, freq="15min", inclusive="left")
    frame = pd.DataFrame(100.0, index=index, columns=["open", "high", "low", "close"])
    frame["gap_before_bars"] = 0
    frame["public_trade_count"] = 1
    opening = pd.Timestamp("2026-08-17T13:30:00Z")
    price = 100.0 * (1.0 + gap_bps / 10_000.0)
    frame.loc[opening, ["open", "high", "low", "close"]] = price
    return frame
