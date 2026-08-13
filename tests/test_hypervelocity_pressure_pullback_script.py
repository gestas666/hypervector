"""Command-contract tests for the pressure-pullback replay script."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


def _load_script() -> ModuleType:
    path = Path("scripts/hypervelocity_pressure_pullback_replay.py")
    spec = importlib.util.spec_from_file_location("pressure_pullback_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pressure-pullback replay script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_regime_base_skips_hard_bbwp_transforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical mode must retain runtime structure plus breakout confirmation."""
    module = _load_script()
    canonical = pd.DataFrame(
        {
            "entry_direction": [None],
            "structural_direction": ["long"],
            "state_1m": ["TREND_UP"],
            "state_5m": ["BREAKOUT"],
            "reason": ["5m_breakout_awaiting_1m_confirmation"],
        },
        index=pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC"),
    )
    monkeypatch.setattr(
        module,
        "load_hypervelocity_profile",
        lambda _path: SimpleNamespace(regime_config=object()),
    )
    monkeypatch.setattr(
        module,
        "classify_multitimeframe",
        lambda _bars, config: canonical.copy(),
    )

    result = module._base_decisions(
        canonical,
        Path("config.toml"),
        "canonical-breakout-confirmed",
    )

    assert result["entry_direction"].tolist() == ["long"]
    assert "bbwp_5m_hard_range" not in result


def test_parser_accepts_canonical_regime_base() -> None:
    """The selected regime base must be explicit in the replay command."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--regime-base",
            "canonical-breakout-confirmed",
            "--out",
            "report.json",
        ]
    )

    assert args.regime_base == "canonical-breakout-confirmed"


def test_parser_accepts_source_grounded_margin_stop() -> None:
    """The inferred loss limit must be explicit and reportable."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--fixed-margin-stop-pct",
            "2",
            "--out",
            "report.json",
        ]
    )

    config = module._maker_replay_config(args)

    assert args.fixed_margin_stop_pct == 2.0
    assert config.fixed_margin_stop_pct == 2.0


def test_parser_reports_fresh_opposed_confirmation_candidate() -> None:
    """The transition delay is opt-in and encoded in replay identity."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--regime-base",
            "canonical-breakout-confirmed",
            "--pressure-timing",
            "first-opposed-snapshot",
            "--fresh-opposed-confirmation-bars",
            "1",
            "--out",
            "report.json",
        ]
    )

    assert args.fresh_opposed_confirmation_bars == 1
    assert module._candidate_identity(args).endswith(
        "first_opposed_obi5_snapshot_fresh_opposed_confirm_1bar"
    )
    assert module._replay_contract(args)["fresh_opposed_confirmation_bars"] == 1


def test_parser_reports_configured_counter_context_strength_candidate() -> None:
    """The configured percentile threshold is explicit in candidate identity."""
    module = _load_script()
    args = module._parser().parse_args(
        [
            "--bars",
            "bars.parquet",
            "--positions",
            "positions.csv",
            "--config",
            "config.toml",
            "--start",
            "2026-04-28T00:00:00Z",
            "--end",
            "2026-07-27T00:00:00Z",
            "--price-context",
            "prices.parquet",
            "--funding-context",
            "funding.parquet",
            "--regime-base",
            "canonical-breakout-confirmed",
            "--pressure-timing",
            "first-opposed-snapshot",
            "--minimum-opposed-strength-percentile",
            "50",
            "--out",
            "report.json",
        ]
    )

    assert args.minimum_opposed_strength_percentile == 50.0
    assert module._candidate_identity(args).endswith(
        "first_opposed_obi5_snapshot_opposed_strength_ge_50pct"
    )
    assert module._replay_contract(args)["minimum_opposed_strength_percentile"] == 50.0
