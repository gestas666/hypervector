"""Operator exit behavior while a cohort transition drain is active."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.bidirectional_intents import RoutingAction
from hypervector.live.cohort_operator_commands import (
    CohortOperatorClaim,
    CohortOperatorCommand,
)
from hypervector.live.multi_asset_operator_runtime import LiveOperatorCommandProcessor
from hypervector.live.asset_state import AssetLiveSnapshot, AssetLiveState


class _Source:
    def __init__(self, claim: CohortOperatorClaim) -> None:
        self.claim = claim
        self.outcomes: list[tuple[str, str]] = []

    def claim_pending(self) -> tuple[CohortOperatorClaim, ...]:
        return (self.claim,)

    def finalize(
        self,
        claim: CohortOperatorClaim,
        *,
        status: str,
        reason: str,
    ) -> None:
        self.outcomes.append((status, reason))


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit_operator_command(self, payload: dict[str, object]) -> None:
        self.events.append(payload)


class _Engine:
    @property
    def snapshot(self) -> AssetLiveSnapshot:
        return AssetLiveSnapshot(
            state=AssetLiveState.OPEN,
            position_size_signed=0.01,
            stop_oid=9,
        )


def test_active_transition_drain_still_allows_manual_close() -> None:
    """Entry admission is drained, but an explicit protected exit remains usable."""
    command = CohortOperatorCommand(
        request_id="a" * 32,
        run_id="fixture-run",
        profile_fingerprint="b" * 64,
        created_at_utc="2026-08-05T13:00:00+00:00",
        action="manual_close",
        symbol="BTC",
        provider=None,
        side=None,
        settings=None,
    )
    claim = CohortOperatorClaim(command.request_id, Path("claimed.json"), command, None)
    source = _Source(claim)
    telemetry = _Telemetry()
    executed: list[RoutingAction] = []
    processor = LiveOperatorCommandProcessor(
        source=source,
        telemetry=telemetry,
        engines={"BTC": _Engine()},
        executable_provider_symbols=frozenset(),
        executable_provider_directions=frozenset(),
        maximum_positions=1,
        transition_drain_active=lambda: True,
    )

    actions, affected = processor.process(
        reference_prices={"BTC": 100.0},
        observed_ms=1_785_600_000_000,
        execute=executed.append,
    )

    assert actions == tuple(executed)
    assert actions[0].action == "close"
    assert actions[0].strategy_id == "operator_override:manual_close"
    assert affected == {"BTC"}
    assert source.outcomes == [("completed", "venue lifecycle reconciled")]
