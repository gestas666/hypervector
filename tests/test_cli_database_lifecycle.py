"""CLI boundaries must release SQLite handles on normal and failed queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.runs.db import RunsDB


@pytest.mark.parametrize(
    "command,owner,expected",
    [(["backtest", "report"], "sweep", 0), (["export", "create"], "export", 1)],
)
@pytest.mark.parametrize("failed_query", [False, True])
def test_read_commands_close_their_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    owner: str,
    expected: int,
    failed_query: bool,
) -> None:
    """Even early refusal or a technical query failure must release the handle."""
    database = RunsDB(tmp_path / "trials.db")
    monkeypatch.setattr(f"hypervector.commands.{owner}.RunsDB", lambda _path: database)
    if failed_query:

        def refuse_query(**_kwargs: object) -> list[dict[str, object]]:
            raise sqlite3.OperationalError("injected query failure")

        monkeypatch.setattr(database, "list_trials", refuse_query)
    try:
        argv = ["--data-root", str(tmp_path), *command, "--track", "uptrend"]
        if failed_query:
            with pytest.raises(sqlite3.OperationalError, match="injected"):
                main(argv)
        else:
            assert main(argv) == expected
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            database.init_schema()
    finally:
        database.close()
