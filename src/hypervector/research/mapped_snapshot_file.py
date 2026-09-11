"""Seekable snapshot storage with anonymous pages and an exact temporary-file spill."""

from __future__ import annotations

from collections.abc import Buffer
from contextlib import ExitStack
import io
import mmap
import tempfile
from typing import BinaryIO

_ZERO_CHUNK_BYTES = 64 * 1024


def _write_exact(target: BinaryIO, data: memoryview) -> None:
    if target.write(data) != len(data):
        raise OSError("short snapshot disk write; frozen bytes are incomplete")


class MappedSnapshotFile(io.RawIOBase):
    """Keep bounded raw bytes outside the heap and unmap them on spill or close."""

    def __init__(self, capacity: int) -> None:
        """Allocate anonymous address space; pages are populated only as written."""
        super().__init__()
        self._resources = ExitStack()
        self._disk: BinaryIO | None = None
        self._position = 0
        self._length = 0
        self._capacity = capacity
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValueError("snapshot memory capacity must be a positive integer")
        self._memory = self._resources.enter_context(mmap.mmap(-1, capacity))

    def _require_open(self) -> None:
        if self.closed:
            raise ValueError("snapshot stream is closed")

    def readable(self) -> bool:
        """Expose binary read capability while the snapshot is open."""
        self._require_open()
        return True

    def writable(self) -> bool:
        """Allow captured bytes to be copied into the open snapshot."""
        self._require_open()
        return True

    def seekable(self) -> bool:
        """Allow hashing and parsing to revisit the same frozen prefix."""
        self._require_open()
        return True

    def tell(self) -> int:
        """Return the logical byte cursor rather than the mapping capacity."""
        self._require_open()
        return self._position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        """Move the byte cursor with ordinary file offset semantics."""
        self._require_open()
        origins = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self._length}
        if whence not in origins:
            raise ValueError("invalid snapshot seek origin")
        target = origins[whence] + offset
        if target < 0:
            raise ValueError("snapshot seek offset must be nonnegative")
        if self._disk is not None:
            self._disk.seek(target)
        self._position = target
        return target

    def write(self, data: Buffer) -> int:
        """Write exact bytes, transferring the frozen prefix to disk on overflow."""
        self._require_open()
        with memoryview(data) as original, original.cast("B") as source:
            if not source:
                return 0
            end = self._position + len(source)
            if self._disk is None and end > self._capacity:
                self._spill()
            if self._disk is not None:
                _write_exact(self._disk, source)
            else:
                self._memory[self._position:end] = source
            self._position = end
            self._length = max(self._length, end)
            return len(source)

    def readinto(self, buffer: Buffer) -> int:
        """Read only logical snapshot bytes without copying the entire mapping."""
        self._require_open()
        with memoryview(buffer) as original, original.cast("B") as target:
            if target.readonly:
                raise TypeError("snapshot readinto requires a writable buffer")
            count = min(len(target), max(0, self._length - self._position))
            if not count:
                return 0
            if self._disk is not None:
                with target[:count] as requested:
                    if self._disk.readinto(requested) != count:
                        raise OSError("short snapshot disk read; frozen bytes are incomplete")
            else:
                with memoryview(self._memory) as source:
                    target[:count] = source[self._position:self._position + count]
            self._position += count
            return count

    def truncate(self, size: int | None = None) -> int:
        """Set logical EOF and prevent discarded tail bytes from reappearing."""
        self._require_open()
        length = self._position if size is None else size
        if length < 0:
            raise ValueError("snapshot length must be nonnegative")
        if self._disk is None and length > self._capacity:
            self._spill()
        if self._disk is not None:
            self._disk.truncate(length)
        elif length < self._length:
            self._clear_tail(length)
        self._length = length
        return length

    def _clear_tail(self, start: int) -> None:
        while start < self._length:
            end = min(start + _ZERO_CHUNK_BYTES, self._length)
            self._memory[start:end] = bytes(end - start)
            start = end

    def _spill(self) -> None:
        backing = self._resources.enter_context(tempfile.TemporaryFile(mode="w+b"))
        with memoryview(self._memory) as memory, memory[:self._length] as prefix:
            _write_exact(backing, prefix)
        backing.seek(self._position)
        self._memory.close()
        self._disk = backing

    def flush(self) -> None:
        """Flush spilled bytes; anonymous pages need no external synchronization."""
        self._require_open()
        if self._disk is not None:
            self._disk.flush()

    def close(self) -> None:
        """Release every owned mapping and file even if flushing fails."""
        try:
            super().close()
        finally:
            self._resources.close()
