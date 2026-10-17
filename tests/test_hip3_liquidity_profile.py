"""Tests for point-in-time HIP-3 visible-liquidity profiling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import duckdb
import pytest

from hypervector.cli import main
from hypervector.research.hip3_fee_model import Hip3FeeInputs
from hypervector.research.hip3_liquidity_profile import build_liquidity_profile


def _database(
    path: Path,
    *,
    market_family: str = "hip3",
    book_only: bool = True,
    symbol: str = "xyz:SPCX",
) -> None:
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE archive_bundles (
            bundle_id VARCHAR,
            symbol VARCHAR,
            start_utc TIMESTAMPTZ,
            end_utc TIMESTAMPTZ,
            book_rows BIGINT
        );
        CREATE TABLE archive_bundle_provenance (
            bundle_id VARCHAR,
            market_family VARCHAR,
            book_only BOOLEAN,
            book_source VARCHAR
        );
        CREATE TABLE book_snapshots (
            symbol VARCHAR,
            ts_exchange_ms BIGINT,
            ts_utc TIMESTAMPTZ,
            mid_price DOUBLE,
            spread_bps DOUBLE,
            bids STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[],
            asks STRUCT(n INTEGER, px DOUBLE, sz DOUBLE)[]
        );
        CREATE TABLE public_trades (symbol VARCHAR);
        CREATE VIEW replay_book_snapshots AS SELECT * FROM book_snapshots;
        CREATE VIEW replay_public_trades AS SELECT * FROM public_trades;
        """
    )
    start = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
    connection.execute(
        "INSERT INTO archive_bundles VALUES (?, ?, ?, ?, ?)",
        ["bundle-1", symbol, start, start + timedelta(minutes=15), 4],
    )
    connection.execute(
        "INSERT INTO archive_bundle_provenance VALUES (?, ?, ?, ?)",
        ["bundle-1", market_family, book_only, "0xarchive_hyperliquid_hip3_l2"],
    )
    rows = (
        _book(start + timedelta(seconds=5), 99.0, 101.0, symbol),
        _book(start + timedelta(seconds=20), 98.0, 102.0, symbol),
        _book(start + timedelta(minutes=5, seconds=20), 99.0, 101.0, symbol),
        _book(start + timedelta(minutes=10, seconds=10), 99.0, 101.0, symbol),
    )
    connection.executemany(
        "INSERT INTO book_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)", rows
    )
    connection.close()


def _book(
    timestamp: datetime,
    bid: float,
    ask: float,
    symbol: str = "xyz:SPCX",
) -> tuple[object, ...]:
    return (
        symbol,
        int(timestamp.timestamp() * 1_000),
        timestamp,
        (bid + ask) / 2.0,
        (ask / bid - 1.0) * 10_000.0,
        [{"n": 1, "px": bid, "sz": 1.0}],
        [{"n": 1, "px": ask, "sz": 1.0}],
    )


def test_profile_uses_first_timely_snapshot_and_finite_depth(tmp_path: Path) -> None:
    """Sampling must be causal, delay-bounded, and non-extrapolating."""
    database = tmp_path / "hip3.duckdb"
    _database(database)

    profile = build_liquidity_profile(
        database,
        symbol="xyz:SPCX",
        notionals_usd=(50.0, 200.0),
        sample_interval_minutes=5,
        maximum_boundary_delay_ms=15_000,
    )

    assert profile.coverage.expected_boundaries == 3
    assert profile.coverage.observed_boundaries == 3
    assert profile.coverage.timely_samples == 2
    assert profile.coverage.late_boundaries == 1
    assert profile.coverage.missing_boundaries == 0
    assert profile.spread_bps.p50 == pytest.approx(202.020202)
    small, large = profile.notionals
    assert small.notional_usd == 50.0
    assert small.both_complete_rate == 1.0
    assert small.round_trip_visible_cost_bps.p50 == pytest.approx(200.0)
    assert large.both_complete_rate == 0.0
    assert large.round_trip_visible_cost_bps.count == 0
    assert profile.public_trade_rows == 0
    assert profile.fee_status == "unresolved_excluded"


def test_skhx_profile_uses_korean_scheduled_session_labels(tmp_path: Path) -> None:
    database = tmp_path / "skhx.duckdb"
    _database(database, symbol="xyz:SKHX")

    profile = build_liquidity_profile(
        database,
        symbol="xyz:SKHX",
        notionals_usd=(50.0,),
    )

    sessions = {item.session: item.samples for item in profile.sessions}
    assert set(sessions) == {
        "scheduled_external_reference",
        "scheduled_internal_or_closed",
    }
    assert sessions["scheduled_internal_or_closed"] == 2
    assert "scheduled_session_is_not_observed_oracle_mode" in profile.limitations


def test_profile_rejects_non_hip3_provenance(tmp_path: Path) -> None:
    """A core-market bundle must not be accepted as HIP-3 evidence."""
    database = tmp_path / "wrong-family.duckdb"
    _database(database, market_family="core")

    with pytest.raises(ValueError, match="HIP-3 provenance"):
        build_liquidity_profile(
            database,
            symbol="xyz:SPCX",
            notionals_usd=(50.0,),
        )


def test_profile_accepts_checksum_paired_hip3_provenance(tmp_path: Path) -> None:
    """Paired book/trade ingestion is at least as attributable as books-only."""
    database = tmp_path / "paired.duckdb"
    _database(database, book_only=False)

    profile = build_liquidity_profile(
        database,
        symbol="xyz:SPCX",
        notionals_usd=(50.0,),
    )

    assert profile.coverage.archive_bundles == 1
    assert profile.coverage.archive_book_rows == 4


def test_profile_adds_explicit_taker_fee_sensitivity(tmp_path: Path) -> None:
    """Fee-inclusive costs must use only an explicit evidenced formula input."""
    database = tmp_path / "fees.duckdb"
    _database(database)
    fee_inputs = Hip3FeeInputs(
        account_maker_rate=0.00015,
        account_taker_rate=0.00045,
        active_referral_discount=0.04,
        deployer_fee_scale=1.0,
        growth_mode=True,
        aligned_quote=False,
        aligned_quote_status="unresolved_conservative_false",
        evidence_label="fixture",
    )

    profile = build_liquidity_profile(
        database,
        symbol="xyz:SPCX",
        notionals_usd=(50.0,),
        fee_inputs=fee_inputs,
    )

    assert profile.fee_status == "modeled_current_inputs"
    assert profile.fees is not None
    assert profile.fees.round_trip_taker_fee_bps == pytest.approx(1.728)
    total = profile.notionals[0].round_trip_taker_total_cost_bps
    assert total.p50 == pytest.approx(201.728)


@pytest.mark.parametrize("notionals", [(), (0.0,), (25.0, 25.0)])
def test_profile_rejects_invalid_notional_contract(
    tmp_path: Path,
    notionals: tuple[float, ...],
) -> None:
    """Requested liquidity sizes must be unique finite positive values."""
    database = tmp_path / "invalid.duckdb"
    _database(database)

    with pytest.raises(ValueError, match="notionals_usd"):
        build_liquidity_profile(
            database,
            symbol="xyz:SPCX",
            notionals_usd=notionals,
        )


def test_cli_writes_report_only_profile_without_overwriting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI must persist evidence once and expose no execution authority."""
    database = tmp_path / "cli.duckdb"
    output = tmp_path / "profile.json"
    _database(database)
    arguments = [
        "--data-root",
        str(tmp_path),
        "db",
        "hip3-liquidity",
        "--database",
        str(database),
        "--symbol",
        "xyz:SPCX",
        "--notional-usd",
        "50",
        "--account-maker-rate",
        "0.00015",
        "--account-taker-rate",
        "0.00045",
        "--active-referral-discount",
        "0.04",
        "--deployer-fee-scale",
        "1",
        "--growth-mode",
        "--no-aligned-quote",
        "--aligned-quote-status",
        "unresolved_conservative_false",
        "--fee-evidence-label",
        "fixture",
        "--out",
        str(output),
    ]

    assert main(arguments) == 0
    rendered = json.loads(capsys.readouterr().out)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert rendered == persisted
    assert rendered["report_only"] is True
    assert rendered["execution_authority"] == "none"
    assert rendered["profile"]["symbol"] == "xyz:SPCX"
    assert rendered["profile"]["fee_status"] == "modeled_current_inputs"
    assert rendered["profile"]["fees"]["round_trip_taker_fee_bps"] == pytest.approx(
        1.728
    )
    assert main(arguments) == 1
    assert "already exists" in capsys.readouterr().err
