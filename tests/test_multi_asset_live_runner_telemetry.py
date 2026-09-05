"""Display-only setup telemetry for the multi-asset live runner."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from hypervector.live.multi_asset_intent_poller import CohortIntentPoll
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from test_multi_asset_live_runner import _runner

_DECISION_MS = 1_785_585_600_000


def test_live_runner_publishes_display_rows_without_changing_runtime_rows(
    tmp_path: Path,
) -> None:
    """Screen 2 receives current setup data while routing retains recovery data."""
    recovery = _evaluation("recovery_exit")
    display = replace(
        recovery,
        decision_time_ms=_DECISION_MS + 1,
        decision_action="hold",
        reason="current_setup",
        exit_sides=frozenset(),
        exit_reason=None,
    )
    runner, _engines, telemetry = _runner(
        tmp_path,
        (),
        evaluations=(recovery,),
    )
    poller = runner._intent_poller
    original_poll = poller.poll

    def poll_with_display(observed_at: datetime) -> CohortIntentPoll:
        result = original_poll(observed_at)
        return replace(result, display_evaluations=(display,))

    poller.poll = poll_with_display

    runner.run(max_polls=1)

    assert telemetry.routings[0][2] == (display,)


def _evaluation(reason: str) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id="hulk",
        symbol="BTC",
        decision_time_ms=_DECISION_MS,
        reference_price=100.0,
        decision_action="close_long",
        eligible=False,
        reason=reason,
        side=None,
        readiness=SignalReadiness(None, 1, 2, ("waiting",), ("CURRENT 1/2",)),
        exit_sides=frozenset({"long"}),
        exit_reason=reason,
    )
