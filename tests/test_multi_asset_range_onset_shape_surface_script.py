"""Tests for the post-hoc range-onset exit-shape surface."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "multi_asset_range_onset_shape_surface.py"
)


def _module() -> ModuleType:
    if not SCRIPT.is_file():
        pytest.fail("multi-asset range-onset shape surface script is missing")
    spec = spec_from_file_location("multi_asset_range_onset_shape_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPT.parent))
    return module


def test_shape_grid_is_fixed_complete_and_contains_baseline() -> None:
    """The local exit neighborhood must be declared before inspection."""
    module = _module()

    shapes = module.onset_shape_grid()

    assert len(shapes) == 16
    assert len(set(shapes)) == len(shapes)
    assert module.OnsetShape(60.0, 48) in shapes
    assert {shape.stop_bps for shape in shapes} == {40.0, 60.0, 80.0, 100.0}
    assert {shape.max_hold_hours for shape in shapes} == {24, 48, 96, None}


def test_shape_config_is_low_exposure_and_preserves_price_stop() -> None:
    """Shape robustness must remain separate from leverage optimization."""
    module = _module()

    config = module.onset_shape_config(
        module.OnsetShape(80.0, 96),
        symbol="SOL",
    )

    assert config.margin_fraction == pytest.approx(0.10)
    assert config.leverage == pytest.approx(5.0)
    assert config.stop_margin_pct == pytest.approx(4.0)
    assert config.max_hold_bars == 96 * 60


def test_evaluate_shapes_retains_every_requested_trial() -> None:
    """A losing exit shape must remain in the artifact."""
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
    signals = module.build_range_onset_signals(bars)
    shapes = (module.OnsetShape(40.0, 24), module.OnsetShape(100.0, None))

    results = module.evaluate_onset_shapes(
        bars,
        signals,
        symbol="SOL",
        shapes=shapes,
    )

    assert len(results) == 2
    assert results[0]["shape"] == {"stop_bps": 40.0, "max_hold_hours": 24}
    assert results[1]["execution_authority"] == "none"


def test_trial_summary_separates_long_and_short_outcomes() -> None:
    """Aggregate results must not conceal a failing directional leg."""
    module = _module()
    report = {
        "net_pnl_usd": 2.0,
        "profit_factor": 1.2,
        "trades": (
            {
                "direction": "long",
                "net_pnl_usd": 5.0,
                "fees_usd": 1.0,
                "funding_cashflow_usd": -0.5,
                "exit_reason": "max_hold",
            },
            {
                "direction": "short",
                "net_pnl_usd": -3.0,
                "fees_usd": 0.8,
                "funding_cashflow_usd": 0.2,
                "exit_reason": "stop",
            },
        ),
        "limitations": ("bar-only",),
    }

    summary = module._trial_summary(module.OnsetShape(60.0, 48), report)

    assert summary["by_side"]["long"] == {
        "trades": 1,
        "wins": 1,
        "losses": 0,
        "net_pnl_usd": 5.0,
        "profit_factor": None,
        "fees_usd": 1.0,
        "funding_cashflow_usd": -0.5,
        "exit_reasons": {"max_hold": 1},
    }
    assert summary["by_side"]["short"]["profit_factor"] == 0.0
    assert summary["by_side"]["short"]["losses"] == 1


def test_trial_summary_rejects_unknown_trade_direction() -> None:
    """Malformed evidence must not disappear from directional attribution."""
    module = _module()
    report = {
        "trades": (
            {
                "direction": "flat",
                "net_pnl_usd": 0.0,
                "fees_usd": 0.0,
                "funding_cashflow_usd": 0.0,
                "exit_reason": "end_of_data",
            },
        ),
        "limitations": (),
    }

    with pytest.raises(ValueError, match="direction must be long or short"):
        module._trial_summary(module.OnsetShape(60.0, 48), report)


def test_cli_requires_explicit_chronological_boundaries() -> None:
    """Every evidence boundary must be explicit."""
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
        ]
    )

    assert parsed.symbol == "SOL"
    assert parsed.validation_end.isoformat() == "2026-04-28T00:00:00+00:00"
