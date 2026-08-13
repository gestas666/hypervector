"""Shared source-follow live-audit test fixtures."""

from __future__ import annotations

import duckdb


def event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    *,
    profile_id: str = "source-bidirectional",
) -> dict[str, object]:
    """Build one identified live-ledger event."""
    return {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": f"2026-07-31T20:{sequence:02d}:00+00:00",
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": True,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": profile_id,
        "profile_fingerprint": f"profile-{profile_id}",
        "run_fingerprint": f"run-{profile_id}",
        "run_id": run_id,
        "payload": payload,
    }


def identity(run_id: str, sequence: int, profile_id: str) -> dict[str, object]:
    """Build one source-follow configuration identity."""
    return event(
        run_id,
        sequence,
        "configuration_identity",
        {
            "symbol": "BTC",
            "strategy_name": "hypervelocity_source_follow_5m",
            "network": "mainnet",
        },
        profile_id=profile_id,
    )


def candle(
    run_id: str,
    sequence: int,
    *,
    event_type: str = "regime_history",
    feed_ts: str = "2026-07-31T20:00:00+00:00",
    profile_id: str = "source-bidirectional",
) -> dict[str, object]:
    """Build one valid source-follow backend candle event."""
    return event(
        run_id,
        sequence,
        event_type,
        {
            "feed_ts": feed_ts,
            "primary_regime": "RANGE",
            "confidence": 0.75,
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "reference_price": 101.0,
            "volume": 12.0,
            "entry_allowed": False,
            "regime_admitted": False,
            "long_entry": False,
            "short_entry": False,
            "decision_action": "history_only",
        },
        profile_id=profile_id,
    )


def create_replay_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the minimal independent tape schema used by audit tests."""
    connection.execute(
        """
        CREATE TABLE replay_live_public_trades (
            symbol VARCHAR, aggressor_side VARCHAR, price DOUBLE, size DOUBLE,
            exchange_ts_ms BIGINT, received_ts_ns BIGINT, trade_id BIGINT
        );
        CREATE TABLE replay_live_book_snapshots (
            symbol VARCHAR, exchange_ts_ms BIGINT, received_ts_ns BIGINT
        );
        CREATE TABLE live_stream_gaps (
            symbol VARCHAR, channel VARCHAR, detected_ts_ns BIGINT,
            reason VARCHAR, previous_exchange_ts_ms BIGINT,
            next_exchange_ts_ms BIGINT
        );
        """
    )
