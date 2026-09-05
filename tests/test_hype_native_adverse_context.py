"""Tests for the predeclared HYPE 15-minute context diagnostic."""

from importlib import import_module
from importlib.util import find_spec

import pandas as pd
import pytest


def _market() -> pd.DataFrame:
    """Build three causal days with mixed 15-minute long-entry contexts."""
    index = pd.date_range("2026-01-01", periods=3 * 1_440, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.15,
            "low": 99.85,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "BREAKOUT",
            "state_1m": "RANGE",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    for ordinal, position in enumerate(range(0, len(frame) - 121, 240)):
        frame.iloc[position, frame.columns.get_loc("entry_side")] = "long"
        context = "TREND_DOWN" if ordinal % 2 == 0 else "RANGE"
        frame.iloc[position, frame.columns.get_loc("context_15m")] = context
        frame.iloc[position + 60, frame.columns.get_loc("entry_side")] = "short"
    return frame


def test_adverse_context_comparison_module_exists() -> None:
    """The report-only diagnostic has a dedicated implementation boundary."""
    assert find_spec("hypervector.research.hype_native_adverse_context") is not None


def test_censor_removes_only_trend_down_long_entries() -> None:
    """The challenger retains every short exit signal and other long onsets."""
    module = import_module("hypervector.research.hype_native_adverse_context")
    censor = getattr(module, "censor_adverse_long_entries", None)
    assert callable(censor)
    market = pd.DataFrame(
        {
            "entry_side": ["long", "short", "long", "short"],
            "context_15m": ["TREND_DOWN", "TREND_DOWN", "RANGE", "TREND_UP"],
        },
        index=pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC"),
    )

    censored, count = censor(market)

    assert censored["entry_side"].tolist() == [None, "short", "long", "short"]
    assert count == 1
    assert market["entry_side"].tolist() == ["long", "short", "long", "short"]


def test_comparison_keeps_short_exit_authority_and_reports_folds() -> None:
    """The one-variable replay reports both arms without execution authority."""
    module = import_module("hypervector.research.hype_native_adverse_context")
    build = getattr(module, "build_hype_native_adverse_context_comparison", None)
    assert callable(build)

    report = build(_market(), holdout_days=1, fold_count=3)

    development = report["development"]
    control = development["control_long_only"]
    challenger = development["censor_trend_down_long"]
    assert report["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert control["entry_sides"] == ["long"]
    assert challenger["entry_sides"] == ["long"]
    assert control["policy_id"] == "hype_native_long_control"
    assert challenger["policy_id"] == "hype_native_long_censor_trend_down_15m"
    assert challenger["censored_long_signals"] > 0
    assert challenger["retained_short_signals"] == control["retained_short_signals"]
    assert challenger["exit_reasons"]["opposite_strategy_intent"] > 0
    assert len(control["chronological_fold_net_bps"]) == 3
    assert sum(control["chronological_fold_net_bps"]) == pytest.approx(
        control["net_return_bps"]
    )


def test_comparison_rejects_missing_context_contract() -> None:
    """The challenger cannot silently invent absent completed 15m context."""
    module = import_module("hypervector.research.hype_native_adverse_context")

    with pytest.raises(ValueError, match="missing columns.*context_15m"):
        module.censor_adverse_long_entries(pd.DataFrame({"entry_side": ["long"]}))


def test_comparison_rejects_invalid_fold_count() -> None:
    """Chronological attribution requires at least two folds."""
    module = import_module("hypervector.research.hype_native_adverse_context")

    with pytest.raises(ValueError, match="fold_count must be at least two"):
        module.build_hype_native_adverse_context_comparison(
            _market(),
            holdout_days=1,
            fold_count=1,
        )
