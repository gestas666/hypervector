"""Contract tests for the complete HYPE-native exit comparison."""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
import json
from pathlib import Path

import pandas as pd


_ROOT = Path(__file__).parents[1]
_LINEAGE = (
    _ROOT / "docs/research-journal/v54-hype-native-exit-lineage-reconciliation-v1.json"
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=4 * 24 * 60, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "TREND_UP",
            "state_1m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    market.loc[index[0], "entry_side"] = "long"
    market.loc[index[60], "entry_side"] = "short"
    market.loc[index[4_800], "entry_side"] = "long"
    return market


def test_complete_contract_closes_both_policies_on_opposite_native_onset() -> None:
    """The v54 comparison must include its configured opposite-onset exit."""
    module_name = "hypervector.research.hype_native_exit_comparison"
    assert find_spec(module_name) is not None
    builder = import_module(module_name).build_hype_native_exit_comparison
    report = builder(_market(), holdout_days=1)

    assert report["execution_authority"] == "none"
    assert report["contract"]["opposite_native_onset_exit"] is True
    assert report["development"]["fixed_8h"]["exit_reasons"] == {
        "opposite_strategy_intent": 1
    }
    assert report["development"]["supported_extension"]["exit_reasons"] == {
        "opposite_strategy_intent": 1
    }


def test_historical_lineage_describes_all_seven_exit_outcomes_exactly() -> None:
    """The journal must not overcount near-eight-hour maximum-hold winners."""
    payload = json.loads(_LINEAGE.read_text())
    finding = payload["evidence"][0]["finding"]

    assert "four maximum-hold winners closed near eight hours" in finding
    assert "two maximum-hold winners extended beyond eight hours" in finding
    assert "one protective-stop loss" in finding
