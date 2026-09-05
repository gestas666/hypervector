"""Frozen-route tests for later-window four-Pine validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_features import build_pine_stack_features
from hypervector.research.pine_stack_frozen_route import (
    FrozenPineRoute,
    evaluate_frozen_pine_partition,
    frozen_sol30_route,
)
from hypervector.research.pine_stack_screen import PineStackScreenConfig
from hypervector.research.pine_stack_signals import compose_pine_stack_entries


def _bars(rows: int = 900) -> pd.DataFrame:
    """Return deterministic 30-minute waves with zero funding."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 8.0 * np.sin(positions / 15.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="30min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.75,
            "low": np.minimum(open_, close) - 0.75,
            "close": close,
            "volume": 100.0 + positions,
            "funding_rate": np.zeros(rows),
        }
    )


def test_sol30_route_freezes_the_development_selected_identity() -> None:
    """The later-window replay must not expose a parameter or route search."""
    route = frozen_sol30_route()

    assert route == FrozenPineRoute(
        symbol="SOL",
        bar_minutes=30,
        candidate="cs_trend",
        exit_variant="cs_flip",
    )


def test_frozen_partition_replays_only_declared_route_with_stress() -> None:
    """Nominal and stress results must share one frozen signal identity."""
    bars = _bars()
    features = build_pine_stack_features(bars, bar_minutes=30)
    entries = compose_pine_stack_entries(features, symbol="SOL")
    nominal = PineStackScreenConfig()
    stress = PineStackScreenConfig(
        maker_target_fee_rate=0.00045,
        slippage_bps_per_side=5.0,
    )

    result = evaluate_frozen_pine_partition(
        bars=bars,
        features=features,
        entries=entries,
        route=frozen_sol30_route(),
        venue_max_leverage=20.0,
        nominal_config=nominal,
        stress_config=stress,
    )

    assert result.route == frozen_sol30_route()
    assert result.execution_authority == "none"
    assert result.signal_count == int(entries["candidate"].eq("cs_trend").sum())
    assert result.nominal.completed_trades > 0
    assert result.stress.completed_trades > 0
    assert result.stress.net_pnl_usd < result.nominal.net_pnl_usd
    payload = result.to_dict()
    assert payload["route"]["candidate"] == "cs_trend"
    assert payload["nominal"]["all"]["completed_trades"] > 0
    assert set(payload["stress"]["by_side"]) == {"long", "short"}


def test_frozen_partition_rejects_mismatched_market_identity() -> None:
    """A SOL route must not be silently replayed with another symbol's entries."""
    bars = _bars()
    features = build_pine_stack_features(bars, bar_minutes=30)
    entries = compose_pine_stack_entries(features, symbol="ETH")

    try:
        evaluate_frozen_pine_partition(
            bars=bars,
            features=features,
            entries=entries,
            route=frozen_sol30_route(),
            venue_max_leverage=20.0,
            nominal_config=PineStackScreenConfig(),
            stress_config=PineStackScreenConfig(slippage_bps_per_side=5.0),
        )
    except ValueError as exc:
        assert "route symbol" in str(exc)
    else:
        raise AssertionError("mismatched entry symbol was accepted")
