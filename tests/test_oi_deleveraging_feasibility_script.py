"""Command-level isolation tests for the frozen OI feasibility screen."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd


_SCRIPT = Path("scripts/oi_deleveraging_feasibility.py")


def _module() -> object:
    spec = spec_from_file_location("oi_deleveraging_feasibility_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flat_minutes(start: datetime, count: int) -> pd.DataFrame:
    minute = pd.date_range(start, periods=count, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "minute": minute,
            "close": 100.0,
            "trade_imbalance": 0.0,
            "book_imbalance": 0.0,
            "open_interest": 1_000.0,
            "first_bid": 99.99,
            "first_ask": 100.01,
            "first_quote_at": minute + pd.Timedelta(seconds=1),
        }
    )


def test_failed_development_never_loads_confirmation() -> None:
    module = _module()
    calls: list[tuple[str, datetime, datetime]] = []

    def loader(
        _database: Path, symbol: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        calls.append((symbol, start, end))
        return _flat_minutes(start, int((end - start).total_seconds() // 60))

    result = module._run_evaluations(Path("unused.duckdb"), loader=loader)

    assert result["development"].assessment["passed"] is False
    assert result["confirmation"] is None
    assert result["confirmation_status"] == "withheld_not_evaluated"
    assert [item[0] for item in calls] == ["BTC", "SOL"]
    assert all(item[1] == datetime(2026, 8, 4, 1, 5, tzinfo=UTC) for item in calls)
    expected_end = datetime(2026, 8, 8, 8, 50, tzinfo=UTC)
    assert all(item[2] == expected_end for item in calls)


def test_parser_requires_explicit_database_and_output() -> None:
    module = _module()

    parser = module.build_parser()
    args = parser.parse_args(["--database", "events.duckdb", "--out", "result.json"])

    assert args.database == Path("events.duckdb")
    assert args.out == Path("result.json")
