"""Tests for the execution-incapable HIP-3 roster checkpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from hypervector.live.hyperliquid_protocol import (
    Hip3MarketFeeMetadata,
    SolBookLevel,
    SolBookSnapshot,
    SolMarketMetadata,
    SolPositionSnapshot,
    SolVenuePreflight,
)
from hypervector.research.hip3_roster_observer import (
    ACTIVE_HIP3_MARKETS,
    Hip3RosterObserver,
)


class _Reader:
    """Return deterministic read-only venue truth for one market."""

    def __init__(
        self,
        symbol: str,
        leverage: int,
        *,
        wrong_symbol: bool = False,
        growth_mode: bool | None = True,
    ) -> None:
        self.symbol = symbol
        self.leverage = leverage
        self.wrong_symbol = wrong_symbol
        self.growth_mode = growth_mode

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        assert expected_max_leverage == self.leverage
        symbol = "xyz:WRONG" if self.wrong_symbol else self.symbol
        return SolVenuePreflight(
            market=SolMarketMetadata(symbol, 3, self.leverage),
            mark_price=100.25,
            price_tick=0.01,
            size_step=0.001,
            fees=SimpleNamespace(
                maker_rate=0.00015,
                taker_rate=0.00045,
                active_referral_discount=0.04,
            ),
            account_value_usd=507.08,
            withdrawable_usd=500.0,
            position=_position(),
            account_abstraction_mode="unifiedAccount",
        )

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        assert depth_levels == 20
        bids = tuple(
            SolBookLevel(100.0 - index * 0.01, float(index + 1), index + 1)
            for index in range(20)
        )
        asks = tuple(
            SolBookLevel(100.5 + index * 0.01, float(index + 2), index + 1)
            for index in range(20)
        )
        return SolBookSnapshot(
            exchange_timestamp_ms=1_786_000_000_000,
            bids=bids,
            asks=asks,
            mid_price=100.25,
            spread_bps=49.87531172069825,
            bid_depth=sum(level.size for level in bids),
            ask_depth=sum(level.size for level in asks),
            order_pressure=-0.08695652173913043,
        )

    def open_orders(self) -> tuple[object, ...]:
        return ()

    def hip3_fee_metadata(self) -> Hip3MarketFeeMetadata:
        return Hip3MarketFeeMetadata(
            deployer_fee_scale=1.0,
            growth_mode=self.growth_mode,
            collateral_token_index=0,
        )


def test_checkpoint_reports_exact_active_roster_and_historical_wti() -> None:
    """Active Brent must not be mislabeled as live WTI."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    observer = Hip3RosterObserver(readers=readers)

    result = observer.snapshot(datetime(2026, 8, 6, 16, 0, tzinfo=UTC))

    assert result["status"] == "available"
    assert result["active_symbols"] == [
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    ]
    assert result["execution_authority"] == "none"
    assert result["report_only"] is True
    assert result["automatic_promotion"] is False
    assert result["runtime_strategy_changed"] is False
    assert result["signing_client_constructed"] is False
    assert result["requested_aliases"]["WTIOIL"]["live_symbol"] is None
    assert result["requested_aliases"]["WTIOIL"]["historical_symbol"] == "cash:WTI"
    assert result["requested_aliases"]["WTIOIL"]["status"] == "historical_only"


def test_checkpoint_exposes_depth_windows_and_account_truth() -> None:
    """The TUI boundary needs useful book and account data rather than zeros."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }

    result = Hip3RosterObserver(readers=readers).snapshot(
        datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
    )
    market = result["markets"][0]

    assert market["symbol"] == "xyz:SP500"
    assert market["venue"]["mark_price"] == 100.25
    assert market["book"]["level_count"] == {"bids": 20, "asks": 20}
    assert market["book"]["depth_5"]["bid_base"] == 15.0
    assert market["book"]["depth_20"]["bid_base"] == 210.0
    assert len(market["book"]["bids"]) == 20
    assert market["account"]["account_value_usd"] == 507.08
    assert market["account"]["open_order_count"] == 0
    assert market["account"]["position"]["size_signed"] == 0.0


def test_checkpoint_publishes_exact_hourly_funding_from_one_source_read() -> None:
    """The existing TUI funding field must receive signed hourly rates, including zero."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    rates = dict(zip(readers, (0.0000125, -0.00002, 0.0, None, 0.00003)))
    calls = 0

    def funding() -> dict[str, float | None]:
        """Return one complete shared funding snapshot."""
        nonlocal calls
        calls += 1
        return rates

    result = Hip3RosterObserver(readers=readers, funding_source=funding).snapshot(
        datetime(2026, 9, 11, 14, 0, tzinfo=UTC)
    )

    assert calls == 1
    assert result["execution_authority"] == "none"
    for market in result["markets"]:
        assert market["venue"]["funding_rate_hourly"] == rates[market["symbol"]]
        assert market["venue"]["funding_source"] == "hyperliquid_info_metaAndAssetCtxs"
    assert result["markets"][3]["venue"]["funding_status"] == "unavailable"
    assert result["markets"][2]["venue"]["funding_status"] == "available"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0.01"])
def test_checkpoint_rejects_invalid_funding_source_values(value: object) -> None:
    """Invalid funding cannot become a plausible number in the native display."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    rates = dict.fromkeys(readers, value)
    observer = Hip3RosterObserver(readers=readers, funding_source=lambda: rates)
    with pytest.raises(ValueError, match="funding.*finite number"):
        observer.snapshot(datetime(2026, 9, 11, 14, 0, tzinfo=UTC))


@pytest.mark.parametrize("rates", [{}, {"cash:WTI": 0.001}])
def test_checkpoint_rejects_funding_roster_mismatch(
    rates: dict[str, float | None],
) -> None:
    """A missing or wrong namespace must not silently assign another market's rate."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    observer = Hip3RosterObserver(readers=readers, funding_source=lambda: rates)
    with pytest.raises(ValueError, match="funding roster mismatch"):
        observer.snapshot(datetime(2026, 9, 11, 14, 0, tzinfo=UTC))


def test_checkpoint_explicitly_labels_unconfigured_funding() -> None:
    """Legacy callers remain compatible while exposing why funding is absent."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    result = Hip3RosterObserver(readers=readers).snapshot(
        datetime(2026, 9, 11, 14, 0, tzinfo=UTC)
    )
    assert all(row["venue"]["funding_rate_hourly"] is None for row in result["markets"])
    assert all(
        row["venue"]["funding_status"] == "unconfigured" for row in result["markets"]
    )


@pytest.mark.parametrize("response", [None, []])
def test_configured_funding_source_cannot_silently_become_unconfigured(
    response: object,
) -> None:
    """A malformed configured source must not pass as a legacy optional omission."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    observer = Hip3RosterObserver(readers=readers, funding_source=lambda: response)
    with pytest.raises(ValueError, match="funding source must return a mapping"):
        observer.snapshot(datetime(2026, 9, 11, 14, 0, tzinfo=UTC))


def test_checkpoint_refreshes_funding_without_reusing_failed_previous_poll() -> None:
    """A failed refresh propagates to the sidecar's unavailable-state publisher."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }
    calls = 0

    def funding() -> dict[str, float | None]:
        """Supply one valid poll followed by an explicit source failure."""
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("funding refresh failed")
        return dict.fromkeys(readers, 0.00001)

    observer = Hip3RosterObserver(readers=readers, funding_source=funding)
    observer.snapshot(datetime(2026, 9, 11, 14, 0, tzinfo=UTC))
    with pytest.raises(ValueError, match="funding refresh failed"):
        observer.snapshot(datetime(2026, 9, 11, 14, 2, tzinfo=UTC))


def test_checkpoint_exposes_effective_hip3_fees_not_raw_account_rates() -> None:
    """Growth-mode telemetry must not label base user fees as executable rates."""
    readers = {
        spec.symbol: _Reader(spec.symbol, spec.expected_max_leverage)
        for spec in ACTIVE_HIP3_MARKETS
    }

    result = Hip3RosterObserver(readers=readers).snapshot(
        datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
    )
    venue = result["markets"][0]["venue"]

    assert venue["account_base_maker_fee_rate"] == 0.00015
    assert venue["account_base_taker_fee_rate"] == 0.00045
    assert venue["active_referral_discount"] == 0.04
    assert venue["deployer_fee_scale"] == 1.0
    assert venue["growth_mode"] is True
    assert venue["aligned_quote_status"] == "unresolved_conservative_false"
    assert venue["maker_fee_rate"] == pytest.approx(0.0000288)
    assert venue["taker_fee_rate"] == pytest.approx(0.0000864)


def test_checkpoint_preserves_unresolved_growth_mode_without_fake_fee() -> None:
    """Incomplete metadata must not erase other market telemetry or invent rates."""
    readers = {
        spec.symbol: _Reader(
            spec.symbol,
            spec.expected_max_leverage,
            growth_mode=None if spec.symbol == "xyz:GOLD" else True,
        )
        for spec in ACTIVE_HIP3_MARKETS
    }

    result = Hip3RosterObserver(readers=readers).snapshot(
        datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
    )
    gold = next(row for row in result["markets"] if row["symbol"] == "xyz:GOLD")

    assert gold["venue"]["effective_fee_status"] == "unresolved_growth_mode"
    assert gold["venue"]["maker_fee_rate"] is None
    assert gold["venue"]["taker_fee_rate"] is None
    assert gold["book"]["level_count"] == {"bids": 20, "asks": 20}


def test_checkpoint_rejects_reader_identity_mismatch() -> None:
    """A namespace mismatch must fail instead of publishing plausible telemetry."""
    readers = {
        spec.symbol: _Reader(
            spec.symbol,
            spec.expected_max_leverage,
            wrong_symbol=spec.symbol == "xyz:GOLD",
        )
        for spec in ACTIVE_HIP3_MARKETS
    }

    with pytest.raises(ValueError, match="xyz:GOLD reader returned xyz:WRONG"):
        Hip3RosterObserver(readers=readers).snapshot(
            datetime(2026, 8, 6, 16, 0, tzinfo=UTC)
        )


def _position() -> SolPositionSnapshot:
    return SolPositionSnapshot(
        size_signed=0.0,
        entry_price=None,
        liquidation_price=None,
        margin_used_usd=0.0,
        position_value_usd=0.0,
        unrealized_pnl_usd=0.0,
        leverage_type=None,
        leverage=None,
    )
