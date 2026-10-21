"""Asset telemetry recovery keeps accounting identities without retaining books."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from hypervector.live.sol_range_onset_config import SolRangeOnsetConfig
from hypervector.live.sol_range_onset_ledger import SolLiveLedger, SolLiveLedgerError
from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry

from engine_config_fixtures import engine_asset_config

_OBSERVED = datetime(2026, 7, 31, 12, tzinfo=UTC)


def _history(tmp_path: Path) -> tuple[SolRangeOnsetConfig, SolLiveLedger]:
    """Create a local-only ledger and configuration without an execution client."""
    config = engine_asset_config(tmp_path / 'live/bidirectional_cohort/sol.jsonl')
    ledger = SolLiveLedger(
        path=config.live_ledger, profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint, run_id='prior-run',
    )
    return config, ledger


def _append(ledger: SolLiveLedger, event_type: str, payload: dict[str, object]) -> None:
    """Append one historical fixture through the production validation boundary."""
    ledger.append(event_type=event_type, payload=payload,
                  observed_at_utc=_OBSERVED.isoformat(), live_armed=True,
                  execution_authority='hyperliquid_mainnet')


def test_recovery_streams_history_and_preserves_accounting_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Books cannot force full materialization; all deduplication keys survive."""
    config, ledger = _history(tmp_path)
    _append(ledger, 'book_observation', {'symbol': 'SOL'})
    _append(ledger, 'fill', {'trade_id': 11})
    _append(ledger, 'fee', {'source': 'fill', 'trade_id': 11})
    _append(ledger, 'fee', {'source': 'venue_fee_schedule'})
    _append(ledger, 'funding', {'transaction_hash': 'funding-1', 'venue_timestamp_ms': 12})
    _append(ledger, 'book_observation', {'symbol': 'SOL'})

    def forbidden_read_all() -> list[dict[str, object]]:
        raise AssertionError('asset recovery must not retain the complete history')

    monkeypatch.setattr(ledger, 'read_all', forbidden_read_all)
    telemetry = SolLiveTelemetry(config=config, ledger=ledger, now_fn=lambda: _OBSERVED)

    assert telemetry._fresh_ledger is False
    assert telemetry._run_started_at_ms == int(_OBSERVED.timestamp() * 1000)
    assert telemetry._seen_fills == {11}
    assert telemetry._seen_fill_fees == {11}
    assert telemetry._seen_funding == {('funding-1', 12)}


@pytest.mark.parametrize('has_history', [False, True])
def test_history_without_accounting_events_retains_freshness_and_start_time(
    tmp_path: Path, has_history: bool,
) -> None:
    """A book-only history remains distinct from a genuinely empty ledger."""
    config, ledger = _history(tmp_path)
    if has_history:
        _append(ledger, 'book_observation', {'symbol': 'SOL'})
    telemetry = SolLiveTelemetry(config=config, ledger=ledger, now_fn=lambda: _OBSERVED)
    assert telemetry._fresh_ledger is not has_history
    expected_start = int(_OBSERVED.timestamp() * 1000) if has_history else None
    assert telemetry._run_started_at_ms == expected_start
    assert telemetry._seen_fills == telemetry._seen_fill_fees == set()
    assert telemetry._seen_funding == set()


def test_unretained_book_rows_still_receive_full_validation(tmp_path: Path) -> None:
    """Filtering recovery records cannot conceal corruption in unrelated history."""
    config, ledger = _history(tmp_path)
    _append(ledger, 'book_observation', {'symbol': 'SOL'})
    invalid = {'sequence': 2, 'event_type': 'book_observation',
               'payload': {'price': float('nan')}}
    with ledger.path.open('a') as handle:
        handle.write(json.dumps(invalid) + '\n')
    with pytest.raises(SolLiveLedgerError, match='non-finite'):
        SolLiveTelemetry(config=config, ledger=ledger, now_fn=lambda: _OBSERVED)


def test_invalid_historical_fill_identity_remains_an_error(tmp_path: Path) -> None:
    """Recovery does not silently drop a malformed accounting event."""
    config, ledger = _history(tmp_path)
    _append(ledger, 'book_observation', {'symbol': 'SOL'})
    _append(ledger, 'fill', {'oid': 11})
    with pytest.raises(ValueError, match='trade_id'):
        SolLiveTelemetry(config=config, ledger=ledger, now_fn=lambda: _OBSERVED)
