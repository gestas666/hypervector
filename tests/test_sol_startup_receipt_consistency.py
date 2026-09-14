"""Bounded startup receipt waiting must preserve exact ownership and fail-closed behavior."""

from collections.abc import Mapping
from unittest.mock import Mock

import pytest
from test_sol_range_onset_live_reconcile import _record, _stop, _stop_fill, _venue

from hypervector.live.hyperliquid_protocol import SolLiveAdapterProtocol
from hypervector.live.sol_range_onset_consistency import SolReconciliationPoller
from hypervector.live.sol_range_onset_reconcile import SolStartupReconciliationError
from hypervector.live.sol_startup_receipt_consistency import wait_for_stable_startup

PROFILE = "a" * 64


def records() -> list[Mapping[str, object]]:
    """Declare complete, profile-scoped ownership of one exact stop-protected position."""
    return [
        _record(
            "OPEN",
            entry_oid=101,
            stop_oid=202,
            position_size_signed=0.3,
            opened_at_ms=1,
            profile_fingerprint=PROFILE,
        )
    ]


def poller(adapter: Mock, sleeps: list[float]) -> SolReconciliationPoller:
    """Use a bounded three-read policy with a recording offline sleeper."""
    return SolReconciliationPoller(
        adapter=adapter,
        attempts=3,
        delay_seconds=0.25,
        sleep_fn=sleeps.append,
    )


def test_delayed_owned_exit_recovers_on_the_last_permitted_read() -> None:
    """Startup may wait for evidence but cannot infer closure from flat exposure alone."""
    adapter = Mock(spec=SolLiveAdapterProtocol)
    initial, complete = _venue(0), _venue(0, fills=[_stop_fill()])
    adapter.reconcile.side_effect = [initial, initial, complete]
    sleeps: list[float] = []
    result, confirmed = wait_for_stable_startup(
        records=records(),
        venue=initial,
        expected_profile_fingerprint=PROFILE,
        poller=poller(adapter, sleeps),
    )
    assert result.disposition == "protective_stop_filled" and confirmed is complete
    assert sleeps == [0.25, 0.25] and adapter.reconcile.call_count == 3


@pytest.mark.parametrize("foreign_fill", [False, True])
def test_missing_or_wrong_owned_fill_exhausts_the_bound_and_stays_an_error(
    foreign_fill: bool,
) -> None:
    """Unrelated fills cannot satisfy an owned stop or silently convert the mismatch to flat."""
    adapter = Mock(spec=SolLiveAdapterProtocol)
    initial = _venue(0, fills=[_stop_fill(oid=999)] if foreign_fill else [])
    adapter.reconcile.return_value = initial
    sleeps: list[float] = []
    with pytest.raises(SolStartupReconciliationError, match="position size mismatch"):
        wait_for_stable_startup(
            records=records(),
            venue=initial,
            expected_profile_fingerprint=PROFILE,
            poller=poller(adapter, sleeps),
        )
    assert sleeps == [0.25, 0.25] and adapter.reconcile.call_count == 3


@pytest.mark.parametrize("foreign_order", [False, True])
def test_exposure_and_unknown_order_mismatches_are_not_receipt_waits(foreign_order: bool) -> None:
    """Only the locally owned flat transition qualifies for bounded receipt waiting."""
    adapter = Mock(spec=SolLiveAdapterProtocol)
    initial = _venue(0, orders=[_stop(oid=999)]) if foreign_order else _venue(0.2, [_stop()])
    sleeps: list[float] = []
    with pytest.raises(SolStartupReconciliationError):
        wait_for_stable_startup(
            records=records(),
            venue=initial,
            expected_profile_fingerprint=PROFILE,
            poller=poller(adapter, sleeps),
        )
    assert not sleeps and adapter.reconcile.call_count == 0


def test_new_conflicting_exposure_during_wait_propagates_without_more_retries() -> None:
    """The receipt condition must not swallow a changed exposure or ownership error."""
    adapter = Mock(spec=SolLiveAdapterProtocol)
    adapter.reconcile.return_value = _venue(-0.3, [_stop()])
    sleeps: list[float] = []
    with pytest.raises(SolStartupReconciliationError):
        wait_for_stable_startup(
            records=records(),
            venue=_venue(0),
            expected_profile_fingerprint=PROFILE,
            poller=poller(adapter, sleeps),
        )
    assert adapter.reconcile.call_count == 1 and not sleeps
