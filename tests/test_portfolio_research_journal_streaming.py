"""Require bounded evidence reads through the public research journal APIs."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from hypervector.data.research_database import ResearchDatabase
from test_portfolio_research_journal import _record, _record_file

READ_LIMIT = 1024 * 1024


class BoundedReader(io.BufferedReader):
    """Reject whole-artifact reads while preserving real local file behavior."""

    def __init__(self, source: io.BufferedReader, requests: list[int]) -> None:
        """Bind the real evidence stream and its read-size audit."""
        super().__init__(source)
        self.requests = requests

    def read(self, size: int | None = -1) -> bytes:
        """Require each requested chunk to fit the evidence read budget."""
        assert size is not None and 0 < size <= READ_LIMIT, 'unbounded evidence read'
        self.requests.append(size)
        return super().read(size)


def guard_evidence_reads(monkeypatch: pytest.MonkeyPatch, evidence: Path) -> list[int]:
    """Apply the budget only to the evidence file, leaving JSON/DB reads intact."""
    original = Path.open
    requests: list[int] = []

    def guarded(path: Path, mode: str = 'r', *args: object, **kwargs: object) -> object:
        """Wrap the one binary evidence stream used by production code."""
        source = original(path, mode, *args, **kwargs)
        if path.resolve() == evidence.resolve():
            assert mode == 'rb' and isinstance(source, io.BufferedReader)
            return BoundedReader(source, requests)
        return source

    monkeypatch.setattr(Path, 'open', guarded)
    return requests


@pytest.mark.parametrize('phase', ['append', 'report'])
@pytest.mark.parametrize('size', [0, 2 * READ_LIMIT + 17])
def test_journal_evidence_reads_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          phase: str, size: int) -> None:
    """Empty and multi-chunk evidence verify through bounded public API reads."""
    evidence = tmp_path / 'evidence.bin'
    evidence.write_bytes(b'a' * size)
    record = _record_file(tmp_path, _record(evidence=evidence))
    database = ResearchDatabase(tmp_path / 'journal.duckdb')
    if phase == 'report':
        database.append_portfolio_research_revision(record)
    requests = guard_evidence_reads(monkeypatch, evidence)
    if phase == 'append':
        assert database.append_portfolio_research_revision(record).inserted
    else:
        assert database.portfolio_research_history('hype-breakout-core')['evidence_integrity'] == {
            'matching': 1, 'changed': 0, 'missing': 0,
        }
    assert requests and max(requests) <= READ_LIMIT
    assert len(requests) >= size // READ_LIMIT + 1


def test_streaming_report_detects_changed_final_chunk(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """A change beyond the first chunk remains visible despite the read limit."""
    evidence = tmp_path / 'evidence.bin'
    evidence.write_bytes(b'a' * (2 * READ_LIMIT + 17))
    record = _record_file(tmp_path, _record(evidence=evidence))
    database = ResearchDatabase(tmp_path / 'journal.duckdb')
    database.append_portfolio_research_revision(record)
    with evidence.open('r+b') as target:
        target.seek(-1, 2)
        target.write(b'b')
    guard_evidence_reads(monkeypatch, evidence)
    assert database.portfolio_research_history('hype-breakout-core')['evidence_integrity'] == {
        'matching': 0, 'changed': 1, 'missing': 0,
    }


def test_streaming_append_keeps_byte_count_validation(tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """Correct digest with a wrong declared byte count still refuses ingestion."""
    evidence = tmp_path / 'evidence.bin'
    evidence.write_bytes(b'a' * (READ_LIMIT + 17))
    payload = _record(evidence=evidence)
    payload['evidence'][0]['bytes'] += 1
    record = _record_file(tmp_path, payload)
    database = ResearchDatabase(tmp_path / 'journal.duckdb')
    guard_evidence_reads(monkeypatch, evidence)
    with pytest.raises(ValueError, match='evidence byte-count mismatch'):
        database.append_portfolio_research_revision(record)


@pytest.mark.parametrize('phase', ['append', 'report'])
def test_missing_evidence_stays_explicit(tmp_path: Path, phase: str) -> None:
    """Missing files cannot become successful ingestion or matching reports."""
    evidence = tmp_path / 'evidence.bin'
    evidence.write_bytes(b'evidence')
    record = _record_file(tmp_path, _record(evidence=evidence))
    database = ResearchDatabase(tmp_path / 'journal.duckdb')
    if phase == 'report':
        database.append_portfolio_research_revision(record)
    evidence.unlink()
    if phase == 'append':
        with pytest.raises(FileNotFoundError, match='research evidence file is missing'):
            database.append_portfolio_research_revision(record)
    else:
        assert database.portfolio_research_history('hype-breakout-core')['evidence_integrity'] == {
            'matching': 0, 'changed': 0, 'missing': 1,
        }


@pytest.mark.parametrize('phase', ['append', 'report'])
def test_evidence_read_errors_propagate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      phase: str) -> None:
    """An unreadable stream is an explicit failure rather than matching evidence."""
    evidence = tmp_path / 'evidence.bin'
    evidence.write_bytes(b'evidence')
    record = _record_file(tmp_path, _record(evidence=evidence))
    database = ResearchDatabase(tmp_path / 'journal.duckdb')
    if phase == 'report':
        database.append_portfolio_research_revision(record)
    original = Path.open

    def unreadable(path: Path, *args: object, **kwargs: object) -> object:
        """Reproduce an evidence-only operating-system read failure."""
        if path.resolve() == evidence.resolve():
            raise PermissionError('evidence permission denied')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', unreadable)
    with pytest.raises(PermissionError, match='evidence permission denied'):
        if phase == 'append':
            database.append_portfolio_research_revision(record)
        else:
            database.portfolio_research_history('hype-breakout-core')
