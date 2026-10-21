"""Falsifier tests for the transition drain's terminal boundary."""

from __future__ import annotations

import pytest

from hypervector.live.multi_asset_live_runner_support import all_flat_and_unowned
from hypervector.live.asset_state import AssetLiveSnapshot, AssetLiveState


@pytest.mark.parametrize("field", ("entry_oid", "stop_oid", "target_oid", "close_oid"))
def test_flat_lifecycle_with_any_owned_order_is_not_drained(field: str) -> None:
    """A flat label cannot conceal an outstanding backend-owned order."""
    values: dict[str, object] = {field: 7}
    snapshot = AssetLiveSnapshot(state=AssetLiveState.FLAT, **values)

    assert all_flat_and_unowned((snapshot,)) is False


def test_flat_unowned_zero_position_is_the_only_terminal_boundary() -> None:
    """The drain completes only after lifecycle and position facts agree."""
    snapshot = AssetLiveSnapshot(
        state=AssetLiveState.FLAT,
        position_size_signed=0.0,
    )

    assert all_flat_and_unowned((snapshot,)) is True


def test_flat_label_with_nonzero_position_is_not_drained() -> None:
    """Venue exposure prevents completion even if lifecycle state is stale."""
    snapshot = AssetLiveSnapshot(
        state=AssetLiveState.FLAT,
        position_size_signed=0.01,
    )

    assert all_flat_and_unowned((snapshot,)) is False
