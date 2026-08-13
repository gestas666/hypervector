"""Tests for the multi-asset regime-gate surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "multi_asset_regime_gate_surface.py"


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset regime-gate surface script is missing")
    spec = spec_from_file_location("multi_asset_regime_gate_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_gate_grid_is_fixed_and_includes_baseline_and_htf_variants() -> None:
    """The regime search must be frozen before any result is observed."""
    module = _module()

    gates = module.regime_gate_grid()

    assert len(gates) == 10
    assert len(set(gates)) == len(gates)
    assert gates[0].name == "baseline"
    assert {gate.name for gate in gates} >= {
        "five_min_structural",
        "fifteen_min_non_opposed",
        "fifteen_min_strict",
        "five_structural_fifteen_strict",
        "composite_entry_direction",
    }


def test_range_onset_grid_is_explicitly_separate_and_post_hoc() -> None:
    """Observed range attribution must not be relabeled as a pristine search."""
    module = _module()

    gates = module.range_onset_gate_grid()

    assert len(gates) == 7
    assert gates[0].name == "baseline"
    assert {gate.name for gate in gates} == {
        "baseline",
        "only_5m_range",
        "five_min_range_or_transition",
        "five_min_range_or_breakout",
        "not_five_min_structural",
        "five_min_range_fifteen_non_opposed",
        "five_min_range_fifteen_strict",
    }


def test_range_onset_gate_uses_state_at_the_decision_time() -> None:
    """The exploratory onset gate must retain only causal 5-minute range rows."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    signals = pd.DataFrame(
        {
            "long_entry": True,
            "short_entry": True,
            "long_exit": False,
            "short_exit": False,
            "long_signal_name": "long",
            "short_signal_name": "short",
        },
        index=index,
    )
    regimes = pd.DataFrame(
        {
            "state_5m": ["RANGE", "TRANSITION", "TREND_UP", "RANGE"],
            "context_15m": ["TREND_UP", "RANGE", "TREND_UP", "TREND_DOWN"],
            "structural_direction": [None, None, "long", None],
            "entry_direction": [None, None, "long", None],
            "confidence": [0.2, 0.5, 0.8, 0.2],
        },
        index=index,
    )

    only_range = module.apply_regime_gate(
        signals,
        regimes,
        module.RegimeGate("only_5m_range"),
    )
    range_nonopposed = module.apply_regime_gate(
        signals,
        regimes,
        module.RegimeGate("five_min_range_fifteen_non_opposed"),
    )

    assert only_range["long_entry"].tolist() == [True, False, False, True]
    assert only_range["short_entry"].tolist() == [True, False, False, True]
    assert range_nonopposed["long_entry"].tolist() == [True, False, False, False]
    assert range_nonopposed["short_entry"].tolist() == [False, False, False, True]


def test_apply_gate_preserves_exits_and_uses_explicit_htf_semantics() -> None:
    """A gate may suppress entries but must not interfere with exits."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    signals = pd.DataFrame(
        {
            "long_entry": [True, True, True, True],
            "short_entry": [True, True, True, True],
            "long_exit": [False, True, False, True],
            "short_exit": [True, False, True, False],
            "long_signal_name": "long",
            "short_signal_name": "short",
        },
        index=index,
    )
    regimes = pd.DataFrame(
        {
            "state_5m": ["TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION"],
            "context_15m": ["TREND_UP", "TREND_DOWN", "RANGE", "UNKNOWN"],
            "structural_direction": ["long", "short", None, None],
            "entry_direction": ["long", "short", None, None],
            "confidence": [0.8, 0.8, 0.2, 0.7],
        },
        index=index,
    )

    non_opposed = module.apply_regime_gate(
        signals,
        regimes,
        module.RegimeGate("fifteen_min_non_opposed"),
    )
    strict = module.apply_regime_gate(
        signals,
        regimes,
        module.RegimeGate("fifteen_min_strict"),
    )

    assert non_opposed["long_entry"].tolist() == [True, False, True, True]
    assert non_opposed["short_entry"].tolist() == [False, True, True, True]
    assert strict["long_entry"].tolist() == [True, False, False, False]
    assert strict["short_entry"].tolist() == [False, True, False, False]
    pd.testing.assert_series_equal(strict["long_exit"], signals["long_exit"])
    pd.testing.assert_series_equal(strict["short_exit"], signals["short_exit"])


def test_evaluate_gates_retains_every_trial_and_entry_count() -> None:
    """Every gate must produce a report even when it suppresses all entries."""
    module = _module()
    index = pd.date_range("2026-01-01", periods=60 * 72, freq="1min", tz="UTC")
    close = pd.Series(
        [100.0 + ((position // 360) % 2) * 5.0 for position in range(len(index))],
        index=index,
    )
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
    signals = module.build_trend_signals(bars)
    regimes = module.classify_regimes(bars)
    gates = (module.RegimeGate("baseline"), module.RegimeGate("fifteen_min_strict"))

    results = module.evaluate_gates(
        bars,
        signals,
        regimes,
        symbol="SOL",
        gates=gates,
    )

    assert len(results) == 2
    assert all(result["execution_authority"] == "none" for result in results)
    assert all("retained_entries" in result for result in results)


def test_cli_requires_explicit_chronological_boundaries() -> None:
    """The command must freeze the full chronological evidence contract."""
    module = _module()

    parsed = module.build_parser().parse_args(
        [
            "--symbol",
            "SOL",
            "--bars",
            "bars.parquet",
            "--funding",
            "funding.parquet",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-04-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--output",
            "report.json",
            "--surface",
            "range-onset",
        ]
    )

    assert parsed.symbol == "SOL"
    assert parsed.development_end.isoformat() == "2026-01-28T00:00:00+00:00"
    assert parsed.surface == "range-onset"
