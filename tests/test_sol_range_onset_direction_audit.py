from __future__ import annotations

import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.research.sol_range_onset_direction_audit import (
    audit_sol_range_onset_directions,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_direction_audit.py"


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_direction_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trade(direction: str, pnl: float, *, reason: str = "signal") -> dict[str, object]:
    return {
        "direction": direction,
        "net_pnl_usd": pnl,
        "exit_reason": reason,
    }


def _artifact(
    path: Path,
    *,
    start: str,
    end: str,
    trades: list[dict[str, object]],
) -> Path:
    final_equity = 15_000.0 + sum(float(trade["net_pnl_usd"]) for trade in trades)
    payload = {
        "schema_version": 2,
        "execution_authority": "none",
        "model_authority": "none",
        "initial_equity": 15_000.0,
        "continuous": {
            "start_utc": start,
            "end_utc": end,
            "trials": [
                {
                    "effective_exposure": 0.15,
                    "trial": {
                        "leverage": 5.0,
                        "margin_fraction": 0.03,
                        "stop_bps": 60.0,
                    },
                    "event_replay": {
                        "status": "complete",
                        "failure": None,
                        "completed_trades": len(trades),
                        "initial_equity": 15_000.0,
                        "final_equity": final_equity,
                        "trades": trades,
                    },
                }
            ],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_direction_audit_reports_block_and_leave_one_out_stability(
    tmp_path: Path,
) -> None:
    paths = (
        _artifact(
            tmp_path / "one.json",
            start="2026-01-01T00:00:00Z",
            end="2026-01-02T00:00:00Z",
            trades=[_trade("long", 10.0), _trade("short", -2.0)],
        ),
        _artifact(
            tmp_path / "two.json",
            start="2026-01-03T00:00:00Z",
            end="2026-01-04T00:00:00Z",
            trades=[_trade("long", -3.0), _trade("short", 9.0)],
        ),
        _artifact(
            tmp_path / "three.json",
            start="2026-01-05T00:00:00Z",
            end="2026-01-06T00:00:00Z",
            trades=[_trade("long", 4.0), _trade("short", 1.0)],
        ),
    )

    report = audit_sol_range_onset_directions(paths, expected_trades=6)

    assert report["artifact_count"] == 3
    assert report["trade_count"] == 6
    assert report["runtime_strategy_changed"] is False
    assert report["execution_authority"] == "none"
    long = report["directions"]["long"]
    assert long["trades"] == 3
    assert long["wins"] == 2
    assert long["losses"] == 1
    assert long["net_pnl_usd"] == pytest.approx(11.0)
    assert long["profit_factor"] == pytest.approx(14.0 / 3.0)
    assert long["positive_blocks"] == 2
    assert long["blocks_with_trades"] == 3
    assert long["leave_one_block_out_min_net_pnl_usd"] == pytest.approx(1.0)
    assert long["leave_one_block_out_all_positive"] is True
    assert long["top_1_winner_gross_profit_share"] == pytest.approx(10.0 / 14.0)
    short = report["directions"]["short"]
    assert short["net_pnl_usd"] == pytest.approx(8.0)
    assert short["profit_factor"] == pytest.approx(5.0)
    assert len(report["source_evidence"]) == 3


def test_direction_audit_rejects_censored_end_of_data_trade(tmp_path: Path) -> None:
    path = _artifact(
        tmp_path / "censored.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        trades=[_trade("long", 10.0, reason="end_of_data")],
    )

    with pytest.raises(ValueError, match="end_of_data"):
        audit_sol_range_onset_directions((path,), expected_trades=1)


def test_direction_audit_rejects_overlapping_blocks(tmp_path: Path) -> None:
    first = _artifact(
        tmp_path / "first.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-03T00:00:00Z",
        trades=[_trade("long", 10.0)],
    )
    second = _artifact(
        tmp_path / "second.json",
        start="2026-01-02T00:00:00Z",
        end="2026-01-04T00:00:00Z",
        trades=[_trade("short", 5.0)],
    )

    with pytest.raises(ValueError, match="overlap"):
        audit_sol_range_onset_directions((first, second), expected_trades=2)


def test_direction_audit_enforces_expected_population(tmp_path: Path) -> None:
    path = _artifact(
        tmp_path / "one.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        trades=[_trade("long", 10.0)],
    )

    with pytest.raises(ValueError, match="expected 2 trades, found 1"):
        audit_sol_range_onset_directions((path,), expected_trades=2)


def test_direction_audit_script_writes_report_once(tmp_path: Path) -> None:
    source = _artifact(
        tmp_path / "one.json",
        start="2026-01-01T00:00:00Z",
        end="2026-01-02T00:00:00Z",
        trades=[_trade("long", 10.0), _trade("short", 5.0)],
    )
    output = tmp_path / "report.json"
    module = _load_script()
    arguments = [
        "--replay",
        str(source),
        "--expected-trades",
        "2",
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["trade_count"] == 2
    assert module.main(arguments) == 1
