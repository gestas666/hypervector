"""Tests for pooled SOL range-onset fixed-target diagnostics."""

from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.sol_range_onset_target_exit_audit import (
    audit_target_exit_blocks,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_target_exit_audit.py"


def _script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_target_exit_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trade(side: str, entry: int, exit_ms: int, pnl: float) -> dict[str, object]:
    return {
        "direction": side,
        "entry_decision_time_ms": entry,
        "exit_event_time_ms": exit_ms,
        "exit_reason": "target" if pnl > 0.0 else "stop",
        "net_pnl_usd": pnl,
    }


def _trial(target: float | None, trades: list[dict[str, object]]) -> dict[str, object]:
    pnl = sum(float(trade["net_pnl_usd"]) for trade in trades)
    profits = sum(max(float(trade["net_pnl_usd"]), 0.0) for trade in trades)
    losses = -sum(min(float(trade["net_pnl_usd"]), 0.0) for trade in trades)
    return {
        "trial": {
            "stop_bps": 80.0,
            "margin_fraction": 0.15,
            "leverage": 5.0,
            "target_bps": target,
            "initial_equity": 5_000.0,
            "taker_fee_rate": 0.000432,
        },
        "effective_exposure": 0.75,
        "event_replay": {
            "status": "complete",
            "failure": None,
            "initial_equity": 5_000.0,
            "final_equity": 5_000.0 + pnl,
            "completed_trades": len(trades),
            "wins": sum(float(trade["net_pnl_usd"]) > 0.0 for trade in trades),
            "losses": sum(float(trade["net_pnl_usd"]) < 0.0 for trade in trades),
            "profit_factor": profits / losses if losses else None,
            "realized_maximum_drawdown_pct": -1.0,
            "total_fees_usd": float(len(trades)),
            "funding_cashflow_usd": -0.1 * len(trades),
            "liquidations": 0,
            "trades": trades,
        },
    }


def _artifact(
    path: Path,
    *,
    start: str,
    end: str,
    control: list[dict[str, object]],
    target: list[dict[str, object]],
) -> Path:
    path.write_text(
        json.dumps(
            {
                "symbol": "SOL",
                "execution_authority": "none",
                "model_authority": "none",
                "trial_surface": "v49-target-exit-posthoc",
                "continuous": {
                    "start_utc": start,
                    "end_utc": end,
                    "trials": [
                        _trial(None, control),
                        _trial(25.0, target),
                        _trial(40.0, target),
                        _trial(60.0, target),
                        _trial(80.0, target),
                        _trial(120.0, target),
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_audit_reports_repeatability_sides_and_no_runtime_authority(
    tmp_path: Path,
) -> None:
    first = _artifact(
        tmp_path / "one.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        control=[_trade("long", 1, 2, 10.0), _trade("short", 3, 4, -3.0)],
        target=[_trade("long", 1, 5, 7.0), _trade("short", 3, 6, -2.0)],
    )
    second = _artifact(
        tmp_path / "two.json",
        start="2026-01-03T00:00:00Z",
        end="2026-01-04T00:00:00Z",
        control=[_trade("long", 7, 8, -4.0)],
        target=[_trade("long", 7, 9, 5.0)],
    )

    report = audit_target_exit_blocks((first, second), expected_trades=3)

    assert report["execution_authority"] == "none"
    assert report["runtime_strategy_changed"] is False
    assert report["paired_entry_population"] is True
    control = report["targets"]["native"]
    assert control["pooled_reset_net_usd"] == pytest.approx(3.0)
    assert control["net_excluding_largest_winner_usd"] == pytest.approx(-7.0)
    assert control["positive_blocks"] == 1
    sixty = report["targets"]["60"]
    assert sixty["pooled_reset_net_usd"] == pytest.approx(10.0)
    assert sixty["net_excluding_largest_winner_usd"] == pytest.approx(3.0)
    assert sixty["directions"]["long"]["net_pnl_usd"] == pytest.approx(12.0)
    assert sixty["directions"]["short"]["net_pnl_usd"] == pytest.approx(-2.0)
    assert len(report["source_evidence"]) == 2


def test_audit_rejects_target_that_changes_entry_population(tmp_path: Path) -> None:
    path = _artifact(
        tmp_path / "bad.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        control=[_trade("long", 1, 2, 10.0)],
        target=[_trade("long", 2, 3, 7.0)],
    )

    with pytest.raises(ValueError, match="entry population"):
        audit_target_exit_blocks((path,), expected_trades=1)


def test_audit_rejects_overlapping_blocks(tmp_path: Path) -> None:
    trades = [_trade("long", 1, 2, 10.0)]
    first = _artifact(
        tmp_path / "one.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-03T00:00:00Z",
        control=trades,
        target=trades,
    )
    second = _artifact(
        tmp_path / "two.json",
        start="2026-01-02T00:00:00Z",
        end="2026-01-04T00:00:00Z",
        control=trades,
        target=trades,
    )

    with pytest.raises(ValueError, match="overlap"):
        audit_target_exit_blocks((first, second), expected_trades=2)


def test_script_writes_one_immutable_report(tmp_path: Path) -> None:
    trades = [_trade("long", 1, 2, 10.0)]
    source = _artifact(
        tmp_path / "source.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        control=trades,
        target=trades,
    )
    output = tmp_path / "audit.json"
    module = _script()
    args = ["--artifact", str(source), "--expected-trades", "1", "--out", str(output)]

    assert module.main(args) == 0
    assert (
        json.loads(output.read_text(encoding="utf-8"))["execution_authority"] == "none"
    )
    assert module.main(args) == 1
