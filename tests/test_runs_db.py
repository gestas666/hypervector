"""SQLite runs DB + ranking report (SRS_HV1_RUNS_DB, SRS_HV1_RANK_PRIMARY)."""

from __future__ import annotations

from pathlib import Path

from hypervector.report import METRIC_COLUMNS, rank_trials
from hypervector.runs.db import RunsDB, TrialRow


def test_insert_and_list_trials(tmp_path: Path):
    db = RunsDB(tmp_path / "runs" / "hypervector.db")
    tid = db.insert_trial(
        TrialRow(
            run_id="r1",
            track="uptrend",
            strategy="ma_cross_long",
            params={"fast": 5, "slow": 20},
            net_pnl=100.0,
            total_return_pct=1.0,
            sharpe=1.2,
            trade_count=10,
            wins=6,
            losses=4,
            win_pct=60.0,
            max_drawdown=-0.05,
            research_meta={
                "init_cash": 10_000.0,
                "tp_sl_mode": "atr",
                "exits": {"mode": "atr", "sl_pct": 0.01, "rr": 2.0},
            },
        )
    )
    assert tid >= 1
    rows = db.list_trials(track="uptrend")
    assert len(rows) == 1
    assert rows[0]["net_pnl"] == 100.0
    assert rows[0]["params"] == {"fast": 5, "slow": 20}
    assert rows[0]["research_meta"]["init_cash"] == 10_000.0


def test_best_by_net_pnl_orders_primary(tmp_path: Path):
    db = RunsDB(tmp_path / "hv.db")
    for pnl, ret in ((50.0, 2.0), (200.0, 1.0), (100.0, 5.0)):
        db.insert_trial(
            TrialRow(
                run_id="r",
                track="downtrend",
                strategy="ma_cross_short",
                params={"fast": 5, "slow": 20, "tag": pnl},
                net_pnl=pnl,
                total_return_pct=ret,
                sharpe=0.5,
                trade_count=5,
                wins=2,
                losses=3,
                win_pct=40.0,
                max_drawdown=-0.1,
            )
        )
    best = db.best_by_net_pnl("downtrend")
    assert best is not None
    assert best["net_pnl"] == 200.0


def test_rank_trials_primary_net_pnl_then_return():
    rows = [
        {
            "strategy": "a",
            "params": {},
            "net_pnl": 10,
            "total_return_pct": 50,
            "sharpe": 1,
            "trade_count": 1,
            "wins": 1,
            "losses": 0,
            "win_pct": 100,
            "max_drawdown": 0,
            "status": "ok",
        },
        {
            "strategy": "b",
            "params": {},
            "net_pnl": 20,
            "total_return_pct": 1,
            "sharpe": 1,
            "trade_count": 1,
            "wins": 1,
            "losses": 0,
            "win_pct": 100,
            "max_drawdown": 0,
            "status": "ok",
        },
        {
            "strategy": "c",
            "params": {},
            "net_pnl": 20,
            "total_return_pct": 9,
            "sharpe": 1,
            "trade_count": 1,
            "wins": 1,
            "losses": 0,
            "win_pct": 100,
            "max_drawdown": 0,
            "status": "ok",
        },
        {
            "strategy": "err",
            "params": {},
            "net_pnl": 999,
            "total_return_pct": 999,
            "sharpe": 0,
            "trade_count": 0,
            "wins": 0,
            "losses": 0,
            "win_pct": 0,
            "max_drawdown": 0,
            "status": "error",
        },
    ]
    board = rank_trials(rows)
    assert list(board["strategy"])[:3] == ["c", "b", "a"]
    assert board.iloc[-1]["strategy"] == "err"
    for col in (
        "net_pnl",
        "total_return_pct",
        "sharpe",
        "trade_count",
        "wins",
        "losses",
        "win_pct",
        "max_drawdown",
    ):
        assert col in board.columns
    for col in METRIC_COLUMNS:
        assert col in board.columns
