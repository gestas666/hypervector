"""Tests for scheduled HIP-3 external-reference session labels."""

from datetime import UTC, datetime

import pytest

from hypervector.research.hip3_market_sessions import (
    SCHEDULED_EXTERNAL_REFERENCE,
    SCHEDULED_INTERNAL_OR_CLOSED,
    oracle_session_contract,
    scheduled_oracle_session,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    (
        ("2026-08-10T23:49:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("2026-08-10T23:55:00", SCHEDULED_INTERNAL_OR_CLOSED),
        ("2026-08-11T00:00:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("2026-08-11T06:35:00", SCHEDULED_INTERNAL_OR_CLOSED),
        ("2026-08-11T10:59:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("2026-08-11T11:00:00", SCHEDULED_INTERNAL_OR_CLOSED),
        ("2026-08-15T00:00:00", SCHEDULED_INTERNAL_OR_CLOSED),
    ),
)
def test_skhx_uses_korean_scheduled_reference_windows(
    timestamp: str,
    expected: str,
) -> None:
    assert scheduled_oracle_session("xyz:SKHX", _utc(timestamp)) == expected


@pytest.mark.parametrize(
    ("symbol", "timestamp", "expected"),
    (
        ("xyz:MU", "2026-08-10T14:00:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("xyz:SKHY", "2026-08-14T23:59:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("xyz:MU", "2026-08-15T14:00:00", SCHEDULED_INTERNAL_OR_CLOSED),
        ("xyz:SKHY", "2026-08-16T23:59:00", SCHEDULED_INTERNAL_OR_CLOSED),
        ("xyz:SKHY", "2026-08-17T00:00:00", SCHEDULED_EXTERNAL_REFERENCE),
        ("xyz:MU", "2026-08-15T00:00:00", SCHEDULED_INTERNAL_OR_CLOSED),
    ),
)
def test_us_equities_use_twenty_four_five_reference_window(
    symbol: str,
    timestamp: str,
    expected: str,
) -> None:
    assert scheduled_oracle_session(symbol, _utc(timestamp)) == expected


def test_session_classifier_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        scheduled_oracle_session("xyz:MU", datetime(2026, 8, 11, 12))


def test_session_classifier_rejects_unsupported_symbols() -> None:
    with pytest.raises(ValueError, match="unsupported HIP-3 session contract"):
        scheduled_oracle_session("BTC", _utc("2026-08-11T12:00:00"))


def test_contract_is_diagnostic_only_and_symbol_exact() -> None:
    contract = oracle_session_contract("xyz:SKHX")

    assert contract["status"] == "classified"
    assert contract["schedule_id"] == "korea_external_reference_v1"
    assert contract["source_url"] == "https://docs.trade.xyz/asset-directory/korea"
    assert contract["execution_gate"] is False
    assert contract["holiday_calendar_applied"] is False
    assert oracle_session_contract("xyz:CL")["status"] == "unclassified"
