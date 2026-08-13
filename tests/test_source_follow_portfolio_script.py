"""CLI contract for queue-aware source-follow portfolio evidence."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _module() -> ModuleType:
    path = Path("scripts/hypervelocity_source_portfolio_replay.py")
    spec = importlib.util.spec_from_file_location("source_portfolio_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load source portfolio script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_baseline_summary_reconstructs_net_profit_factor() -> None:
    module = _module()
    replay = {
        "completed_trades": 2,
        "liquidations": 1,
        "final_equity": 90.0,
        "maximum_drawdown_pct": -20.0,
        "trades": [{"net_pnl": 20.0}, {"net_pnl": -30.0}],
    }

    summary = module.baseline_summary(replay)

    assert summary["profit_factor"] == 2.0 / 3.0
    assert summary["net_pnl"] == -10.0


def test_research_risk_arguments_preserve_eight_percent_margin_target() -> None:
    """Changing leverage must move price distance, not gross margin return."""
    module = _module()
    args = module.parse_args(
        [
            "--database",
            "market.duckdb",
            "--artifact",
            "source.json",
            "--prices",
            "prices.parquet",
            "--funding",
            "funding.parquet",
            "--leverage",
            "25",
            "--margin-fraction",
            "0.4",
            "--minimum-signal-range-bps",
            "12",
            "--out",
            "result.json",
        ]
    )

    config = module.replay_config(args)

    assert config.leverage == 25.0
    assert config.margin_fraction == 0.4
    assert config.target_price_fraction == 8.0 / 25.0 / 100.0
    assert args.minimum_signal_range_bps == 12.0
