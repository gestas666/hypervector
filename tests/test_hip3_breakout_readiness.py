"""Structured readiness and exact depth evidence for HIP-3 breakout routes."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_INDEX_STRATEGY,
    Hip3BreakoutPressureCollector,
    Hip3LedgerPressureSource,
    Hip3PressureObservation,
)
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from test_hip3_cohort_providers import _PressureSource, _bars, _breakout_signals


def _short_breakout_signals(
    bars: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
) -> pd.DataFrame:
    output = _breakout_signals(bars, config)
    output["long_entry"] = False
    output["short_entry"] = False
    output.loc[output.index[-1], "short_entry"] = True
    output["prior_breakout_high"] = 118.0
    output["prior_breakout_low"] = 112.0
    output["fast_ema"] = 100.0
    output["slow_ema"] = 110.0
    return output


def test_breakout_collector_exposes_structured_decision_geometry() -> None:
    """Prospective challengers must not parse levels and EMAs from display text."""
    decision_ms = int(pd.Timestamp("2026-08-07T15:00:00Z").timestamp() * 1_000)
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=_PressureSource(
            Hip3PressureObservation(decision_ms - 1_000, -0.6)
        ),
        signal_builder=_short_breakout_signals,
    )
    batch = collector(
        _bars(),
        symbol="xyz:SPCX",
        observed_at=pd.Timestamp("2026-08-07T15:00:05Z"),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    metrics = batch.evaluations[0].readiness.metrics
    assert _geometry(metrics) == {
        "prior_breakout_high": 118.0,
        "prior_breakout_low": 112.0,
        "ema_fast": 100.0,
        "ema_slow": 110.0,
        "ema_fast_period": 2,
        "ema_slow_period": 3,
        "breakout_level": 112.0,
        "reference_close": 111.0,
    }
    assert metrics["directional_breakout_distance_bps"] == pytest.approx(89.2857)
    assert metrics["breakout_distance_semantics"] == "positive_beyond_side_level_v1"


def _geometry(metrics: dict[str, object]) -> dict[str, object]:
    fields = (
        "prior_breakout_high",
        "prior_breakout_low",
        "ema_fast",
        "ema_slow",
        "ema_fast_period",
        "ema_slow_period",
        "breakout_level",
        "reference_close",
    )
    return {field: metrics[field] for field in fields}


def test_ledger_pressure_uses_exact_first_ten_levels(tmp_path: Path) -> None:
    """Depth beyond level ten cannot contaminate the strategy confirmation."""
    asset = tmp_path / "xyz:sp500.jsonl"
    payload = {
        "event_type": "book_observation",
        "payload": {
            "source": "hyperliquid_mainnet_l2_rest",
            "recv_ts_ms": 123,
            "bids": [{"size": 1.0}] * 10 + [{"size": 100.0}],
            "asks": [{"size": 2.0}] * 10 + [{"size": 100.0}],
        },
    }
    asset.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    source = Hip3LedgerPressureSource(
        asset_ledgers={"xyz:SP500": asset},
        cohort_ledger=tmp_path / "decisions.jsonl",
    )

    observed = source.latest_at_or_before("xyz:SP500", 123)

    assert observed is not None
    assert observed.recv_ts_ms == 123
    assert observed.imbalance_10 == pytest.approx(-1.0 / 3.0)


def test_ledger_pressure_selects_newest_book_before_cycle_cutoff(
    tmp_path: Path,
) -> None:
    """A post-reconcile book cannot hide the preceding causal observation."""
    asset = tmp_path / "xyz:sp500.jsonl"
    rows = [
        {
            "event_type": "book_observation",
            "payload": {
                "source": "hyperliquid_mainnet_l2_rest",
                "recv_ts_ms": recv_ts_ms,
                "bids": [{"size": bid_size}] * 10,
                "asks": [{"size": ask_size}] * 10,
            },
        }
        for recv_ts_ms, bid_size, ask_size in (
            (1_000, 3.0, 1.0),
            (2_000, 1.0, 3.0),
        )
    ]
    asset.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    source = Hip3LedgerPressureSource(
        asset_ledgers={"xyz:SP500": asset},
        cohort_ledger=tmp_path / "decisions.jsonl",
    )

    observed = source.latest_at_or_before("xyz:SP500", 1_500)

    assert observed is not None
    assert observed.recv_ts_ms == 1_000
    assert observed.imbalance_10 == pytest.approx(0.5)
