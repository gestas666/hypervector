"""Tests for cross-era SOL stop-distance reconciliation."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.sol_range_onset_stop_reconciliation import (
    reconcile_stop_audits,
)

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "sol_range_onset_stop_reconciliation.py"
)


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_stop_reconciliation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _stop(*, pnl: float, profit: float, loss: float) -> dict[str, object]:
    return {
        "trades": 2,
        "wins": 1,
        "losses": 1,
        "reset_block_net_pnl_usd": pnl,
        "gross_profit_usd": profit,
        "gross_loss_usd": loss,
        "product_equity_usd": 15_000.0 + pnl,
        "product_return_pct": pnl / 150.0,
        "positive_blocks": int(pnl > 0.0),
        "total_fees_usd": 2.0,
        "funding_cashflow_usd": -0.5,
        "liquidations": 0,
        "worst_block_realized_drawdown_pct": -1.0,
        "directions": {
            "long": {
                "trades": 1,
                "wins": 1,
                "losses": 0,
                "net_pnl_usd": profit,
                "profit_factor": None,
            },
            "short": {
                "trades": 1,
                "wins": 0,
                "losses": 1,
                "net_pnl_usd": -loss,
                "profit_factor": 0.0,
            },
        },
    }


def _report(
    path: Path,
    *,
    mode: str,
    start: str,
    end: str,
    sixty_pnl: float,
    eighty_pnl: float,
) -> Path:
    payload: dict[str, object] = {
        "schema_version": 1,
        "mode": mode,
        "execution_authority": "none",
        "model_authority": "none",
        "runtime_strategy_changed": False,
        "stops": {
            "60": _stop(pnl=sixty_pnl, profit=100.0 + sixty_pnl, loss=100.0),
            "80": _stop(pnl=eighty_pnl, profit=100.0 + eighty_pnl, loss=100.0),
        },
        "blocks": [
            {
                "start_utc": start,
                "end_utc": end,
                "trades": 2,
                "stop_60_final_equity_usd": 15_000.0 + sixty_pnl,
                "stop_80_final_equity_usd": 15_000.0 + eighty_pnl,
            }
        ],
    }
    if mode == "sol_range_onset_backward_exact_audit":
        payload["surfaces"] = {
            "public_trade": {"status": "complete"},
            "sampled_mark": {"status": "censored", "censored_blocks": [1]},
        }
    else:
        payload["control_match"] = True
        payload["entry_population_match"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_reconciliation_combines_chronological_paired_stop_evidence(
    tmp_path: Path,
) -> None:
    backward = _report(
        tmp_path / "backward.json",
        mode="sol_range_onset_backward_exact_audit",
        start="2025-01-01T00:00:00Z",
        end="2025-02-01T00:00:00Z",
        sixty_pnl=30.0,
        eighty_pnl=60.0,
    )
    later = _report(
        tmp_path / "later.json",
        mode="sol_range_onset_capacity_shape_paired_audit",
        start="2026-01-01T00:00:00Z",
        end="2026-02-01T00:00:00Z",
        sixty_pnl=90.0,
        eighty_pnl=70.0,
    )

    report = reconcile_stop_audits(backward, later)

    assert report["entry_population_match"] is True
    assert report["trade_count"] == 4
    assert report["block_count"] == 2
    assert report["aggregate_leader_bps"] == 80.0
    assert report["mark_trigger_evidence"] == "censored"
    sixty = report["stops"]["60"]
    eighty = report["stops"]["80"]
    assert sixty["reset_block_net_pnl_usd"] == pytest.approx(120.0)
    assert eighty["reset_block_net_pnl_usd"] == pytest.approx(130.0)
    assert sixty["product_equity_usd"] == pytest.approx(15_120.18)
    assert eighty["product_equity_usd"] == pytest.approx(15_130.28)
    comparison = report["paired_block_comparison"]
    assert comparison["blocks_favoring_60"] == 1
    assert comparison["blocks_favoring_80"] == 1
    assert comparison["ties"] == 0
    assert comparison["exact_sign_flip_p_value_two_sided"] == pytest.approx(1.0)
    assert report["recommendation"]["forward_stop_bps"] == 80.0
    assert report["recommendation"]["confidence"] == "low"


def test_reconciliation_rejects_overlapping_evidence_windows(tmp_path: Path) -> None:
    backward = _report(
        tmp_path / "backward.json",
        mode="sol_range_onset_backward_exact_audit",
        start="2025-01-01T00:00:00Z",
        end="2025-02-01T00:00:00Z",
        sixty_pnl=30.0,
        eighty_pnl=60.0,
    )
    later = _report(
        tmp_path / "later.json",
        mode="sol_range_onset_capacity_shape_paired_audit",
        start="2025-01-15T00:00:00Z",
        end="2025-03-01T00:00:00Z",
        sixty_pnl=90.0,
        eighty_pnl=70.0,
    )

    with pytest.raises(ValueError, match="overlap"):
        reconcile_stop_audits(backward, later)


def test_reconciliation_script_writes_one_immutable_report(tmp_path: Path) -> None:
    backward = _report(
        tmp_path / "backward.json",
        mode="sol_range_onset_backward_exact_audit",
        start="2025-01-01T00:00:00Z",
        end="2025-02-01T00:00:00Z",
        sixty_pnl=30.0,
        eighty_pnl=60.0,
    )
    later = _report(
        tmp_path / "later.json",
        mode="sol_range_onset_capacity_shape_paired_audit",
        start="2026-01-01T00:00:00Z",
        end="2026-02-01T00:00:00Z",
        sixty_pnl=90.0,
        eighty_pnl=70.0,
    )
    output = tmp_path / "reconciliation.json"
    module = _load_script()
    arguments = [
        "--backward-audit",
        str(backward),
        "--later-audit",
        str(later),
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    assert (
        json.loads(output.read_text(encoding="utf-8"))["aggregate_leader_bps"] == 80.0
    )
    assert module.main(arguments) == 1
