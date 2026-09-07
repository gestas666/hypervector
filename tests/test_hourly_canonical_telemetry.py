"""Session-bounded hourly routes receive causal, non-executable regime context."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.live.canonical_regime_telemetry import (
    CanonicalRegimeTelemetryCollector,
)
from hypervector.live.configured_canonical_regime import (
    configured_canonical_regime_symbols,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config


def test_v89_canonical_scope_includes_every_configured_hourly_route() -> None:
    """Explicit hourly mechanisms opt into telemetry without changing legacy scope."""
    config = load_multi_asset_live_config(
        Path("configs/multi_asset_growth_first_5000_noncrypto_research_v89.toml"),
        mode="observe",
    )
    assert configured_canonical_regime_symbols(config) == config.symbols


def _session(start: str, length: int, price: float) -> pd.DataFrame:
    values = price + np.arange(length) * 0.01
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=length, freq="1min", tz="UTC"),
            "open": values,
            "high": values + 0.5,
            "low": values - 0.5,
            "close": values,
            "volume": 10.0,
        }
    )


@pytest.mark.parametrize("length", [3, 180])
def test_session_gap_resets_history_and_partial_bar_has_no_effect(length: int) -> None:
    """The actual detector ignores pre-gap prices and emits no executable action."""
    prior = _session("2026-09-01T10:00", 360, 900.0)
    current = _session("2026-09-02T10:00", length, 100.0)
    observed = current.timestamp.iloc[-1]
    boundary = int((observed - pd.Timedelta(minutes=2)).timestamp() * 1000)
    outputs = []
    for bars in (current.iloc[:-1], pd.concat([prior, current], ignore_index=True)):
        collector = CanonicalRegimeTelemetryCollector(
            symbols=("xyz:SPCX",),
            legacy_execution_enabled=False,
        )
        collector.activate(boundary)
        output = collector.collect({("xyz:SPCX", "1m"): bars}, observed)
        assert len(output) == 2
        assert all(row.readiness.metrics["sma_fast"] is None for row in output)
        assert all(
            not row.eligible and row.side is None and not row.exit_sides
            for row in output
        )
        assert all(row.decision_action == "regime_observation" for row in output)
        assert collector.collect({("xyz:SPCX", "1m"): bars}, observed) == ()
        outputs.append(output)
    assert outputs[0] == outputs[1]
