"""The actual engine must use its supplied clock for order recovery waits."""

from pathlib import Path

import pytest
from test_asset_live_engine import FakeVenueAdapter, _order, _runtime, _venue

from hypervector.live.hyperliquid_protocol import HyperliquidOrderStatus
from hypervector.live.hyperliquid_parsing import HyperliquidOrderUnavailableError
from hypervector.live.asset_engine import AssetLiveEngine
from hypervector.live.asset_state import AssetLiveState
from hypervector.research.native_replay_clock import ReplayClock


def test_engine_recovery_wait_uses_the_injected_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost response becomes recoverable only after the injected 250 ms wait."""
    config, ledger = _runtime(tmp_path)
    clock = ReplayClock(1_789_135_200_000)
    initial = clock.now_ms
    stop = _order(202, size=0.30, reduce_only=True, trigger=True)
    adapter = FakeVenueAdapter([_venue(0), _venue(0), _venue(0.30), _venue(0.30, (stop,))])
    adapter.response_loss.add("entry")
    original = adapter.order_status_by_client_id

    def delayed(client_id: str) -> HyperliquidOrderStatus:
        """Expose the already executed synthetic order after one recovery interval."""
        if clock.now_ms < initial + 250:
            raise HyperliquidOrderUnavailableError("synthetic status has not arrived")
        return original(client_id)

    monkeypatch.setattr(adapter, "order_status_by_client_id", delayed)
    engine = AssetLiveEngine(
        config=config,
        adapter=adapter,
        ledger=ledger,
        credentials_present=True,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
    )
    engine.start()
    result = engine.enter(side="long", mark_price=73, decision_time_ms=initial)
    assert result.state is AssetLiveState.OPEN and result.opened_at_ms == initial
    assert clock.now_ms == initial + 250
    assert sum(name == "submit_entry" for name, _ in adapter.calls) == 1
