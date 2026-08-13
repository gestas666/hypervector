"""Sanitized, execution-incapable SOL canary preflight report tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hypervector.live.hyperliquid_protocol import (
    HyperliquidFeeSchedule,
    SolAccountSnapshot,
    SolBookLevel,
    SolBookSnapshot,
    SolFundingPayment,
    SolMarketMetadata,
    SolPositionSnapshot,
    SolReconciliationSnapshot,
    SolVenuePreflight,
)
from hypervector.live.sol_range_onset_config import load_sol_range_onset_config
from hypervector.live.sol_range_onset_read_only_preflight import (
    collect_sol_read_only_preflight,
)

PROFILE = Path("configs/sol_range_onset_canary.toml")
NOW = datetime(2026, 7, 31, 13, 0, tzinfo=UTC)


def _position(size: float = 0.0) -> SolPositionSnapshot:
    return SolPositionSnapshot(size, None, None, 0.0, 0.0, 0.0, None, None)


class FakeReader:
    """Return deterministic official-SDK-shaped read results."""

    def __init__(self, *, size: float = 0.0) -> None:
        position = _position(size)
        self.venue = SolVenuePreflight(
            SolMarketMetadata("SOL", 2, 20),
            73.5,
            0.001,
            0.01,
            HyperliquidFeeSchedule(0.00015, 0.00045),
            150.0,
            150.0,
            position,
        )
        self.reconciliation = SolReconciliationSnapshot(
            SolAccountSnapshot(150.0, 150.0, 0.0, abs(size) * 73.5, position),
            (),
            (),
        )
        levels = (SolBookLevel(73.49, 10.0, 1),)
        asks = (SolBookLevel(73.51, 8.0, 1),)
        self.book = SolBookSnapshot(1000, levels, asks, 73.5, 2.72, 10.0, 8.0, 0.111)
        self.funding_args: tuple[int, int] | None = None

    def preflight(self, *, expected_max_leverage: int) -> SolVenuePreflight:
        assert expected_max_leverage == 20
        return self.venue

    def reconcile(self) -> SolReconciliationSnapshot:
        return self.reconciliation

    def book_snapshot(self, *, depth_levels: int) -> SolBookSnapshot:
        assert depth_levels == 5
        return self.book

    def funding_payments(
        self,
        *,
        start_time_ms: int,
        end_time_ms: int,
    ) -> tuple[SolFundingPayment, ...]:
        self.funding_args = (start_time_ms, end_time_ms)
        return (SolFundingPayment(end_time_ms, -0.01, 0.2, 0.0001, "0xabc"),)


def test_report_is_sanitized_flat_and_sized_from_actual_equity() -> None:
    """The report proves read authority and computes the frozen $22.50 cap."""
    reader = FakeReader()
    config = load_sol_range_onset_config(PROFILE, mode="shadow")

    report = collect_sol_read_only_preflight(
        config=config,
        reader=reader,
        observed_at=NOW,
    )

    assert report["authority"] == {
        "execution_authority": "none",
        "execution_client_constructed": False,
        "signing_key_required": False,
        "operation": "read_only_preflight",
    }
    assert report["account"]["account_value_usd"] == pytest.approx(150.0)
    assert report["account"]["funding_24h_usd"] == pytest.approx(-0.01)
    assert report["venue"]["account_abstraction_mode"] == "disabled"
    assert report["canary"]["planned_notional_usd"] == pytest.approx(22.5)
    assert report["canary"]["stop_bps"] == pytest.approx(80.0)
    assert report["canary"]["technically_ready"] is True
    assert reader.funding_args == (
        int((NOW.timestamp() - 86_400) * 1_000),
        int(NOW.timestamp() * 1_000),
    )


def test_nonflat_state_is_reported_not_hidden() -> None:
    """Existing SOL exposure is an explicit technical readiness failure."""
    report = collect_sol_read_only_preflight(
        config=load_sol_range_onset_config(PROFILE, mode="shadow"),
        reader=FakeReader(size=0.2),
        observed_at=NOW,
    )

    assert report["account"]["flat"] is False
    assert report["canary"]["technically_ready"] is False
    assert report["canary"]["readiness_reasons"] == (
        "SOL account is not flat or has open SOL orders",
    )
