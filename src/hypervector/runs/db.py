"""Local SQLite persistence for trial metrics (SRS_HV1_RUNS_DB)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TrialRow:
    run_id: str
    track: str
    strategy: str
    params: dict[str, Any]
    net_pnl: float
    total_return_pct: float
    sharpe: float
    trade_count: int
    wins: int
    losses: int
    win_pct: float
    max_drawdown: float
    status: str = "ok"
    id: int | None = None
    created_at: str | None = None


class RunsDB:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                track TEXT NOT NULL,
                strategy TEXT NOT NULL,
                params_json TEXT NOT NULL,
                net_pnl REAL NOT NULL,
                total_return_pct REAL NOT NULL,
                sharpe REAL NOT NULL,
                trade_count INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                win_pct REAL NOT NULL,
                max_drawdown REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'ok',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trials_track ON trials(track)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trials_run ON trials(run_id)"
        )
        self._conn.commit()

    def insert_trial(self, trial: TrialRow) -> int:
        created = trial.created_at or datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO trials (
                run_id, track, strategy, params_json,
                net_pnl, total_return_pct, sharpe, trade_count,
                wins, losses, win_pct, max_drawdown, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trial.run_id,
                trial.track,
                trial.strategy,
                json.dumps(trial.params, sort_keys=True),
                float(trial.net_pnl),
                float(trial.total_return_pct),
                float(trial.sharpe),
                int(trial.trade_count),
                int(trial.wins),
                int(trial.losses),
                float(trial.win_pct),
                float(trial.max_drawdown),
                trial.status,
                created,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_trials(
        self, track: str | None = None, run_id: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM trials WHERE 1=1"
        params: list[Any] = []
        if track is not None:
            sql += " AND track = ?"
            params.append(track)
        if run_id is not None:
            sql += " AND run_id = ?"
            params.append(run_id)
        sql += " ORDER BY net_pnl DESC, total_return_pct DESC, id ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def best_by_net_pnl(self, track: str) -> dict[str, Any] | None:
        rows = self.list_trials(track=track)
        ok = [r for r in rows if r["status"] == "ok"]
        return ok[0] if ok else None

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["params"] = json.loads(d.pop("params_json"))
        return d

    def close(self) -> None:
        self._conn.close()
