"""Prospective BRENTOIL oil-shock shadow decision contracts."""

from __future__ import annotations

import pandas as pd

from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
    BrentoilOilShockShadowCollector,
    BrentoilOilShockShadowCursor,
)
from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)


def test_shadow_freezes_exact_identity_and_symmetric_signal() -> None:
    """A fresh completed shock publishes one exact report-only decision."""
    config = Hip3OilShockReversionConfig(
        return_lookback_bars=2,
        threshold_lookback_bars=6,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )
    collector = BrentoilOilShockShadowCollector(config=config)
    bars = _bars([100.0, 101.0, 99.0, 101.0, 100.0, 100.0, 100.0, 94.0])
    cursor = _cursor(pd.Timestamp("2026-08-15T12:35:00Z"))

    batch = collector(
        bars,
        symbol="xyz:BRENTOIL",
        observed_at=pd.Timestamp("2026-08-15T12:40:05Z"),
        cursor=cursor,
    )

    assert batch.execution_authority == "none"
    assert batch.intents == ()
    assert len(batch.decisions) == 1
    decision = batch.decisions[0]
    assert decision.provider_id == BRENTOIL_OIL_SHOCK_PROVIDER_ID
    assert decision.profile_id == BRENTOIL_OIL_SHOCK_PROFILE_ID
    assert decision.symbol == "xyz:BRENTOIL"
    assert decision.prospective is True
    assert decision.eligible is True
    assert decision.side == "long"
    assert decision.trailing_return_bps < -decision.shock_threshold_bps
    assert decision.decision_delay_ms == 5_000
    assert decision.signal_ohlc_source == "hyperliquid_public_candleSnapshot_5m"
    assert decision.candle_close == 94.0
    assert decision.candle_high == 94.1
    assert len(decision.signal_window_sha256) == 64


def test_late_decision_is_recorded_but_cannot_be_eligible() -> None:
    """A stale unseen bar advances evidence without a retroactive entry claim."""
    config = Hip3OilShockReversionConfig(
        return_lookback_bars=2,
        threshold_lookback_bars=6,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )
    collector = BrentoilOilShockShadowCollector(config=config)

    batch = collector(
        _bars([100.0, 101.0, 99.0, 101.0, 100.0, 100.0, 100.0, 94.0]),
        symbol="xyz:BRENTOIL",
        observed_at=pd.Timestamp("2026-08-15T12:41:00Z"),
        cursor=_cursor(pd.Timestamp("2026-08-15T12:35:00Z")),
    )

    assert len(batch.decisions) == 1
    assert batch.decisions[0].side == "long"
    assert batch.decisions[0].prospective is False
    assert batch.decisions[0].eligible is False
    assert batch.decisions[0].non_action_reason == "decision_stale"


def test_restart_boundary_prevents_duplicate_completed_bar() -> None:
    """A cursor already at the latest close emits no repeated observation."""
    collector = BrentoilOilShockShadowCollector()
    cursor = _cursor(pd.Timestamp("2026-08-15T12:40:00Z"))

    batch = collector(
        _bars([100.0] * 8),
        symbol="xyz:BRENTOIL",
        observed_at=pd.Timestamp("2026-08-15T12:40:05Z"),
        cursor=cursor,
    )

    assert batch.decisions == ()
    assert batch.next_cursor == cursor


def _cursor(boundary: pd.Timestamp) -> BrentoilOilShockShadowCursor:
    return BrentoilOilShockShadowCursor(
        provider_id=BRENTOIL_OIL_SHOCK_PROVIDER_ID,
        profile_id=BRENTOIL_OIL_SHOCK_PROFILE_ID,
        symbol="xyz:BRENTOIL",
        decision_time_ms=int(boundary.timestamp() * 1_000),
        observed_at_ms=int(boundary.timestamp() * 1_000),
    )


def _bars(closes: list[float]) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-15T12:00:00Z", periods=len(closes), freq="5min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": 10.0,
        }
    )
