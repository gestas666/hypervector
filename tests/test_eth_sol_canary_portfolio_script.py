"""Tests for the bounded ETH/SOL shared-canary replay command."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from hypervector.research.current_cohort_shared_portfolio import (
    CohortTradeSpec,
    adapt_breakout_trades,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade

SCRIPT = Path(__file__).parents[1] / "scripts" / "eth_sol_canary_portfolio.py"


def _load() -> ModuleType:
    """Load the command module without executing its CLI entry point."""
    spec = spec_from_file_location("eth_sol_canary_portfolio_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load ETH/SOL portfolio script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _outcome(
    strategy: str,
    symbol: str,
    side: str,
    entry: str,
    exit_: str,
    net_bps: float,
) -> object:
    """Return one normalized fixed-notional lifecycle."""
    trade = HypeExitTrade(
        side=side,
        signal_time_utc=entry,
        entry_time_utc=entry,
        exit_time_utc=exit_,
        entry_price=100.0,
        exit_price=101.0,
        stop_price=99.0,
        gross_return_bps=net_bps + 13.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=net_bps,
        hold_minutes=60,
        maximum_favorable_excursion_bps=100.0,
        maximum_adverse_excursion_bps=10.0,
        exit_reason="maximum_hold",
    )
    spec = CohortTradeSpec(strategy, symbol, 25.0, 5.0, 4.5)
    return adapt_breakout_trades((trade,), spec)[0]


def test_parser_defaults_to_exact_eth_and_twelve_sol_sources() -> None:
    """The replay must bind the evidence paths used by the survivor audit."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])

    assert args.eth_bars.name == "ETH_1m_365d.parquet"
    assert args.eth_funding.name == "funding.parquet"
    assert len(args.sol_artifact) == 12
    assert args.out == Path("result.json")


def test_artifact_reports_shared_account_and_direction_attribution() -> None:
    """The bounded result must expose each strategy and both directions."""
    module = _load()
    trades = (
        _outcome(
            module.ETH_STRATEGY,
            "ETH",
            "long",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T01:00:00+00:00",
            20.0,
        ),
        _outcome(
            module.SOL_STRATEGY,
            "SOL",
            "short",
            "2026-06-01T00:00:00+00:00",
            "2026-06-01T01:00:00+00:00",
            -10.0,
        ),
    )

    artifact = module.build_artifact(
        trades,
        data_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
        source_summaries={"fixture": {"status": "synthetic"}},
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["contract"]["maximum_positions"] == 2
    assert artifact["input_trade_counts"] == {
        "development": 1,
        "opened_final_60d": 1,
        "purged": 0,
    }
    assert set(artifact["all_available"]["by_strategy_side"]) == {
        f"{module.ETH_STRATEGY}|long",
        f"{module.SOL_STRATEGY}|short",
    }
