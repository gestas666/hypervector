"""Source-boundary and causality failures during report-only entry recovery."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from hypervector.research import cohort_entry_context_recovery as recovery
from test_cohort_checkpoint_entry_context_restart import _fixture
from test_cohort_checkpoint_restart_recovery import _publish, _write_ledgers


@pytest.mark.parametrize('start,end,message', [
    (-1, 3, 'non-empty prior'), (3, 3, 'non-empty prior'),
    (0, 20, 'truncated before'), (0, 2, 'incomplete record'),
])
def test_entry_scan_requires_complete_bounded_source(
    tmp_path: Path, start: int, end: int, message: str,
) -> None:
    """Malformed bounds or truncated rows fail instead of creating partial evidence."""
    path = tmp_path / 'rows.jsonl'
    path.write_bytes(b'{}\n')
    with pytest.raises(ValueError, match=message):
        list(recovery._bounded_lines(path, start, end))


@pytest.mark.parametrize('operation', ['truncate', 'replace'])
def test_source_mutation_during_scan_rejects_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    """A substituted or shortened fixture source cannot authenticate scanned rows."""
    cohort, assets = _fixture()
    root = _write_ledgers(tmp_path, cohort, assets)
    original = recovery._bounded_lines

    def mutate(path: Path, start: int, end: int) -> Iterator[tuple[int, bytes]]:
        yield from original(path, start, end)
        if operation == 'truncate':
            path.write_bytes(b'')
        else:
            replacement = path.with_suffix('.replacement')
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)

    monkeypatch.setattr(recovery, '_bounded_lines', mutate)
    with pytest.raises(ValueError, match='during recovery'):
        _publish(root, tmp_path)
    assert not (tmp_path / 'checkpoint.json').exists()


def test_evaluation_predating_source_identity_is_rejected(tmp_path: Path) -> None:
    """Physically misplaced evidence cannot be attributed before its run began."""
    cohort, assets = _fixture()
    cohort[2]['observed_at_utc'] = '2026-08-01T15:59:00+00:00'
    root = _write_ledgers(tmp_path, cohort, assets)
    with pytest.raises(ValueError, match='predates its source run'):
        _publish(root, tmp_path)
