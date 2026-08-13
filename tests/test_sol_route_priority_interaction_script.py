"""Tests for the immutable SOL route-priority interaction command."""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome
from hypervector.research.sol_route_priority_interaction import (
    BREAKOUT_STRATEGY,
    HULK_STRATEGY,
    RANGE_STRATEGY,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_route_priority_interaction.py"


def _load() -> ModuleType:
    """Load the command without invoking its entry point."""
    spec = spec_from_file_location("sol_route_priority_interaction_script", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load SOL priority interaction script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade(identity: str, strategy: str, entry: int) -> CohortOutcome:
    """Return one deterministic fixed-cap SOL lifecycle."""
    return CohortOutcome(
        strategy,
        "long",
        SharedTradeOutcome(
            trade_id=identity,
            symbol="SOL",
            entry_time_ms=entry,
            exit_time_ms=entry + 60_000,
            source_equity_usd=500.0,
            margin_fraction=0.03,
            entry_fee_usd=0.03375,
            net_pnl_usd=0.5,
            outcome="maximum_hold",
        ),
    )


def test_parser_and_profile_bind_exact_current_sources() -> None:
    """The command must bind all local sources and exact v25 SOL sizing."""
    module = _load()

    args = module.build_parser().parse_args(["--out", "result.json"])
    profile = module.load_profile_contract(args.config)

    assert args.sol_bars.name == "SOL_1m_365d.parquet"
    assert len(args.hulk_artifact) == 3
    assert len(args.range_artifact) == 12
    assert profile["profile_id"] == (
        "multi_asset_bidirectional_complete_portfolio_canary_v25"
    )
    assert profile["notional_usd"] == 75.0
    assert profile["leverage"] == 5.0
    assert profile["entry_fee_bps"] == 4.5
    assert profile["static_priority"] == [
        BREAKOUT_STRATEGY,
        RANGE_STRATEGY,
        HULK_STRATEGY,
    ]


def test_artifact_is_report_only_and_preserves_source_contract() -> None:
    """The command artifact cannot promote or omit source identity."""
    module = _load()
    outcomes = (
        _trade("hulk", HULK_STRATEGY, 1_000),
        _trade("range", RANGE_STRATEGY, 2_000),
        _trade("breakout", BREAKOUT_STRATEGY, 3_000),
    )
    contract = {
        "profile_id": "fixture",
        "notional_usd": 75.0,
        "leverage": 5.0,
        "entry_fee_bps": 4.5,
        "static_priority": [BREAKOUT_STRATEGY, RANGE_STRATEGY, HULK_STRATEGY],
    }

    artifact = module.build_artifact(
        outcomes,
        profile_contract=contract,
        data_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
        source_summaries={"fixture": {"trades": 3}},
        development_end_ms=10_000,
        opened_final_start_ms=20_000,
        opened_final_end_ms=30_000,
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False
    assert artifact["profile_contract"] == contract
    assert artifact["source_summaries"] == {"fixture": {"trades": 3}}
    assert artifact["source_evidence"] == {"fixture": {"sha256": "0" * 64, "bytes": 1}}


def test_run_rejects_existing_output_before_loading_sources(tmp_path: Path) -> None:
    """An immutable output path must never be overwritten."""
    module = _load()
    output = tmp_path / "existing.json"
    output.touch()

    try:
        module.run(
            argparse.Namespace(
                out=output,
                config=tmp_path / "missing.toml",
                sol_bars=tmp_path / "missing.parquet",
                sol_funding=tmp_path / "missing-funding.parquet",
                hulk_artifact=[],
                range_artifact=[],
            )
        )
    except FileExistsError as exc:
        assert "immutable SOL priority output exists" in str(exc)
    else:
        raise AssertionError("existing immutable SOL priority output was accepted")
