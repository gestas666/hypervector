"""A flat restart retains compatible history projected by the active backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from cohort_live_audit_trade_fixture import traded_asset_rows
from hypervector.research.cohort_checkpoint_asset_snapshots import (
    projected_asset_fill_counts,
)
from test_cohort_checkpoint_restart_recovery import _hashes, _publish, _write_ledgers
from test_multi_asset_live_audit import (
    _RUN_ID,
    _SYMBOLS,
    _asset_rows,
    _cohort_rows_with_trade,
)
from test_multi_asset_live_audit_restart import _append_run, _with_prior_cohort_identity


@pytest.mark.parametrize('recent_fills_present', [False, True])
def test_flat_restart_recovers_completed_history_projected_by_backend(
    tmp_path: Path, recent_fills_present: bool,
) -> None:
    """Closed trade totals survive a restart even after recent fills roll off."""
    cohort = _with_prior_cohort_identity(_cohort_rows_with_trade())
    for row in cohort:
        if row['event_type'] != 'cohort_snapshot':
            continue
        row['payload']['assets'][0]['fill_count'] = 2
        for fill in row['payload']['recent_fills']:
            fill['origin_run_id'] = 'prior-run'
        if not recent_fills_present:
            row['payload']['recent_fills'] = []
    assets = {symbol: _asset_rows(symbol) for symbol in _SYMBOLS}
    assets['BTC'] = _append_run(traded_asset_rows('prior-run'), assets['BTC'])
    root = _write_ledgers(tmp_path, cohort, assets)
    before = _hashes(root)

    checkpoint = _publish(root, tmp_path)

    execution = checkpoint['audit']['execution']
    assert execution['current_run_fills'] == 0
    assert execution['fills'] == execution['projected_fills'] == 2
    assert execution['closed_trades'] == 1
    assert execution['net_pnl_usd'] == pytest.approx(0.97)
    assert execution['fees_usd'] == pytest.approx(0.02)
    assert execution['funding_usd'] == pytest.approx(-0.01)
    assert checkpoint['audit']['coverage'] == {'complete': True, 'technical_gaps': []}
    assert checkpoint['audit']['run']['run_id'] == _RUN_ID
    assert _hashes(root) == before


def test_projected_fill_count_requires_compatible_exact_history(tmp_path: Path) -> None:
    """An incompatible old profile cannot satisfy the backend's accounting count."""
    cohort = _with_prior_cohort_identity(_cohort_rows_with_trade())
    for row in cohort:
        if row['event_type'] == 'cohort_snapshot':
            row['payload']['assets'][0]['fill_count'] = 2
    prior = traded_asset_rows('prior-run')
    for row in prior:
        row['run_fingerprint'] = 'incompatible-run-fingerprint'
    assets = {symbol: _asset_rows(symbol) for symbol in _SYMBOLS}
    assets['BTC'] = _append_run(prior, assets['BTC'])
    root = _write_ledgers(tmp_path, cohort, assets)

    with pytest.raises(ValueError, match='projected fill count.*compatible execution'):
        _publish(root, tmp_path)
    assert not (tmp_path / 'checkpoint.json').exists()


@pytest.mark.parametrize("invalid_count", [None, True, -1, 0.5, "2"])
def test_invalid_projected_count_is_not_treated_as_missing(
    invalid_count: object,
) -> None:
    """An explicit corrupt count must not silently discard historical evidence."""
    row = {"payload": {"assets": [{"symbol": "BTC", "fill_count": invalid_count}]}}
    with pytest.raises(ValueError, match="asset fill count"):
        projected_asset_fill_counts(row)


def test_duplicate_projected_symbol_is_rejected() -> None:
    """Two conflicting asset counts cannot overwrite each other silently."""
    row = {"payload": {"assets": [
        {"symbol": "BTC", "fill_count": 2},
        {"symbol": "BTC", "fill_count": 0},
    ]}}
    with pytest.raises(ValueError, match="duplicate snapshot asset fill count"):
        projected_asset_fill_counts(row)


def test_legacy_absent_count_remains_distinct_from_explicit_zero() -> None:
    """Legacy snapshots retain their supported scope without inventing a count."""
    row = {"payload": {"assets": [
        {"symbol": "BTC"}, {"symbol": "ETH", "fill_count": 0},
    ]}}
    assert projected_asset_fill_counts(row) == {"ETH": 0}
