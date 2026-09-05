"""Tests for the immutable SOL Range Onset profit-lock proxy command."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import duckdb
import pytest

_SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "sol_range_onset_profit_lock_l2_proxy.py"
)
_BASE_MS = 1_767_225_600_000


def _module() -> object:
    spec = spec_from_file_location("sol_range_onset_profit_lock_l2_proxy", _SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trade(side: str, start_ms: int) -> dict[str, object]:
    entry = 100.0 if side == "long" else 101.0
    exit_price = 100.2 if side == "long" else 100.8
    return {
        "direction": side,
        "entry_decision_time_ms": start_ms,
        "entry_snapshot_time_ms": start_ms + 1_000,
        "exit_event_time_ms": start_ms + 4 * 60_000,
        "exit_snapshot_time_ms": start_ms + 4 * 60_000 + 1_000,
        "entry_price": entry,
        "exit_price": exit_price,
        "quantity": 1.0,
        "gross_pnl_usd": 0.2,
        "fees_usd": 0.09,
        "net_pnl_usd": 0.11,
        "exit_reason": "signal",
    }


def _trial(target: float | None, trade: dict[str, object]) -> dict[str, object]:
    return {
        "trial": {
            "stop_bps": 80.0,
            "margin_fraction": 0.15,
            "leverage": 5.0,
            "target_bps": target,
            "initial_equity": 5_000.0,
            "taker_fee_rate": 0.000432,
        },
        "event_replay": {
            "status": "complete",
            "failure": None,
            "initial_equity": 5_000.0,
            "final_equity": 5_000.11,
            "completed_trades": 1,
            "wins": 1,
            "losses": 0,
            "realized_maximum_drawdown_pct": -0.1,
            "total_fees_usd": 0.09,
            "funding_cashflow_usd": 0.0,
            "liquidations": 0,
            "trades": [trade],
        },
    }


def _artifact(path: Path, side: str, start_ms: int, database: Path) -> Path:
    trade = _trade(side, start_ms)
    targets = (None, 25.0, 40.0, 60.0, 80.0, 120.0)
    start = datetime.fromtimestamp(start_ms / 1_000, tz=UTC)
    end = datetime.fromtimestamp((start_ms + 5 * 60_000) / 1_000, tz=UTC)
    payload = {
        "symbol": "SOL",
        "execution_authority": "none",
        "model_authority": "none",
        "trial_surface": "v49-target-exit-posthoc",
        "database_coverage": {"database_path": str(database.resolve())},
        "continuous": {
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "trials": [_trial(target, trade) for target in targets],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _books(path: Path) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE book_snapshots(symbol VARCHAR, ts_exchange_ms BIGINT, "
        "mid_price DOUBLE)"
    )
    for base, prices in (
        (_BASE_MS, ((100.5, 101.0), (100.5, 100.1), (100.5, 100.5))),
        (
            _BASE_MS + 10 * 60_000,
            ((100.5, 100.0), (100.5, 100.9), (100.5, 100.5)),
        ),
    ):
        for minute, values in enumerate(prices, 1):
            for offset in range(0, 60_000, 10_000):
                price = values[1] if offset == 10_000 else values[0]
                connection.execute(
                    "INSERT INTO book_snapshots VALUES (?, ?, ?)",
                    ("SOL", base + minute * 60_000 + offset, price),
                )
    connection.close()


def test_command_publishes_pooled_side_and_block_evidence(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "market.duckdb"
    _books(database)
    first = _artifact(tmp_path / "one.json", "long", _BASE_MS, database)
    second = _artifact(tmp_path / "two.json", "short", _BASE_MS + 10 * 60_000, database)
    output = tmp_path / "report.json"
    args = Namespace(
        artifact=[first, second], database=database, expected_trades=2, output=output
    )

    assert module.run_command(args) == 0
    report = json.loads(output.read_text())
    threshold = report["thresholds_ms"]["15000"]
    assert report["contract"]["execution_authority"] == "none"
    assert report["selection"]["selected_native_lifecycles"] == 2
    assert threshold["overall"]["a25_floor15_trail10"]["trades"] == 2
    assert threshold["by_side"]["long"]["a25_floor15_trail10"]["trades"] == 1
    assert threshold["by_side"]["short"]["a25_floor15_trail10"]["trades"] == 1
    assert report["assessment"]["live_change_proposed"] is False
    assert report["sources"]["database"]["selected_rows_sha256"]


def test_command_rejects_database_identity_mismatch(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "market.duckdb"
    wrong = tmp_path / "wrong.duckdb"
    _books(database)
    _books(wrong)
    artifact = _artifact(tmp_path / "one.json", "long", _BASE_MS, wrong)
    args = Namespace(
        artifact=[artifact],
        database=database,
        expected_trades=1,
        output=tmp_path / "report.json",
    )

    with pytest.raises(ValueError, match="database identity"):
        module.run_command(args)


def test_command_refuses_to_overwrite_immutable_output(tmp_path: Path) -> None:
    module = _module()
    database = tmp_path / "market.duckdb"
    _books(database)
    artifact = _artifact(tmp_path / "one.json", "long", _BASE_MS, database)
    output = tmp_path / "report.json"
    output.write_text("{}", encoding="utf-8")
    args = Namespace(
        artifact=[artifact], database=database, expected_trades=1, output=output
    )

    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def test_command_rejects_database_mutation_during_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    database = tmp_path / "market.duckdb"
    _books(database)
    artifact = _artifact(tmp_path / "one.json", "long", _BASE_MS, database)
    output = tmp_path / "report.json"
    args = Namespace(
        artifact=[artifact], database=database, expected_trades=1, output=output
    )
    original = module._assessment

    def mutate_database(report: Mapping[str, object]) -> dict[str, object]:
        result = original(report)
        database.write_bytes(database.read_bytes() + b"mutated")
        return result

    monkeypatch.setattr(module, "_assessment", mutate_database)

    with pytest.raises(RuntimeError, match="database changed"):
        module.run_command(args)
    assert not output.exists()
