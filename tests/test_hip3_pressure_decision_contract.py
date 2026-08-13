"""Decision-time invariance for live HIP-3 breakout pressure."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_cohort_providers import (
    HIP3_BREAKOUT_INDEX_STRATEGY,
    HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY,
    Hip3BreakoutPressureCollector,
)
from hypervector.live.hip3_ledger_pressure import Hip3PressureObservation
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)

_PARITY_JOURNAL = Path(
    "docs/research-journal/hip3-live-pressure-freshness-parity-v2.json"
)


def _bars() -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-07T12:00:00Z", periods=12, freq="15min")
    closes = [100.0 + position for position in range(len(timestamps))]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0] * len(timestamps),
        }
    )


def _long_breakout(
    bars: pd.DataFrame,
    config: Hip3BreakoutPressureConfig,
) -> pd.DataFrame:
    del config
    output = pd.DataFrame(index=bars.index)
    output["long_entry"] = False
    output.loc[output.index[-1], "long_entry"] = True
    output["short_entry"] = False
    output["prior_breakout_high"] = 108.0
    output["prior_breakout_low"] = 98.0
    output["fast_ema"] = 110.0
    output["slow_ema"] = 100.0
    output["decision_imbalance_10"] = bars["decision_imbalance_10"]
    return output


class _RecordingPressureSource:
    def __init__(self, values: tuple[Hip3PressureObservation, ...]) -> None:
        self._values = values
        self.cutoffs: list[int] = []

    def latest_at_or_before(
        self,
        symbol: str,
        not_after_ms: int,
    ) -> Hip3PressureObservation | None:
        """Return the newest observation within the requested causal prefix."""
        assert symbol == "xyz:SP500"
        self.cutoffs.append(not_after_ms)
        eligible = tuple(
            value for value in self._values if value.recv_ts_ms <= not_after_ms
        )
        return max(eligible, key=lambda value: value.recv_ts_ms, default=None)


def test_breakout_pressure_is_frozen_at_completed_bar_decision_time() -> None:
    """A later polling phase must not replace fresh pre-close pressure."""
    decision = pd.Timestamp("2026-08-07T15:00:00Z")
    decision_ms = int(decision.timestamp() * 1_000)
    source = _RecordingPressureSource(
        (
            Hip3PressureObservation(decision_ms - 53, 0.6),
            Hip3PressureObservation(decision_ms + 1_000, -0.6),
        )
    )
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=source,
        signal_builder=_long_breakout,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=decision + pd.Timedelta(seconds=8),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert source.cutoffs == [decision_ms]
    assert len(batch.intents) == 1
    metrics = batch.evaluations[0].readiness.metrics
    assert metrics["imbalance_10"] == pytest.approx(0.6)
    assert metrics["pressure_age_seconds"] == pytest.approx(0.053)
    assert metrics["pressure_status"] == "available"


@pytest.mark.parametrize(
    ("values", "expected_status"),
    [
        ((), "no_candidate"),
        ((-31_000, 0.6), "stale_candidate"),
    ],
)
def test_breakout_pressure_reports_why_no_candidate_is_usable(
    values: tuple[object, ...],
    expected_status: str,
) -> None:
    """Unavailable pressure must retain an actionable causal diagnosis."""
    decision = pd.Timestamp("2026-08-07T15:00:00Z")
    decision_ms = int(decision.timestamp() * 1_000)
    observations = (
        ()
        if not values
        else (Hip3PressureObservation(decision_ms + int(values[0]), float(values[1])),)
    )
    collector = Hip3BreakoutPressureCollector(
        strategy_id=HIP3_BREAKOUT_INDEX_STRATEGY,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=_RecordingPressureSource(observations),
        signal_builder=_long_breakout,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=decision + pd.Timedelta(seconds=8),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert batch.intents == ()
    evaluation = batch.evaluations[0]
    assert evaluation.readiness.metrics["pressure_status"] == expected_status
    assert f"L2 STATUS {expected_status.upper()}" in evaluation.readiness.indicators


@pytest.mark.parametrize(
    (
        "strategy_id",
        "pressure_age_ms",
        "expected_status",
        "expected_intents",
        "maximum_age_seconds",
    ),
    [
        (HIP3_BREAKOUT_INDEX_STRATEGY, 15_001, "available", 1, 30.0),
        (HIP3_BREAKOUT_INDEX_STRATEGY, 30_001, "stale_candidate", 0, 30.0),
        (HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY, 15_000, "available", 1, 15.0),
        (HIP3_BREAKOUT_INDEX_FRESH15_STRATEGY, 15_001, "stale_candidate", 0, 15.0),
    ],
)
def test_breakout_pressure_uses_versioned_freshness_boundary(
    strategy_id: str,
    pressure_age_ms: int,
    expected_status: str,
    expected_intents: int,
    maximum_age_seconds: float,
) -> None:
    """The parity fix must not rewrite the historical v1 live contract."""
    decision = pd.Timestamp("2026-08-07T15:00:00Z")
    decision_ms = int(decision.timestamp() * 1_000)
    collector = Hip3BreakoutPressureCollector(
        strategy_id=strategy_id,
        config=Hip3BreakoutPressureConfig(3, 2, 3, 0.2, 80.0),
        pressure_source=_RecordingPressureSource(
            (Hip3PressureObservation(decision_ms - pressure_age_ms, 0.6),)
        ),
        signal_builder=_long_breakout,
    )

    batch = collector(
        _bars(),
        symbol="xyz:SP500",
        observed_at=decision + pd.Timedelta(seconds=8),
        after_decision_time_ms=int(
            pd.Timestamp("2026-08-07T14:45:00Z").timestamp() * 1_000
        ),
    )

    assert len(batch.intents) == expected_intents
    metrics = batch.evaluations[0].readiness.metrics
    assert metrics["pressure_status"] == expected_status
    assert metrics["maximum_pressure_age_seconds"] == maximum_age_seconds


def test_parity_journal_reconciles_affected_closed_trade_attribution() -> None:
    """The immutable diagnosis must reconcile the exact four affected losses."""
    report = json.loads(_PARITY_JOURNAL.read_text())
    trades = report["closed_entry_actions_older_than_15_seconds"]
    attribution = report["closed_pnl_attribution"]

    assert len(trades) == 4
    assert all(row["pressure_age_seconds"] > 15.0 for row in trades)
    assert sum(row["net_pnl_usd"] for row in trades) == pytest.approx(-2.097088)
    assert attribution["current_run_net_pnl_usd"] == pytest.approx(-3.117881)
    assert attribution["affected_share_of_absolute_run_loss_pct"] == pytest.approx(
        67.26003975135677
    )
