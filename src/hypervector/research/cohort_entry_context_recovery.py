"""Bounded, read-only recovery of exact recorded lifecycle entry evaluations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from hypervector.live.canonical_regime_telemetry import CANONICAL_REGIME_TELEMETRY_STRATEGY
from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.research.cohort_live_audit_summaries import rebased
from hypervector.research.cohort_live_audit_values import (
    mapping, mapping_list, nonnegative_int, payload, text, timestamp,
)
from hypervector.research.cohort_trade_reflection_index import (
    RECOVERED_ENTRY_EVALUATIONS,
    build_reflection_evidence_index,
)
from hypervector.research.cohort_trade_reflections import (
    entry_source_runs,
    trade_source_run,
)

Record = Mapping[str, object]
EntryKey = tuple[str, str, str, int]
_EVALUATION_EVENTS = (b'intent_routing', b'canonical_regime_evaluations')
_IDENTITY_FIELDS = ('profile_id', 'profile_fingerprint', 'run_fingerprint')


def recover_entry_context(
    path: Path,
    assets: Mapping[str, Sequence[Record]],
    identities: Sequence[Record],
    ancestry: Sequence[Record],
    *,
    before_offset: int,
    as_of: datetime,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Recover exact entry annotations without manufacturing historical timelines."""
    by_run = {text(row.get('run_id'), 'entry context run'): row for row in identities}
    keys = _entry_keys(assets, frozenset(by_run))
    start = min(nonnegative_int(row.get('source_offset'), 'ancestry offset')
                for row in ancestry)
    selected, evidence = _scan_context(
        path, start, before_offset, keys, by_run, as_of,
    )
    index = build_reflection_evidence_index(selected)
    evidence.update({
        'scope': 'exact_entry_evaluations_only',
        'requested_evaluations': len(keys),
        'observed_evaluations': len(index.evaluations),
        'missing_evaluations': [list(key) for key in sorted(keys - index.evaluations.keys())],
        'timeline_recovered': False,
        'execution_authority': 'none',
    })
    return selected, evidence


def _entry_keys(
    assets: Mapping[str, Sequence[Record]], runs: frozenset[str],
) -> frozenset[EntryKey]:
    sources = entry_source_runs(assets)
    keys: set[EntryKey] = set()
    for symbol, rows in assets.items():
        journal = build_live_journal(rebased(rows))
        lifecycles = [*mapping_list(journal.get('trades'), 'closed lifecycles'),
                      *mapping_list(journal.get('open_lifecycles'), 'open lifecycles')]
        for trade in lifecycles:
            run = trade_source_run(symbol, trade, sources)
            if run not in runs:
                continue
            regime = mapping(trade.get('entry_regime'), 'lifecycle entry regime')
            strategy = text(regime.get('strategy_id'), 'entry strategy')
            decision = nonnegative_int(regime.get('decision_time_ms'), 'entry decision')
            for provider in (strategy, CANONICAL_REGIME_TELEMETRY_STRATEGY):
                keys.add((run, provider, symbol, decision))
    return frozenset(keys)


def _scan_context(
    path: Path, start: int, end: int, keys: frozenset[EntryKey],
    identities: Mapping[str, Record], as_of: datetime,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    selected: list[dict[str, object]] = []
    facts: list[dict[str, object]] = []
    digest = hashlib.sha256()
    clocks = tuple(str(key[3]).encode('ascii') for key in keys)
    source = path.stat()
    active_run: str | None = None
    for offset, raw in _bounded_lines(path, start, end):
        digest.update(raw)
        if b'configuration_identity' in raw:
            row = mapping(json.loads(raw), 'entry context identity')
            if row.get('event_type') == 'configuration_identity':
                active_run = text(row.get('run_id'), 'entry context run')
        if not any(event in raw for event in _EVALUATION_EVENTS):
            continue
        if not any(clock in raw for clock in clocks):
            continue
        row = mapping(json.loads(raw), 'entry context row')
        projected = _project_entry_row(row, keys, identities, active_run, as_of)
        if projected is not None:
            selected.append(projected)
            facts.append({'source_offset': offset, 'bytes': len(raw),
                          'sha256': hashlib.sha256(raw).hexdigest(),
                          'source_sequence': row.get('sequence'),
                          'run_id': row.get('run_id'),
                          'event_type': row.get('event_type')})
    final = path.stat()
    if (source.st_dev, source.st_ino) != (final.st_dev, final.st_ino):
        raise ValueError('entry context ledger identity changed during recovery')
    if final.st_size < source.st_size:
        raise ValueError('entry context ledger was truncated during recovery')
    return selected, {'source_start_offset': start, 'source_end_offset': end,
                      'scanned_bytes': end - start, 'sha256': digest.hexdigest(),
                      'source_device': source.st_dev, 'source_inode': source.st_ino,
                      'selected_rows': facts, 'as_of_utc': as_of.isoformat()}


def _bounded_lines(path: Path, start: int, end: int) -> Iterator[tuple[int, bytes]]:
    if start < 0 or end <= start:
        raise ValueError('entry context requires a non-empty prior ledger range')
    with path.open('rb') as handle:
        if os.fstat(handle.fileno()).st_size < end:
            raise ValueError('entry context ledger was truncated before recovery')
        handle.seek(start)
        offset = start
        while offset < end:
            raw = handle.readline(end - offset)
            if not raw.endswith(b'\n'):
                raise ValueError('entry context range contains an incomplete record')
            yield offset, raw
            offset += len(raw)


def _project_entry_row(
    row: Record, keys: frozenset[EntryKey], identities: Mapping[str, Record],
    active_run: str | None, as_of: datetime,
) -> dict[str, object] | None:
    if row.get('event_type') not in ('intent_routing', 'canonical_regime_evaluations'):
        return None
    run = text(row.get('run_id'), 'entry evaluation run')
    if run not in identities or timestamp(row) > as_of:
        return None
    evaluations = [value for value in mapping_list(payload(row).get('evaluations'),
                                                   'entry evaluations')
                   if _evaluation_key(run, value) in keys]
    if not evaluations:
        return None
    identity = identities[run]
    if active_run != run or any(row.get(key) != identity.get(key)
                                for key in _IDENTITY_FIELDS):
        raise ValueError('entry context evaluation has conflicting source identity')
    if timestamp(row) < timestamp(identity):
        raise ValueError('entry context evaluation predates its source run')
    observed_ms = int(timestamp(row).timestamp() * 1_000)
    if any(_evaluation_key(run, value)[3] > observed_ms for value in evaluations):
        raise ValueError('entry context evaluation decision is in the future')
    return {**row, 'event_type': RECOVERED_ENTRY_EVALUATIONS,
            'payload': {'evaluations': evaluations,
                        'source_event_type': row.get('event_type'),
                        'projection_scope': 'exact_entry_evaluations_only'}}


def _evaluation_key(run: str, value: Record) -> EntryKey:
    return (run, text(value.get('strategy_id'), 'entry evaluation strategy'),
            text(value.get('symbol'), 'entry evaluation symbol'),
            nonnegative_int(value.get('decision_time_ms'), 'entry evaluation decision'))
