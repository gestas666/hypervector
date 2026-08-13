"""Contract tests for the frozen source-session short replay."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pandas as pd

from hypervector.research.source_follow_portfolio_models import SourceSignal


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_short_session_replay.py")
    assert path.is_file(), "short session replay script is missing"
    spec = importlib.util.spec_from_file_location("short_session_replay", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("short session replay script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_replay_retains_only_frozen_half_open_utc_window() -> None:
    """The 06-15 challenger must retain 06:00 through 14:59 UTC only."""
    module = _load_script()
    signals = tuple(
        SourceSignal(f"2026-01-01T{hour:02d}:00:00+00:00") for hour in (5, 6, 14, 15)
    )

    selected = module._session_signals(signals)

    assert [signal.decision_time_utc for signal in selected] == [
        "2026-01-01T06:00:00+00:00",
        "2026-01-01T14:00:00+00:00",
    ]


def test_session_replay_changes_signals_only_and_has_no_authority() -> None:
    """Both arms must share one risk contract and remain report-only."""
    module = _load_script()
    configs = module._configs(15_000.0, "trade-through")
    contract = module._contract(15_000.0, "trade-through")

    assert tuple(configs) == ("all_day_control", "session_06_15")
    assert configs["all_day_control"] == configs["session_06_15"]
    assert configs["all_day_control"].margin_fraction == 0.35
    assert configs["all_day_control"].leverage == 30.0
    assert contract["execution_authority"] == "none"
    assert contract["runtime_strategy_changed"] is False
    assert contract["session_utc"] == "[06:00,15:00)"


def test_session_replay_uses_completed_five_minute_range_bars() -> None:
    """The report must not evaluate its range gate on raw minute candles."""
    module = _load_script()
    index = pd.date_range("2026-01-01", periods=5, freq="1min", tz="UTC")
    minute_bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": [101, 102, 103, 104, 105],
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )

    signal_bars = module._signal_bars(minute_bars)

    assert list(signal_bars.index) == [index[0]]
    assert signal_bars.iloc[0]["high"] == 105.0
