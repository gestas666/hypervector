"""Entry indicators and regime evidence remain bound to their originating run."""

from copy import deepcopy
from pathlib import Path

import pytest

from hypervector.research.cohort_trade_reflection_index import (
    build_reflection_evidence_index,
)

from test_cohort_checkpoint_restart_recovery import (
    _hashes, _open_restart_fixture, _publish, _write_ledgers,
)
from test_cohort_canonical_regime_telemetry import _evaluation


def _fixture() -> tuple[list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    """Add distinct recorded entry evidence before the restarted run's identity."""
    cohort, assets = _open_restart_fixture()
    route = deepcopy(next(row for row in cohort if row['event_type'] == 'intent_routing'))
    provider = route['payload']['evaluations'][0]
    provider['readiness']['metrics']['adx'] = 27.25
    provider['readiness']['indicators'] = ['ORIGINAL ENTRY INDICATOR']
    route.update(run_id='prior-run', observed_at_utc='2026-08-01T16:00:00.050000+00:00')
    route['payload'] = {'evaluations': [provider]}
    canonical = deepcopy(route)
    canonical.update(event_type='canonical_regime_evaluations',
                     observed_at_utc='2026-08-01T16:00:00.040000+00:00')
    canonical['payload'] = {'evaluations': [_evaluation(1_785_600_000_000)]}
    combined = [cohort[0], canonical, route, *cohort[1:]]
    return [{**row, 'sequence': n} for n, row in enumerate(combined, 1)], assets


def test_restarted_checkpoint_preserves_exact_prior_entry_context(tmp_path: Path) -> None:
    """Actual publication must recover prior context rather than today's matching clock."""
    cohort, assets = _fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    before = _hashes(root)
    checkpoint = _publish(root, tmp_path)
    audit = checkpoint['audit']
    trade = audit['open_trade_reflections']['trades'][0]
    provider = trade['entry_context']['signal_provider']
    assert provider['readiness']['metrics']['adx'] == 27.25
    assert provider['readiness']['indicators'] == ['ORIGINAL ENTRY INDICATOR']
    assert trade['entry_context']['canonical_regime']['status'] == 'observed'
    assert trade['entry_context']['canonical_regime']['primary_regime'] == 'RANGE'
    assert audit['execution']['current_run_fills'] == 0
    assert audit['execution']['fills'] == 1
    assert audit['execution']['open_positions'][0]['fees_usd'] == 0.01
    expected = sum(len(row['payload']['evaluations']) for row in cohort
                   if row['event_type'] == 'intent_routing' and row['run_id'] != 'prior-run')
    assert audit['readiness']['evaluations'] == expected
    assert _hashes(root) == before


@pytest.mark.parametrize('field,value', [
    ('symbol', 'ETH'), ('strategy_id', 'other-provider'),
    ('decision_time_ms', 1_785_599_940_000),
])
def test_unrelated_prior_evaluation_is_not_entry_evidence(
    tmp_path: Path, field: str, value: object,
) -> None:
    """A same-run annotation must also match provider, symbol and decision."""
    cohort, assets = _fixture()
    cohort[2]['payload']['evaluations'][0][field] = value
    root = _write_ledgers(tmp_path, cohort, assets)
    trade = _publish(root, tmp_path)['audit']['open_trade_reflections']['trades'][0]
    assert trade['entry_context']['signal_provider']['readiness'] is None


def test_conflicting_prior_entry_evaluations_reject_publication(tmp_path: Path) -> None:
    """Recovery cannot silently choose between contradictory exact evaluations."""
    cohort, assets = _fixture()
    duplicate = deepcopy(cohort[2])
    duplicate['payload']['evaluations'][0]['readiness']['metrics']['adx'] = 99.0
    cohort.insert(3, duplicate)
    cohort = [{**row, 'sequence': n} for n, row in enumerate(cohort, 1)]
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match='conflicting duplicate trade-reflection'):
        _publish(root, tmp_path)
    assert not (tmp_path / 'checkpoint.json').exists()


def test_recovered_entry_annotation_is_not_a_regime_timeline() -> None:
    """Sparse entry evidence must not become current state or path history."""
    cohort, _ = _fixture()
    projected = {**cohort[2], 'event_type': 'recovered_entry_evaluations'}
    index = build_reflection_evidence_index([projected])
    assert len(index.evaluations) == 1
    assert index.latest_by_run == {}
    assert index.timelines == {}
    assert index.candles == {}


@pytest.mark.parametrize('recovered_first', [True, False])
def test_recovered_annotation_does_not_hide_complete_evidence(recovered_first: bool) -> None:
    """An exact recovered duplicate cannot suppress independently complete telemetry."""
    cohort, _ = _fixture()
    normal = cohort[2]
    projected = {**normal, 'event_type': 'recovered_entry_evaluations'}
    rows = [projected, normal] if recovered_first else [normal, projected]
    assert build_reflection_evidence_index(rows) == build_reflection_evidence_index([normal])


@pytest.mark.parametrize('field', ['profile_id', 'profile_fingerprint', 'run_fingerprint'])
def test_entry_context_rejects_conflicting_identity(tmp_path: Path, field: str) -> None:
    """A matching evaluation key cannot override contradictory source identity."""
    cohort, assets = _fixture()
    cohort[2][field] = 'wrong-identity'
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match='conflicting source identity'):
        _publish(root, tmp_path)


def test_entry_context_observed_after_cutoff_is_unavailable(tmp_path: Path) -> None:
    """A physically earlier but future-observed annotation cannot cross the cutoff."""
    cohort, assets = _fixture()
    cohort[2]['observed_at_utc'] = '2026-08-02T16:00:00+00:00'
    root = _write_ledgers(tmp_path, cohort, assets)
    trade = _publish(root, tmp_path)['audit']['open_trade_reflections']['trades'][0]
    assert trade['entry_context']['signal_provider']['readiness'] is None


def test_entry_context_future_decision_is_rejected(tmp_path: Path) -> None:
    """An exact decision cannot predate its own observation clock."""
    cohort, assets = _fixture()
    cohort[2]['observed_at_utc'] = '2026-08-01T15:59:59+00:00'
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match='decision is in the future'):
        _publish(root, tmp_path)


def test_identical_duplicates_do_not_multiply_entry_evidence(tmp_path: Path) -> None:
    """Repeated identical source observations have one exact evaluation identity."""
    cohort, assets = _fixture()
    cohort.insert(3, deepcopy(cohort[2]))
    cohort = [{**row, 'sequence': n} for n, row in enumerate(cohort, 1)]
    root = _write_ledgers(tmp_path, cohort, assets)
    checkpoint = _publish(root, tmp_path)
    evidence = checkpoint['evidence']['cohort']['entry_context_ancestry']
    assert evidence['observed_evaluations'] == 2
    assert evidence['timeline_recovered'] is False
    assert checkpoint['audit']['execution']['fills'] == 1


def test_restart_context_does_not_change_current_run_or_execution(tmp_path: Path) -> None:
    """Restored entry annotations leave current telemetry and receipts unchanged."""
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    cohort, assets = _open_restart_fixture()
    baseline = _publish(_write_ledgers(legacy, cohort, assets), legacy)['audit']
    cohort, assets = _fixture()
    actual = _publish(_write_ledgers(tmp_path, cohort, assets), tmp_path)['audit']
    for key in ('run', 'runtime', 'readiness', 'routing', 'health', 'execution'):
        assert actual[key] == baseline[key], key


def test_prior_context_edits_are_reread_instead_of_cached(tmp_path: Path) -> None:
    """A changed old annotation must appear on the next report, with new provenance."""
    cohort, assets = _fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    first = _publish(root, tmp_path)
    path = root / 'decisions.jsonl'
    raw = path.read_bytes()
    assert b'27.25' in raw
    path.write_bytes(raw.replace(b'27.25', b'28.25'))
    second = _publish(root, tmp_path)
    provider = second['audit']['open_trade_reflections']['trades'][0]['entry_context']['signal_provider']
    assert provider['readiness']['metrics']['adx'] == 28.25
    assert first['evidence']['cohort']['entry_context_ancestry']['sha256'] != second['evidence']['cohort']['entry_context_ancestry']['sha256']
