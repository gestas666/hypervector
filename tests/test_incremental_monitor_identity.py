"""Following telemetry must not replay an entire live ledger at every refresh."""

from pathlib import Path

import pytest

from hypervector.live.cohort_monitor_identity import LedgerIdentityReader
from test_cohort_monitor_stale_attachment import _config, _write_ledger


def test_unchanged_identity_reuses_the_validated_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Once read, an unchanged ledger requires only a metadata check."""
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger)
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    reader = LedgerIdentityReader(config)
    first = reader.read()
    monkeypatch.setattr(
        Path, "open", lambda *_a, **_k: pytest.fail("reread unchanged ledger")
    )
    assert reader.read() == first


def test_monitor_reader_rejects_truncation(tmp_path: Path) -> None:
    """A reset ledger needs a new attachment rather than a cached run identity."""
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger)
    reader = LedgerIdentityReader(
        _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    )
    reader.read()
    ledger.write_bytes(b"")
    with pytest.raises(ValueError, match="changed|truncated"):
        reader.read()


def test_replacement_between_stat_and_open_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pathname race cannot silently substitute a new ledger attachment."""
    ledger = tmp_path / "ledger.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    _write_ledger(ledger)
    _write_ledger(replacement)
    reader = LedgerIdentityReader(
        _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    )
    original = Path.open

    def replace_before_open(path: Path, *args: object, **kwargs: object) -> object:
        if path == ledger and replacement.exists():
            replacement.replace(ledger)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replace_before_open)
    with pytest.raises(ValueError, match="changed|truncated"):
        reader.read()
