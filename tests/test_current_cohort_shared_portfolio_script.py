"""Tests for the immutable current-cohort shared-portfolio report command."""

from __future__ import annotations

from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from hypervector.research.current_cohort_shared_portfolio import (
    CohortTradeSpec,
    adapt_breakout_trades,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade

SCRIPT = Path(__file__).parents[1] / "scripts" / "current_cohort_shared_portfolio.py"


def _load() -> ModuleType:
    """Load the command module without invoking its entry point."""
    spec = spec_from_file_location("current_cohort_shared_portfolio_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load current cohort shared portfolio script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade(entry: str, exit_: str, net_bps: float) -> HypeExitTrade:
    """Build one deterministic unit-notional lifecycle."""
    return HypeExitTrade(
        "long",
        entry,
        entry,
        exit_,
        100.0,
        101.0,
        99.0,
        100.0,
        9.0,
        0.0,
        net_bps,
        60,
        100.0,
        10.0,
        "maximum_hold",
    )


def test_parser_defaults_to_exact_current_local_sources() -> None:
    """The command must be runnable without inventing a remote dependency."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])

    assert args.hype_bars.name == "HYPE_1m_365d.parquet"
    assert args.eth_bars.name == "ETH_1m_365d.parquet"
    assert len(args.hulk_artifact) == 3
    assert args.out == Path("result.json")


def test_artifact_uses_independent_common_purge_partitions() -> None:
    """Development and opened-final reports must each start from $500."""
    module = _load()
    spec = CohortTradeSpec("candidate", "HYPE", 75.0, 5.0, 4.5)
    development = adapt_breakout_trades(
        (_trade("2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 100.0),),
        spec,
    )[0]
    holdout_source = replace(
        _trade("2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00", 100.0),
        entry_time_utc="2026-06-01T00:00:00+00:00",
        exit_time_utc="2026-06-01T01:00:00+00:00",
    )
    holdout = adapt_breakout_trades((holdout_source,), spec)[0]

    artifact = module.build_artifact(
        (development, holdout),
        data_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
        source_summaries={"candidate": {"status": "fixture"}},
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["development"]["performance"]["initial_equity_usd"] == 500.0
    assert artifact["opened_final_60d"]["performance"]["initial_equity_usd"] == 500.0
    assert artifact["input_trade_counts"] == {
        "development": 1,
        "opened_final_60d": 1,
        "purged": 0,
    }
