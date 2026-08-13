"""Command tests for the immutable range-onset context audit."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/range_onset_context_challenger.py")


def _module() -> ModuleType:
    if not _SCRIPT.is_file():
        pytest.fail("range-onset context challenger script is missing")
    spec = spec_from_file_location("range_onset_context_challenger_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPT.parent.resolve()))
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPT.parent.resolve()))
    return module


def test_artifact_declares_fixed_report_only_hypotheses() -> None:
    """The bounded audit must not become a strategy or balance gate."""
    module = _module()

    report = module._artifact("ETH", {"bar_rows": 10}, {"continuous": {}})

    assert report["execution_authority"] == "none"
    assert report["model_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["automatic_execution_gate"] is False
    assert report["balance_gate"] is False
    assert report["candidate_count"] == 4
    assert tuple(report["candidate_definitions"]) == (
        "current_contract",
        "component_alignment_gte_neg05",
        "dual_mtf_not_opposed",
        "state_1m_not_opposed",
    )


def test_candidate_summary_retains_trade_rows_and_directional_losses() -> None:
    """Sparse and losing evidence must remain inspectable trade by trade."""
    module = _module()
    report = {
        "initial_equity": 100.0,
        "final_equity": 99.0,
        "net_pnl_usd": -1.0,
        "profit_factor": 0.0,
        "limitations": ("bar-only",),
        "trades": (
            {
                "direction": "long",
                "signal_time_utc": "2026-01-01T00:00:00+00:00",
                "entry_time_utc": "2026-01-01T00:01:00+00:00",
                "exit_time_utc": "2026-01-01T00:02:00+00:00",
                "net_pnl_usd": -1.0,
                "fees_usd": 0.1,
                "funding_cashflow_usd": 0.0,
                "exit_reason": "stop",
            },
        ),
    }

    summary = module._candidate_summary("current_contract", report)

    assert summary["candidate_id"] == "current_contract"
    assert summary["metrics"]["net_pnl_usd"] == -1.0
    assert summary["by_side"]["long"]["losses"] == 1
    assert summary["by_side"]["short"]["trades"] == 0
    assert summary["trades"][0]["exit_reason"] == "stop"


def test_retention_summary_counts_excluded_losses_and_lost_winners() -> None:
    """A better aggregate must disclose whether it discarded rare winners."""
    module = _module()
    baseline = {
        "trades": [
            _trade("long", "00:00", 5.0),
            _trade("short", "01:00", 2.0),
            _trade("long", "02:00", -3.0),
            _trade("short", "03:00", -1.0),
        ]
    }
    candidate = {
        "trades": [
            _trade("long", "00:00", 4.0),
            _trade("short", "03:00", -1.5),
        ]
    }

    retention = module._retention_summary(baseline, candidate)

    assert retention["baseline_winners"] == 2
    assert retention["retained_baseline_winners"] == 1
    assert retention["excluded_baseline_winners"] == 1
    assert retention["baseline_losses"] == 2
    assert retention["excluded_baseline_losses"] == 1
    assert retention["retained_baseline_gross_profit_pct"] == pytest.approx(
        5.0 / 7.0 * 100.0
    )
    assert retention["excluded_baseline_gross_loss_pct"] == pytest.approx(75.0)


def _trade(side: str, minute: str, net_pnl_usd: float) -> dict[str, object]:
    return {
        "direction": side,
        "signal_time_utc": f"2026-01-01T{minute}:00+00:00",
        "net_pnl_usd": net_pnl_usd,
    }


def test_parser_requires_explicit_chronological_evidence_boundaries() -> None:
    """No default date window may silently change the experiment."""
    module = _module()

    parsed = module.build_parser().parse_args(
        [
            "--symbol",
            "ETH",
            "--bars",
            "eth.parquet",
            "--funding",
            "funding.parquet",
            "--development-start",
            "2025-07-28T00:00:00Z",
            "--development-end",
            "2026-01-28T00:00:00Z",
            "--validation-end",
            "2026-05-28T00:00:00Z",
            "--pseudo-holdout-end",
            "2026-07-28T00:00:00Z",
            "--output",
            "report.json",
        ]
    )

    assert parsed.symbol == "ETH"
    assert parsed.development_start.isoformat() == "2025-07-28T00:00:00+00:00"
