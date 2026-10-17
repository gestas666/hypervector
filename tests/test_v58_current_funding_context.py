"""Current official-funding sensitivity for the V58 research roster."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hyperliquid.utils.error import ClientError

import hypervector.research.v58_current_funding_context as funding_context

from hypervector.research.v58_current_funding_context import (
    CurrentFundingContext,
    current_funding_context_payload,
    load_v58_current_funding_context,
)

_CONFIG = Path("configs/multi_asset_growth_first_5000_eight_asset_incremental_v58.toml")
_STRESS = Path(
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)


class _FundingReader:
    def read(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> Sequence[Mapping[str, object]]:
        return (
            {
                "coin": symbol,
                "fundingRate": "0.00001",
                "premium": "-0.0001",
                "time": end_ms - 60_000,
            },
        )


class _StaleFundingReader:
    def read(
        self, symbol: str, start_ms: int, end_ms: int
    ) -> Sequence[Mapping[str, object]]:
        return (
            {
                "coin": symbol,
                "fundingRate": "0.00001",
                "premium": "-0.0001",
                "time": start_ms,
            },
        )


@pytest.mark.evidence
def test_current_funding_is_route_bound_and_not_a_forecast() -> None:
    """Every exact route must retain sides, hold, and frozen-risk comparison."""
    observed_at = datetime(2026, 8, 19, 12, tzinfo=UTC)

    context = load_v58_current_funding_context(
        _CONFIG,
        _STRESS,
        observed_at=observed_at,
        reader=_FundingReader(),
    )
    payload = current_funding_context_payload(context)

    assert payload["status"] == "available"
    assert len(payload["routes"]) == 10
    eth = next(row for row in payload["routes"] if row["symbol"] == "ETH")
    assert eth["maximum_hold_hours"] == 12.0
    assert eth["latest_hourly_funding_rate_bps"] == 0.1
    assert eth["constant_rate_hold_cost_bps_by_side"] == {
        "long": 1.2,
        "short": -1.2,
    }
    assert eth["current_worst_side_cost_bps"] == 1.2
    assert eth["current_exceeds_frozen_adverse"] is True
    assert payload["constant_rate_projection_is_forecast"] is False
    assert payload["sizing_input"] is False
    assert payload["execution_authority"] == "none"


@pytest.mark.evidence
def test_current_funding_rejects_stale_official_evidence() -> None:
    """A report must fail closed when the latest event is more than two hours old."""
    with pytest.raises(
        ValueError, match="latest official funding row is stale for BTC"
    ):
        load_v58_current_funding_context(
            _CONFIG,
            _STRESS,
            observed_at=datetime(2026, 8, 19, 12, tzinfo=UTC),
            reader=_StaleFundingReader(),
        )


def test_live_funding_throttle_is_explicitly_unavailable() -> None:
    """A funding-only 429 must not stale every other research context."""
    loader = getattr(
        funding_context, "load_resilient_live_v58_current_funding_context", None
    )
    assert callable(loader), "resilient live funding loader is missing"

    def throttled_loader(
        _config: Path, _stress: Path, *, observed_at: datetime
    ) -> CurrentFundingContext:
        del observed_at
        raise ClientError(429, None, "limited", {})

    context = loader(
        _CONFIG,
        _STRESS,
        observed_at=datetime(2026, 8, 20, 5, 20, tzinfo=UTC),
        loader=throttled_loader,
    )
    payload = current_funding_context_payload(context)

    assert payload["status"] == "temporarily_unavailable"
    assert payload["failure_reason"] == "http_429_retry_exhausted"
    assert payload["routes"] is None
    assert payload["routes_exceeding_frozen_adverse"] is None
    assert payload["execution_authority"] == "none"
