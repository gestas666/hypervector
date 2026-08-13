"""Publication boundary for the BTC taker-parity research screen."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import duckdb
import pytest

_SCRIPT = Path("scripts/btc_liquidity_sweep_taker_parity.py")


def _script() -> object:
    spec = spec_from_file_location("btc_liquidity_sweep_taker_parity_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load taker-parity script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_writes_one_immutable_authority_none_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI publishes research evidence without changing runtime authority."""
    script = _script()
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        script,
        "_build_report",
        lambda _: {
            "schema_version": "btc_liquidity_sweep_taker_parity_v1",
            "execution_authority": "none",
            "runtime_strategy_changed": False,
        },
    )
    args = [
        "--development-report",
        "development.json",
        "--forward-report",
        "forward.json",
        "--friction-report",
        "friction.json",
        "--database",
        "market.duckdb",
        "--forward-books",
        "books.jsonl.gz",
        "--forward-prices",
        "prices.parquet",
        "--out",
        str(output),
    ]

    assert script.main(args) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["execution_authority"] == "none"
    assert script.main(args) == 1


def test_friction_uses_exact_btc_long_p99_components(tmp_path: Path) -> None:
    """Target and stop path costs come from the frozen full-roster stress."""
    script = _script()
    path = tmp_path / "friction.json"
    path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "account_value_usd": 500.0,
                        "asset_slots": {
                            "BTC": {
                                "routes": [
                                    {
                                        "strategy_id": "liquidity_sweep_long_1h_stop60_v1",
                                        "target_bps": 26.666666666666668,
                                        "stop_bps": 60.0,
                                        "stacked_target_net_before_funding_bps": 13.3133,
                                        "stacked_p99_stop_loss_bps": 85.2371,
                                    }
                                ]
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    friction = script._friction(path)

    assert friction.win_bps == pytest.approx(13.353366666666668)
    assert friction.loss_bps == pytest.approx(25.2371)


def test_development_book_query_is_half_open_and_digest_bound(tmp_path: Path) -> None:
    """Only the requested BTC event window contributes to causal path evidence."""
    script = _script()
    database = tmp_path / "market.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "CREATE TABLE replay_book_snapshots "
            "(symbol VARCHAR, ts_exchange_ms BIGINT, best_bid DOUBLE, best_ask DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO replay_book_snapshots VALUES (?, ?, ?, ?)",
            [
                ("BTC", 1_000, 99.0, 100.0),
                ("BTC", 2_000, 100.0, 101.0),
                ("ETH", 1_500, 50.0, 51.0),
            ],
        )

    frame, digest = script._development_books(database, 1_000, 2_000)

    assert frame.to_dict("records") == [
        {"ts_ms": 1_000, "best_bid": 99.0, "best_ask": 100.0}
    ]
    assert digest["row_count"] == 1
    assert len(digest["sha256"]) == 64


def test_hourly_archive_paths_require_every_exact_window(tmp_path: Path) -> None:
    """Explicit raw mode fails if any requested immutable hourly book is absent."""
    script = _script()
    start_ms = 1_800_000_000_000
    start = script.pd.Timestamp(start_ms, unit="ms", tz="UTC").floor("1h")
    first = script._hourly_book_path(tmp_path, start)
    second = script._hourly_book_path(tmp_path, start + script.pd.Timedelta(hours=1))
    first.parent.mkdir(parents=True)
    first.touch()

    with pytest.raises(FileNotFoundError, match="hourly book"):
        script._hourly_book_paths(tmp_path, start_ms, start_ms + 7_200_000)

    second.parent.mkdir(parents=True)
    second.touch()
    assert script._hourly_book_paths(tmp_path, start_ms, start_ms + 7_200_000) == (
        first,
        second,
    )
