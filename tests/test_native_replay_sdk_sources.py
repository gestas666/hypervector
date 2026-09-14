"""Recorded-source gaps and exchange constraints must remain explicit in the SDK bridge."""

from decimal import Decimal

import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk import SYMBOL, adapter, sdk

from hypervector.live.hyperliquid_sol_parsing import HyperliquidAdapterError

__all__ = ["deny_external_ports"]
D = Decimal


def test_missing_midpoint_preserves_mark_without_fabricating_a_native_mid() -> None:
    """Observed missing mid fields cannot become mark prices or unbounded old midpoint carries."""
    replay = sdk()
    replay.advance_to(1100)
    replay.observe_prices(SYMBOL, source_time_ms=1100, mark=D(101), mid=None)
    assert replay.account.snapshot().mark_prices[SYMBOL] == D(101)
    assert SYMBOL not in replay.info.all_mids("xyz")
    with pytest.raises(HyperliquidAdapterError, match="mid"):
        adapter(replay).preflight(expected_max_leverage=10)
    replay.advance_to(1200)
    replay.observe_prices(SYMBOL, source_time_ms=1200, mark=D(101), mid=D("100.5"))
    assert replay.info.all_mids("xyz")[SYMBOL] == "100.5"


@pytest.mark.parametrize("clock,mark", [(999, D(101)), (1000, D(101))])
def test_regressing_or_conflicting_price_observations_cannot_change_account_marks(
    clock: int, mark: Decimal
) -> None:
    """A replay quote source cannot go backward or rewrite the same exchange observation."""
    replay = sdk()
    before = replay.account.snapshot()
    with pytest.raises(ValueError, match="price observation"):
        replay.observe_prices(SYMBOL, source_time_ms=clock, mark=mark, mid=mark)
    assert replay.account.snapshot() == before
    assert replay.info.all_mids("xyz")[SYMBOL] == "100"


def test_conflicting_observed_book_preserves_original_counts_and_snapshot() -> None:
    """Original level order counts are retained; same-clock book rewrites are evidence conflicts."""
    replay = sdk()
    payload = {
        "coin": SYMBOL,
        "time": 1000,
        "levels": [[{"px": "99.9", "sz": "100", "n": 2}], [{"px": "100.1", "sz": "100", "n": 7}]],
    }
    replay.observe_book(SYMBOL, payload)
    payload["levels"][1][0]["n"] = 19
    assert replay.info.l2_snapshot(SYMBOL)["levels"][1][0]["n"] == 7
    with pytest.raises(ValueError, match="book observation"):
        replay.observe_book(SYMBOL, payload)


def test_post_only_target_cannot_be_accepted_when_arrival_book_makes_it_marketable() -> None:
    """A marketable ALO target must reject rather than fabricate a resting maker order."""
    replay = sdk()
    client = adapter(replay)
    client.configure_isolated_leverage(10)
    client.submit_entry(
        side="long", requested_notional_usd=500, mark_price=100, client_order_id="0x" + "5" * 32
    )
    before = replay.account.snapshot()
    target = client.submit_target(
        position_size_signed=5, limit_price=99, client_order_id="0x" + "6" * 32
    )
    assert not target.accepted and "post-only" in target.error.lower()
    assert replay.account.snapshot() == before
    assert len(replay.orders) == 1


def test_flat_funding_still_requires_a_nonblank_event_identity() -> None:
    """A malformed funding source row cannot be silently marked processed while flat."""
    replay = sdk()
    before = replay.account.snapshot()
    with pytest.raises(ValueError, match="funding ID"):
        replay.settle_funding(
            "",
            SYMBOL,
            rate=D(".0001"),
            oracle_price=D(101),
            effective_time_ms=1000,
            visible_delay_ms=0,
        )
    assert replay.account.snapshot() == before and not replay.funding_rows


def test_missing_midpoint_does_not_hide_observed_prices_for_other_symbols() -> None:
    """One missing quote must not prevent the native reader from seeing a different asset's quote."""
    from test_native_replay_sdk_engines import cohort_sdk
    from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

    config = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    replay.advance_to(replay.clock.now_ms + 1000)
    replay.observe_prices("xyz:SPCX", source_time_ms=replay.clock.now_ms, mark=D(101), mid=None)
    observed = replay.info.all_mids("xyz")
    assert "xyz:SPCX" not in observed
    assert observed["xyz:BRENTOIL"] == "100" and observed["xyz:SNDK"] == "100"
