"""Direction authority and operator construction for the live cohort."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.cohort_transition_drain import CohortTransitionDrain
from hypervector.live.multi_asset_live_runner_support import MultiAssetLiveRunnerError
from hypervector.live.multi_asset_operator_runtime import (
    LiveOperatorCommandProcessor,
    OperatorCommandSourceProtocol,
    OperatorEngineProtocol,
    OperatorTelemetryProtocol,
)


def effective_execution_directions(
    pairs: frozenset[tuple[str, str]],
    configured: frozenset[tuple[str, str, str]] | None,
) -> frozenset[tuple[str, str, str]]:
    """Return validated explicit or legacy bidirectional authority."""
    directions = configured if configured is not None else _both_directions(pairs)
    _validate_execution_directions(directions, pairs)
    return directions


def hold_milliseconds(values: Mapping[str, int]) -> dict[str, int]:
    """Convert validated per-symbol hold seconds to milliseconds."""
    return {symbol: seconds * 1_000 for symbol, seconds in values.items()}


def create_operator_processor(
    source: OperatorCommandSourceProtocol | None,
    telemetry: OperatorTelemetryProtocol,
    engines: Mapping[str, OperatorEngineProtocol],
    executable_pairs: frozenset[tuple[str, str]],
    executable_directions: frozenset[tuple[str, str, str]],
    maximum_positions: int,
    transition_drain: CohortTransitionDrain | None,
) -> LiveOperatorCommandProcessor | None:
    """Construct manual-override handling when an inbox is configured."""
    if source is None:
        return None
    return LiveOperatorCommandProcessor(
        source=source,
        telemetry=telemetry,
        engines=engines,
        executable_provider_symbols=executable_pairs,
        executable_provider_directions=executable_directions,
        maximum_positions=maximum_positions,
        activate_transition_drain=(
            None
            if transition_drain is None
            else lambda request_id, requested_at: _activate_transition_drain(
                transition_drain,
                request_id,
                requested_at,
            )
        ),
        transition_drain_active=(
            None if transition_drain is None else lambda: transition_drain.active
        ),
    )


def _activate_transition_drain(
    control: CohortTransitionDrain,
    request_id: str,
    requested_at_utc: str,
) -> str:
    control.activate(
        request_id=request_id,
        requested_at_utc=requested_at_utc,
    )
    return "transition drain activated"


def _both_directions(
    pairs: frozenset[tuple[str, str]],
) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (provider, symbol, side)
        for provider, symbol in pairs
        for side in ("long", "short")
    )


def _validate_execution_directions(
    directions: frozenset[tuple[str, str, str]],
    pairs: frozenset[tuple[str, str]],
) -> None:
    invalid = {
        direction
        for direction in directions
        if direction[2] not in {"long", "short"} or direction[:2] not in pairs
    }
    if invalid:
        raise MultiAssetLiveRunnerError(
            f"executable provider directions exceed provider-symbol scope: {invalid}"
        )
