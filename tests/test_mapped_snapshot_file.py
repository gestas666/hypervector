"""Byte-stream and resource contracts for mapped snapshots and exact disk spills."""

from __future__ import annotations

from collections.abc import Buffer, Iterator
from contextlib import contextmanager
import hashlib
import importlib
import io
import mmap
import tempfile
from typing import BinaryIO
from unittest.mock import patch

import pytest


def snapshot(capacity: int) -> BinaryIO:
    """Construct the reader under test without making missing code a collection error."""
    module = importlib.import_module("hypervector.research.mapped_snapshot_file")
    return module.MappedSnapshotFile(capacity)


@contextmanager
def mappings() -> Iterator[list[mmap.mmap]]:
    """Retain mapping handles to prove their pages were explicitly unmapped."""
    resources: list[mmap.mmap] = []
    original = mmap.mmap

    def allocate(descriptor: int, length: int) -> mmap.mmap:
        resource = original(descriptor, length)
        resources.append(resource)
        return resource

    with patch.object(mmap, "mmap", allocate):
        yield resources


def test_hash_text_and_explicit_unmapping_before_outer_context_exit() -> None:
    """Closing the text consumer must unmap copied bytes immediately."""
    content = '{"text":"\u00e9"}\r\n\n'.encode()
    with mappings() as allocated, snapshot(4096) as stream:
        assert stream.write(content) == len(content)
        assert stream.seek(0, io.SEEK_END) == len(content)
        stream.seek(0)
        assert hashlib.file_digest(stream, "sha256").hexdigest() == hashlib.sha256(content).hexdigest()
        stream.seek(0)
        with io.TextIOWrapper(stream, encoding="utf-8") as text:
            assert list(text) == ['{"text":"\u00e9"}\n', '\n']
        assert stream.closed
        assert len(allocated) == 1
        assert allocated[0].closed


@pytest.mark.parametrize("capacity", [4, 64])
def test_seek_readinto_eof_and_empty_write_match_file_semantics(capacity: int) -> None:
    """Memory and disk paths expose the same logical length and partial reads."""
    with snapshot(capacity) as stream:
        assert stream.readable() and stream.writable() and stream.seekable()
        assert stream.write(b"abcdef") == 6
        assert stream.write(b"") == 0
        assert stream.tell() == 6
        assert stream.seek(-4, io.SEEK_CUR) == 2
        target = bytearray(b"zzzzz")
        assert stream.readinto(target) == 4
        assert target == b"cdefz"
        assert stream.readinto(target) == 0
        assert stream.seek(-2, io.SEEK_END) == 4
        assert stream.read() == b"ef"


def test_spill_preserves_copied_prefix_and_unmaps_before_yielding_disk_data() -> None:
    """Overflow transfers every copied byte and releases the old mapping promptly."""
    with mappings() as allocated, snapshot(4) as stream:
        assert stream.write(b"abcd") == 4
        assert not allocated[0].closed
        with patch.object(tempfile, "TemporaryFile", wraps=tempfile.TemporaryFile) as disk:
            assert stream.write(b"ef") == 2
            assert disk.call_count == 1
        assert allocated[0].closed
        stream.seek(0)
        assert stream.read() == b"abcdef"


@pytest.mark.parametrize("capacity", [4, 64])
def test_truncation_and_later_extension_do_not_resurrect_discarded_bytes(capacity: int) -> None:
    """Torn-tail truncation changes logical EOF while later extension reads as zeros."""
    with snapshot(capacity) as stream:
        stream.write(b"abcdef")
        assert stream.truncate(3) == 3
        assert stream.tell() == 6
        assert stream.seek(0, io.SEEK_END) == 3
        assert stream.read() == b""
        assert stream.truncate(5) == 5
        stream.seek(0)
        assert stream.read() == b"abc\x00\x00"
        stream.seek(2)
        assert stream.truncate() == 2
        stream.seek(0)
        assert stream.read() == b"ab"


def test_seek_beyond_mapping_then_write_spills_with_zero_filled_gap() -> None:
    """Sparse-file seek semantics must not expose bytes beyond the snapshot."""
    with snapshot(4) as stream:
        stream.write(b"ab")
        stream.seek(6)
        assert stream.read() == b""
        stream.write(b"z")
        stream.seek(0)
        assert stream.read() == b"ab\x00\x00\x00\x00z"


def test_extension_beyond_mapping_spills_without_changing_position() -> None:
    """Length extension must preserve the caller's logical cursor across rollover."""
    with snapshot(4) as stream:
        stream.write(b"ab")
        assert stream.truncate(7) == 7
        assert stream.tell() == 2
        stream.seek(0)
        assert stream.read() == b"ab" + b"\x00" * 5


def test_large_truncation_clears_multiple_zeroing_chunks() -> None:
    """Discarded data across chunk boundaries cannot reappear after extending EOF."""
    with snapshot(256 * 1024) as stream:
        stream.write(b"x" * (192 * 1024))
        stream.truncate(1)
        stream.truncate(192 * 1024)
        stream.seek(0)
        assert stream.read() == b"x" + b"\x00" * (192 * 1024 - 1)


def test_overwriting_existing_bytes_keeps_logical_length() -> None:
    """Seeking within captured bytes must not inflate EOF during a bounded write."""
    with snapshot(64) as stream:
        stream.write(b"abcdef")
        stream.seek(2)
        stream.write(b"XY")
        assert stream.seek(0, io.SEEK_END) == 6
        stream.seek(0)
        assert stream.read() == b"abXYef"


@pytest.mark.parametrize("capacity", [0, -1, True])
def test_invalid_capacity_fails_before_allocating_pages(capacity: int) -> None:
    """Invalid configuration cannot create an unlimited or ambiguous mapping."""
    with mappings() as allocated, pytest.raises(ValueError, match="capacity"):
        snapshot(capacity)
    assert allocated == []


def test_mapping_allocation_failure_is_explicit() -> None:
    """Unavailable anonymous memory cannot produce an empty successful snapshot."""
    with (
        patch.object(mmap, "mmap", side_effect=OSError("mapping unavailable")),
        pytest.raises(OSError, match="mapping unavailable"),
    ):
        snapshot(64)


def test_spill_creation_failure_closes_the_mapping() -> None:
    """A full scratch filesystem must abort and release the already copied pages."""
    with mappings() as allocated:
        with (
            patch.object(tempfile, "TemporaryFile", side_effect=OSError("scratch unavailable")),
            pytest.raises(OSError, match="scratch unavailable"),
            snapshot(4) as stream,
        ):
            stream.write(b"abcd")
            stream.write(b"e")
        assert allocated[0].closed


class ShortWrite(io.BytesIO):
    """Inject a partial disk write while retaining normal resource-close semantics."""

    def write(self, data: Buffer) -> int:
        """A partial write is an explicit failure, not an accepted shorter copy."""
        with memoryview(data) as view:
            return super().write(view[:-1])


@pytest.mark.parametrize("prefix", [b"", b"abcd"])
def test_short_disk_writes_fail_and_release_both_resources(prefix: bytes) -> None:
    """Both prefix transfer and the first oversized write require exact counts."""
    backing = ShortWrite()
    with mappings() as allocated:
        with (
            patch.object(tempfile, "TemporaryFile", return_value=backing),
            pytest.raises(OSError, match="short.*write"),
            snapshot(4) as stream,
        ):
            stream.write(prefix)
            stream.write(b"efghi")
        assert backing.closed and allocated[0].closed


@pytest.mark.parametrize("capacity", [4, 64])
def test_negative_offsets_and_invalid_origin_fail(capacity: int) -> None:
    """Invalid seeks and truncations must remain explicit on either backing store."""
    with snapshot(capacity) as stream:
        stream.write(b"abcdef")
        for offset, origin in ((-1, io.SEEK_SET), (0, 123)):
            with pytest.raises(ValueError):
                stream.seek(offset, origin)
        with pytest.raises(ValueError):
            stream.truncate(-1)


def test_closed_stream_rejects_further_io_and_close_is_idempotent() -> None:
    """Closed mappings cannot be used or reopened through inherited IO methods."""
    stream = snapshot(64)
    stream.close()
    stream.close()
    operations = (lambda: stream.write(b"x"), lambda: stream.readinto(bytearray(1)),
                  lambda: stream.seek(0), lambda: stream.tell(), lambda: stream.truncate(),
                  stream.flush, stream.readable, stream.writable, stream.seekable)
    for operation in operations:
        with pytest.raises(ValueError, match="closed"):
            operation()


@pytest.mark.parametrize("capacity", [4, 64])
def test_readinto_rejects_a_readonly_destination(capacity: int) -> None:
    """Invalid destinations cannot be silently accepted on memory or disk paths."""
    with snapshot(capacity) as stream:
        stream.write(b"abcdef")
        stream.seek(0)
        with pytest.raises(TypeError, match="writable buffer"):
            stream.readinto(b"xx")


class ShortRead(io.BytesIO):
    """Simulate unexpected truncation of the private spill file."""

    def readinto(self, buffer: Buffer) -> int:
        """Expose one fewer byte than the snapshot's declared stable range."""
        with memoryview(buffer) as view:
            return super().readinto(view[:-1])


def test_short_spill_read_fails_instead_of_changing_the_frozen_prefix() -> None:
    """The stored logical length must catch unexpected partial reads from disk."""
    backing = ShortRead()
    with (
        patch.object(tempfile, "TemporaryFile", return_value=backing),
        pytest.raises(OSError, match="short snapshot disk read"),
        snapshot(4) as stream,
    ):
        stream.write(b"abcdef")
        stream.seek(0)
        stream.readinto(bytearray(6))
    assert backing.closed


class FlushFailure(io.BytesIO):
    """Inject a failure while closing spilled storage."""

    def flush(self) -> None:
        """Keep failed finalization visible to the caller."""
        raise OSError("spill flush failed")


def test_flush_failure_still_releases_both_resources() -> None:
    """Cleanup must unmap and close the file even if its flush operation fails."""
    backing = FlushFailure()
    with mappings() as allocated:
        with (
            patch.object(tempfile, "TemporaryFile", return_value=backing),
            pytest.raises(OSError, match="spill flush failed"),
            snapshot(4) as stream,
        ):
            stream.write(b"abcdef")
        assert stream.closed and backing.closed and allocated[0].closed
