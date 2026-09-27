"""Snapshot integrity and bounded-memory behavior without routine disk copies."""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import importlib
import io
import json
from pathlib import Path
import tempfile
from typing import BinaryIO
from unittest.mock import patch

import pytest

from hypervector.research.checkpoint_ledger_projection import compact_asset_ledger_rows
from hypervector.research import live_ledger_snapshot as snapshots
from test_live_ledger_snapshot import _compatible_history, _line
from test_mapped_snapshot_file import mappings


def forbid_disk_file(*args: object, **kwargs: object) -> BinaryIO:
    """Simulate unavailable scratch storage, without touching the source ledger."""
    raise OSError("scratch storage unavailable")


@contextmanager
def no_disk_snapshots() -> Iterator[None]:
    """Deny both named copies and spooled-file rollover during this test."""
    with patch.object(tempfile, "NamedTemporaryFile", forbid_disk_file):
        with patch.object(tempfile, "TemporaryFile", forbid_disk_file):
            yield


@pytest.mark.parametrize("partial", [b"", b'{"sequence":3'])
def test_current_run_sized_snapshot_needs_no_disk_copy(
    tmp_path: Path, partial: bytes
) -> None:
    """Small complete prefixes remain readable when scratch disk allocation fails."""
    path = tmp_path / "ledger.jsonl"
    stable = _line(1) + _line(2)
    path.write_bytes(stable + partial)
    with (
        no_disk_snapshots(),
        snapshots.snapshot_decision_ledger(path, allow_incomplete_tail=True) as (
            rows,
            evidence,
        ),
    ):
        assert [row["sequence"] for row in rows] == [1, 2]
        assert evidence["sha256"] == hashlib.sha256(stable).hexdigest()
        assert evidence["bytes"] == len(stable)
        assert evidence["dropped_tail_bytes"] == len(partial)
        path.write_bytes(_line(99))
        assert [row["sequence"] for row in rows] == [1, 2]


def test_full_current_run_keeps_exact_rebased_history_without_scratch(
    tmp_path: Path,
) -> None:
    """The actual reporter mode retains every current-run row and source sequence."""
    path = tmp_path / "ledger.jsonl"
    segments = _compatible_history()
    path.write_bytes(b"".join(segments))
    with (
        no_disk_snapshots(),
        snapshots.snapshot_current_run_ledger(path, run_id="run-current") as (
            rows,
            evidence,
        ),
    ):
        assert [row["sequence"] for row in rows] == [1, 2]
        assert evidence["source_sequence_start"] == 7
        assert evidence["source_sequence_end"] == 8
        assert evidence["sha256"] == hashlib.sha256(segments[-1]).hexdigest()


def test_streamed_compatible_projection_matches_path_projection(tmp_path: Path) -> None:
    """Stream projection cannot change compatible history selection or provenance."""
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(
        b"".join(_compatible_history()).replace(
            b'"event_type": "fill"', b'"event_type": "heartbeat"'
        )
    )

    def projector(source: Path | Iterator[str]) -> snapshots.ProjectedLedgerRows:
        """Retain all event rows in this compatibility fixture."""
        return compact_asset_ledger_rows(source, current_run_id="run-current")

    with snapshots.snapshot_projected_compatible_execution_ledger(
        path, run_id="run-current", projector=projector
    ) as baseline:
        expected_rows, expected_evidence = baseline
    snapshots._COMPATIBLE_BOUNDARIES.clear()
    with (
        no_disk_snapshots(),
        snapshots.snapshot_projected_compatible_execution_ledger(
            path, run_id="run-current", stream_projector=projector
        ) as (rows, evidence),
    ):
        assert rows == expected_rows
        assert evidence == expected_evidence


def test_stream_projection_parser_matches_file_input(tmp_path: Path) -> None:
    """A stream and file must undergo the same contiguous-sequence validation."""
    path = tmp_path / "ledger.jsonl"
    content = _line(1) + _line(2)
    content = content.replace(
        b'"payload": {}', b'"event_type": "heartbeat", "payload": {}'
    )
    path.write_bytes(content)
    expected = compact_asset_ledger_rows(path, current_run_id="run-current")
    assert (
        compact_asset_ledger_rows(
            io.StringIO(content.decode()), current_run_id="run-current"
        )
        == expected
    )


def test_spill_retains_identical_contents_and_checksums(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exceeding the memory budget spills storage without dropping any evidence."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    monkeypatch.setattr(storage, "SNAPSHOT_MEMORY_BYTES", 32)
    path = tmp_path / "ledger.jsonl"
    content = _line(1) + _line(2)
    path.write_bytes(content)
    with patch.object(tempfile, "TemporaryFile", wraps=tempfile.TemporaryFile) as disk:
        with snapshots.snapshot_decision_ledger(path) as (rows, evidence):
            assert [row["sequence"] for row in rows] == [1, 2]
            assert evidence == {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        assert disk.call_count == 1


def test_spill_failure_is_explicit_and_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full scratch filesystem cannot become an empty successful snapshot."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    monkeypatch.setattr(storage, "SNAPSHOT_MEMORY_BYTES", 1)
    path = tmp_path / "ledger.jsonl"
    content = _line(1)
    path.write_bytes(content)
    with (
        no_disk_snapshots(),
        pytest.raises(OSError, match="scratch storage unavailable"),
    ):
        with snapshots.snapshot_decision_ledger(path):
            pass
    assert path.read_bytes() == content


@pytest.mark.parametrize("budget", [1, 128 * 1024 * 1024])
@pytest.mark.parametrize(
    "content,error",
    [
        (b"{broken}\n", "invalid JSONL"),
        (b"[]\n", "decision row must be object"),
        (b'{"sequence":1', "incomplete trailing JSONL record"),
    ],
)
def test_memory_and_spill_reject_invalid_complete_or_partial_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    budget: int,
    content: bytes,
    error: str,
) -> None:
    """Storage choice cannot turn corrupt or torn evidence into valid rows."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    monkeypatch.setattr(storage, "SNAPSHOT_MEMORY_BYTES", budget)
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(content)
    with (
        pytest.raises(ValueError, match=error),
        snapshots.snapshot_decision_ledger(path),
    ):
        pass


@pytest.mark.parametrize("budget", [1, 128 * 1024 * 1024])
def test_snapshot_resource_is_released_before_rows_are_yielded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    budget: int,
) -> None:
    """Retaining multiple asset row sets must not retain their raw memory buffers."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    monkeypatch.setattr(storage, "SNAPSHOT_MEMORY_BYTES", budget)
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(_line(1))
    with mappings() as allocated:
        with snapshots.snapshot_decision_ledger(path) as (rows, _):
            assert len(allocated) == 1
            assert allocated[0].closed
            assert rows[0]["sequence"] == 1


def test_stream_projection_uses_frozen_bytes_when_original_changes(
    tmp_path: Path,
) -> None:
    """Hash and projected rows must describe the same frozen copy during mutation."""
    path = tmp_path / "ledger.jsonl"
    content = b"".join(_compatible_history()).replace(
        b'"event_type": "fill"', b'"event_type": "heartbeat"'
    )
    path.write_bytes(content)

    def projector(lines: Iterator[str]) -> snapshots.ProjectedLedgerRows:
        """Mutate the external source after capture and before consuming its copy."""
        path.write_bytes(b"corrupted external source\n")
        return compact_asset_ledger_rows(lines, current_run_id="run-current")

    with snapshots.snapshot_projected_compatible_execution_ledger(
        path, run_id="run-current", stream_projector=projector
    ) as (rows, evidence):
        offset = evidence["source_start_offset"]
        assert evidence["sha256"] == hashlib.sha256(content[offset:]).hexdigest()
        assert len(rows) == 6


@pytest.mark.parametrize(
    "sequences,start,end,error",
    [
        ([], 1, 1, "no records"),
        ([True], 1, 1, "invalid sequence"),
        ([2, 1], 1, 2, "not source ordered"),
        ([1, 1], 1, 1, "not source ordered"),
        ([1], 2, 3, "exceeds source range"),
        ([3], 1, 2, "exceeds source range"),
    ],
)
def test_invalid_projection_cannot_publish_fabricated_sequence_bounds(
    tmp_path: Path,
    sequences: list[object],
    start: int,
    end: int,
    error: str,
) -> None:
    """Malformed projection results fail before advisory evidence is returned."""
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"".join(_compatible_history()))

    def projector(lines: Iterator[str]) -> snapshots.ProjectedLedgerRows:
        """Return an intentionally invalid projection result as a negative control."""
        return snapshots.ProjectedLedgerRows(
            [{"sequence": item} for item in sequences], start, end
        )

    with (
        pytest.raises(ValueError, match=error),
        snapshots.snapshot_projected_compatible_execution_ledger(
            path, run_id="run-current", stream_projector=projector
        ),
    ):
        pass


def test_projector_contract_requires_exactly_one_consumer(tmp_path: Path) -> None:
    """An ambiguous API request cannot silently select a different projection."""
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"".join(_compatible_history()))
    with (
        pytest.raises(ValueError, match="exactly one"),
        snapshots.snapshot_projected_compatible_execution_ledger(
            path, run_id="run-current"
        ),
    ):
        pass
    with (
        pytest.raises(ValueError, match="exactly one"),
        snapshots.snapshot_projected_compatible_execution_ledger(
            path,
            run_id="run-current",
            projector=compact_asset_ledger_rows,
            stream_projector=compact_asset_ledger_rows,
        ),
    ):
        pass


def test_storage_rejects_ambiguous_projectors_before_opening_source(
    tmp_path: Path,
) -> None:
    """The lower-level API rejects ambiguous consumers even without a source file."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    with (
        pytest.raises(ValueError, match="mutually exclusive"),
        storage.loaded_suffix_snapshot(
            tmp_path / "absent.jsonl",
            start_offset=0,
            allow_incomplete_tail=False,
            evidence_extra={},
            projector=compact_asset_ledger_rows,
            stream_projector=compact_asset_ledger_rows,
        ),
    ):
        pass


def test_multichunk_unicode_and_blank_lines_retain_exact_bytes(tmp_path: Path) -> None:
    """Decoded rows and byte provenance must agree across copy chunk boundaries."""
    path = tmp_path / "ledger.jsonl"
    row = {"sequence": 1, "payload": {"text": "\u00e9" * (1024 * 1024)}}
    content = b"\n" + json.dumps(row, ensure_ascii=False).encode() + b"\r\n\n"
    path.write_bytes(content)
    with (
        no_disk_snapshots(),
        snapshots.snapshot_decision_ledger(path) as (rows, evidence),
    ):
        assert rows == [row]
        assert evidence == {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }


@pytest.mark.parametrize("partial", [b"", b'{"unfinished":'])
def test_empty_stable_prefix_retains_exact_empty_hash(
    tmp_path: Path, partial: bytes
) -> None:
    """The existing empty-prefix contract is preserved without inventing records."""
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(partial)
    with (
        no_disk_snapshots(),
        snapshots.snapshot_decision_ledger(path, allow_incomplete_tail=True) as (
            rows,
            evidence,
        ),
    ):
        assert rows == []
        assert evidence["bytes"] == 0
        assert evidence["sha256"] == hashlib.sha256(b"").hexdigest()
        assert evidence["dropped_tail_bytes"] == len(partial)


def test_current_run_snapshot_uses_multi_day_memory_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long run's share stays in anonymous pages instead of a 30 s disk copy."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    assert 1024**3 <= storage.SNAPSHOT_MEMORY_BYTES <= 2 * 1024**3
    capacities: list[int] = []
    original = storage.MappedSnapshotFile

    def recording(capacity: int) -> BinaryIO:
        capacities.append(capacity)
        return original(capacity)

    monkeypatch.setattr(storage, "MappedSnapshotFile", recording)
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"".join(_compatible_history()))
    with (
        no_disk_snapshots(),
        snapshots.snapshot_current_run_ledger(path, run_id="run-current") as (rows, _),
    ):
        assert [row["sequence"] for row in rows] == [1, 2]
    assert capacities == [storage.SNAPSHOT_MEMORY_BYTES]


def test_default_budget_holds_more_than_former_budget_without_scratch() -> None:
    """Bytes past the former 128 MiB spill point must not reach scratch disk."""
    storage = importlib.import_module("hypervector.research.ledger_snapshot_io")
    former_budget = 128 * 1024 * 1024
    chunk = bytes(range(256)) * 4096
    digest = hashlib.sha256()
    with (
        no_disk_snapshots(),
        storage.MappedSnapshotFile(storage.SNAPSHOT_MEMORY_BYTES) as stream,
    ):
        for _ in range(former_budget // len(chunk) + 1):
            assert stream.write(chunk) == len(chunk)
            digest.update(chunk)
        assert stream.tell() > former_budget
        stream.seek(0)
        assert hashlib.file_digest(stream, "sha256").hexdigest() == digest.hexdigest()
