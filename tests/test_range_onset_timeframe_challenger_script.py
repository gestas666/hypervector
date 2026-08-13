"""Tests for the fixed range-onset timeframe challenger."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

_SCRIPT = Path("scripts/range_onset_timeframe_challenger.py")


def _module() -> ModuleType:
    if not _SCRIPT.is_file():
        pytest.fail("range-onset timeframe challenger script is missing")
    spec = spec_from_file_location("range_onset_timeframe_challenger", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent.resolve()))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPT.parent.resolve()))
    return module


def test_fixed_timeframes_include_lower_cadence_challengers_and_baseline() -> None:
    module = _module()

    assert module.candidate_timeframes() == ("5min", "15min", "30min", "1h")


def test_artifact_is_report_only_and_changes_only_signal_timeframe() -> None:
    module = _module()

    report = module._artifact("HYPE", {"bar_rows": 10}, {"continuous": {}})

    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["candidate_timeframes"] == ["5min", "15min", "30min", "1h"]
    assert (
        report["fixed_entry_logic"]
        == "SMA10/30 cross in completed 5m RANGE or BREAKOUT"
    )
    assert report["fixed_risk"] == {
        "stop_bps": 60.0,
        "maximum_hold_hours": 48,
        "margin_fraction": 0.10,
        "leverage": 5.0,
    }


def test_candidate_summary_retains_trades_and_reports_observed_cadence() -> None:
    module = _module()
    report = {
        "completed_trades": 2,
        "net_pnl_usd": 1.0,
        "limitations": ("bar-only",),
        "trades": (
            _trade("long", "2026-01-01T00:00:00+00:00", 2.0),
            _trade("short", "2026-01-03T00:00:00+00:00", -1.0),
        ),
    }

    summary = module._candidate_summary("15min", report, window_days=10.0)

    assert summary["candidate_id"] == "sma10x30@15min"
    assert summary["cadence"]["trades_per_30_days"] == pytest.approx(6.0)
    assert summary["cadence"]["median_intertrade_hours"] == pytest.approx(48.0)
    assert summary["by_side"]["long"]["wins"] == 1
    assert summary["by_side"]["short"]["losses"] == 1
    assert len(summary["trades"]) == 2


def test_gap_path_attribution_discloses_impacted_trade_contribution() -> None:
    module = _module()
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    bars = pd.DataFrame(
        {"source": ["hl", "hl_gap_fill", "hl", "hl"]},
        index=index,
    )
    touched = _trade("long", index[0].isoformat(), 2.0)
    touched["exit_time_utc"] = index[2].isoformat()
    clean = _trade("short", index[2].isoformat(), -1.0)
    clean["exit_time_utc"] = index[3].isoformat()

    result = module._gap_path_attribution([touched, clean], bars)

    assert result == {
        "gap_fill_rows": 1,
        "trades_touching_gap_fill": 1,
        "gap_touched_net_pnl_usd": 2.0,
        "clean_path_trade_count": 1,
    }


def _trade(side: str, signal_time: str, pnl: float) -> dict[str, object]:
    return {
        "direction": side,
        "signal_time_utc": signal_time,
        "entry_time_utc": signal_time,
        "exit_time_utc": signal_time,
        "net_pnl_usd": pnl,
        "fees_usd": 0.1,
        "funding_cashflow_usd": 0.0,
        "exit_reason": "max_hold",
    }
