from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pandas as pd


def test_hulk_source_maps_completed_bar_to_first_executable_minute() -> None:
    """A 30-minute decision becomes a signal on the minute before its fill boundary."""
    module = importlib.import_module("hypervector.research.btc_v58_hulk_route_source")
    bars = _bars()

    def components(
        strategy: pd.DataFrame, root: Path, *, bar_minutes: int
    ) -> pd.DataFrame:
        assert root == Path("/tmp/source")
        assert bar_minutes == 30
        return pd.DataFrame(index=pd.DatetimeIndex(strategy["bar_open_at"]))

    def quality(indexed: pd.DataFrame, **_: object) -> pd.DataFrame:
        return pd.DataFrame(index=indexed.index)

    def signals(
        indexed: pd.DataFrame,
        component_frame: pd.DataFrame,
        quality_frame: pd.DataFrame,
        config: object,
    ) -> pd.DataFrame:
        del component_frame, quality_frame, config
        timestamp = indexed.index[-1]
        return pd.DataFrame(
            [
                {
                    "candidate": "hulk_rebuilt_expansion_v1",
                    "signal_time_utc": timestamp,
                    "side": "short",
                    "score": 8,
                    "eligible": True,
                    "reason": "eligible",
                    "trigger": "wave_cross",
                    "evidence": ("adx_usable",),
                    "stop_anchor": float(indexed.loc[timestamp, "high"]),
                }
            ]
        )

    events = module.build_v58_hulk_short_events(
        bars,
        Path("/tmp/source"),
        "hulk_expansion_short_robust_v3",
        component_builder=components,
        quality_builder=quality,
        signal_builder=signals,
        inspect_source=False,
    )
    assert len(events.events) == 1
    event = events.events[0]
    assert event.signal_time == bars.index[-1]
    assert event.priority == 20
    assert event.strategy_id == "hulk_expansion_short_robust_v3"


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=60, freq="1min", tz="UTC")
    close = 100.0 + np.linspace(0.0, 1.0, len(index))
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
