"""Tests for the immutable SP500 profit-lock L2 proxy command."""

from __future__ import annotations

from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "sp500_profit_lock_l2_proxy.py"


def _module() -> object:
    spec = spec_from_file_location("sp500_profit_lock_l2_proxy_script", _SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trades(path: object) -> None:
    row = {
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "symbol": "xyz:SP500",
        "phase": "validation",
        "friction": "stress",
        "direction": "long",
        "entry_time_utc": "2026-01-01T00:00:01Z",
        "exit_time_utc": "2026-01-01T00:04:00Z",
        "entry_price": 100.0,
        "exit_price": 100.2,
        "quantity": 1.0,
        "gross_pnl_usd": 0.2,
        "fees_usd": 0.09,
    }
    development = {**row, "phase": "development"}
    decoy = {**row, "strategy_id": "different_provider"}
    pd.DataFrame((row, development, decoy)).to_parquet(path, index=False)


def _books(path: object) -> None:
    start = 1_767_225_600_000
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE book_snapshots(symbol VARCHAR, ts_exchange_ms BIGINT, mid_price DOUBLE)"
    )
    for minute, values in enumerate(
        ((100.5, 101.0), (100.5, 100.1), (100.5, 100.5)), 1
    ):
        for offset in range(0, 60_000, 10_000):
            price = values[1] if offset == 10_000 else values[0]
            connection.execute(
                "INSERT INTO book_snapshots VALUES (?, ?, ?)",
                ("xyz:SP500", start + minute * 60_000 + offset, price),
            )
    connection.close()


def test_command_filters_exact_contract_and_writes_immutable_evidence(tmp_path) -> None:
    module = _module()
    trades = tmp_path / "trades.parquet"
    database = tmp_path / "market.duckdb"
    output = tmp_path / "report.json"
    _trades(trades)
    _books(database)
    args = Namespace(trades=trades, database=database, output=output)

    assert module.run_command(args) == 0
    report = json.loads(output.read_text())
    assert report["selection"] == {
        "strategy_id": "hip3_breakout_pressure_sp500_spcx_bidirectional_v1",
        "symbol": "xyz:SP500",
        "friction": "stress",
        "phases": ["development", "validation"],
        "selected_lifecycles": 2,
    }
    assert (
        report["thresholds_ms"]["15000"]["by_phase"]["validation"][
            "a25_floor15_trail10"
        ]["triggered"]
        == 1
    )
    assert report["sources"]["trades"]["sha256"]
    assert report["sources"]["database"]["selected_rows_sha256"]

    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def test_assessment_rejects_live_lock_and_withholds_validation_only_winner() -> None:
    module = _module()
    negative = {"estimated_net_ex_funding_usd": -0.1, "profit_factor": 0.9}
    positive = {"estimated_net_ex_funding_usd": 0.2, "profit_factor": 1.4}
    policies = ("a25_floor15_trail10", "a40_floor15_trail20")
    report = {
        "thresholds_ms": {
            "15000": {
                "by_phase": {
                    "development": {
                        **{policy: negative for policy in policies},
                        "a60_floor15_trail30": negative,
                    },
                    "validation": {
                        **{policy: negative for policy in policies},
                        "a60_floor15_trail30": positive,
                    },
                }
            }
        }
    }

    assert module._assessment(report) == {
        "overall_disposition": "no_exit_policy_change",
        "a25_floor15_trail10": "rejected_validation_after_cost_negative",
        "a40_floor15_trail20": "rejected_validation_after_cost_negative",
        "a60_floor15_trail30": "withheld_no_cross_partition_support",
        "execution_effect": "report_only",
    }
