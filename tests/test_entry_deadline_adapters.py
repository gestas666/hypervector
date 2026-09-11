"""The real IOC adapter methods must check after metadata and lot preparation."""

from pathlib import Path

import pytest
from entry_deadline_fixtures import DECISION_MS, Case, Clock, scenario
from test_hyperliquid_btc_adapter import _ADDRESS, _CLOID, _Exchange, _Info

from hypervector.live.entry_submission_deadline import (
    EntryDeadlineExpired,
    EntrySubmissionDeadline,
)
from hypervector.live.hyperliquid_btc_adapter import BtcHyperliquidAdapter
from hypervector.live.hyperliquid_sol_adapter import SolHyperliquidAdapter
from hypervector.live.multi_asset_directional_adapter import (
    MultiAssetDirectionalAdapter,
)
from hypervector.live.sol_order_restart import pending_order_intent
from hypervector.live.sol_range_onset_state import SolLiveState


class DelayedInfo(_Info):
    """Supply named fake metadata only after a controlled blocking-read delay."""

    def __init__(self, clock: Clock, symbol: str, delay_ms: int) -> None:
        super().__init__()
        self.clock, self.symbol, self.delay_ms = clock, symbol, delay_ms
        self.metadata_calls = 0

    def meta(self, dex: str = "") -> object:
        """Preserve the requested namespace while delaying the fake response."""
        expected = self.symbol.split(":")[0] if ":" in self.symbol else ""
        assert dex == expected
        self.metadata_calls += 1
        self.clock.offset_us += self.delay_ms * 1_000
        return {"universe": [{"name": self.symbol, "szDecimals": 2, "maxLeverage": 20}]}


def _adapter(
    info: DelayedInfo, exchange: _Exchange, symbol: str
) -> SolHyperliquidAdapter | MultiAssetDirectionalAdapter:
    if symbol == "standalone_SOL":
        return SolHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=_ADDRESS,
            max_notional_usd=100,
            slippage_fraction=0.002,
        )
    return MultiAssetDirectionalAdapter(
        BtcHyperliquidAdapter(
            info=info,
            exchange=exchange,
            account_address=_ADDRESS,
            max_notional_usd=100,
            slippage_fraction=0.002,
            symbol=symbol,
            perp_dex="xyz" if ":" in symbol else "",
        )
    )


@pytest.mark.parametrize(
    "symbol",
    [
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:BRENTOIL",
        "standalone_SOL",
    ],
)
@pytest.mark.parametrize("delay_ms", [0, 1_000, 2_000])
@pytest.mark.parametrize("side", ["long", "short"])
def test_sdk_dispatch_rechecks_after_market_metadata(
    symbol: str,
    delay_ms: int,
    side: str,
) -> None:
    """Both adapter implementations reject expiry after their own blocking work."""
    clock = Clock(29_000_000)
    actual_symbol = "SOL" if symbol == "standalone_SOL" else symbol
    info, exchange = DelayedInfo(clock, actual_symbol, delay_ms), _Exchange()
    adapter = _adapter(info, exchange, symbol)
    deadline = EntrySubmissionDeadline(DECISION_MS, 30_000, clock.milliseconds)
    deadline.check("adapter_dispatch")
    if delay_ms > 1_000:
        with pytest.raises(EntryDeadlineExpired):
            adapter.submit_entry(
                side=side,
                requested_notional_usd=22.5,
                mark_price=73,
                client_order_id=_CLOID,
                entry_deadline=deadline,
            )
        assert exchange.calls == []
    else:
        adapter.submit_entry(
            side=side,
            requested_notional_usd=22.5,
            mark_price=73,
            client_order_id=_CLOID,
            entry_deadline=deadline,
        )
        assert [name for name, _ in exchange.calls] == ["market_open"]
        assert exchange.calls[0][1]["name"] == actual_symbol
        assert exchange.calls[0][1]["is_buy"] is (side == "long")
    assert info.metadata_calls == 1
    assert deadline.last_observation.boundary == "sdk_dispatch"
    assert deadline.last_observation.age_ms == 29_000 + delay_ms


def test_adapter_preparation_expiry_restores_real_engine_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the actual order-submission, directional adapter and engine path."""
    state = scenario(tmp_path, Case("adapter_expiry", 29_000_000))
    info, exchange = DelayedInfo(state.clock, "SOL", 2_000), _Exchange()
    monkeypatch.setattr(
        state.engine._orders, "_adapter", _adapter(info, exchange, "SOL")
    )
    assert state.runner.poll_once() == 0
    assert exchange.calls == []
    assert state.engine.snapshot.state is SolLiveState.FLAT
    records = state.ledger.read_all()
    marker = next(
        row["payload"] for row in records if row["event_type"] == "entry_not_submitted"
    )
    assert marker["submission_boundary"] == "sdk_dispatch"
    assert marker["submission_age_ms"] == 31_000
    assert pending_order_intent(records) is None
