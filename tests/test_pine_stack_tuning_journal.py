"""Append-only storage contracts for four-Pine parameter tuning."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from hypervector.research.pine_stack_tuning import (
    PineStackTuningConfig,
    PineStackTuningResult,
    rank_pine_stack_tuning_results,
)
from hypervector.research.pine_stack_tuning_journal import PineStackTuningJournal


def _result(net_pnl_usd: float) -> PineStackTuningResult:
    """Return one report-only journal fixture."""
    return PineStackTuningResult(
        config=PineStackTuningConfig(10, 5.0, 30),
        symbol="ETH",
        bar_minutes=30,
        signal_count=2,
        completed_trades=1,
        wins=int(net_pnl_usd > 0.0),
        losses=int(net_pnl_usd <= 0.0),
        net_pnl_usd=net_pnl_usd,
        profit_factor=1.2 if net_pnl_usd > 0.0 else 0.8,
        maximum_drawdown_pct=2.0,
        total_fees_usd=3.0,
        funding_cashflow_usd=-0.5,
        liquidations=0,
        monthly_net_pnl_usd={"2025-08": net_pnl_usd},
        trade_records=({"direction": "long", "net_pnl_usd": net_pnl_usd},),
    )


def test_journal_retains_losing_trials_and_rejects_duplicate_run(
    tmp_path: Path,
) -> None:
    """The evidence journal is complete, append-only, and report-only."""
    result = _result(-5.0)
    summaries = rank_pine_stack_tuning_results((result,))
    journal = PineStackTuningJournal(tmp_path / "trials.duckdb")

    journal.write_run(
        run_id="pine-entry-tuning-v1",
        segment="development",
        source_identity={"bars_sha256": "abc"},
        results=(result,),
        summaries=summaries,
    )

    with duckdb.connect(str(journal.path), read_only=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM pine_stack_tuning_trials WHERE net_pnl_usd < 0"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM pine_stack_tuning_trades"
        ).fetchone() == (1,)
    with pytest.raises(ValueError, match="already exists"):
        journal.write_run(
            run_id="pine-entry-tuning-v1",
            segment="development",
            source_identity={"bars_sha256": "abc"},
            results=(result,),
            summaries=summaries,
        )


def test_journal_accepts_frozen_validation_evidence(tmp_path: Path) -> None:
    """The same append-only schema retains untouched validation outcomes."""
    result = _result(5.0)
    journal = PineStackTuningJournal(tmp_path / "validation.duckdb")

    journal.write_run(
        run_id="pine-frozen-validation-v1",
        segment="validation",
        source_identity={"bars_sha256": "abc"},
        results=(result,),
        summaries=rank_pine_stack_tuning_results((result,)),
    )

    with duckdb.connect(str(journal.path), read_only=True) as connection:
        assert connection.execute(
            "SELECT segment FROM pine_stack_tuning_runs"
        ).fetchone() == ("validation",)
