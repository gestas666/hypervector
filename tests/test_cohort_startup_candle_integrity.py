"""Offline corruption, publication and source-identity controls."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path

import pandas as pd
import pytest

from cohort_startup_candle_support import OBSERVED_MS, candle_frame
from hypervector.live.cohort_startup_candles import (
    StartupCandleContext, load_startup_candles, write_startup_candles,
)


def context() -> StartupCandleContext:
    """Return one strictly identified offline source contract."""
    return StartupCandleContext(
        "test", "a" * 64, "b" * 64, "run-test", ("xyz:SPCX",),
        OBSERVED_MS - 60_000, OBSERVED_MS, 14.0,
    )


def test_replay_uses_the_authenticated_bytes_even_if_source_changes_during_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-hash file replacement cannot silently substitute replay values."""
    original = candle_frame()
    receipt = write_startup_candles(tmp_path, context(), {"xyz:SPCX": original})
    replacement = original.assign(close=original.close + 0.001)
    output = BytesIO()
    replacement.to_parquet(output, engine="pyarrow", compression="zstd")
    reader = pd.read_parquet

    def replace_before_decode(source: object, **kwargs: object) -> pd.DataFrame:
        """Replace the pathname after authentication, before decoding starts."""
        (receipt.manifest_path.parent / "candles-000.parquet").write_bytes(output.getvalue())
        return reader(source, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", replace_before_decode)
    restored = load_startup_candles(receipt.manifest_path, receipt.manifest_sha256, context())
    pd.testing.assert_frame_equal(original, restored["xyz:SPCX"], check_exact=True)


@pytest.mark.parametrize("mutation", ["manifest", "payload", "missing", "symlink"])
def test_changed_or_missing_evidence_refuses_replay(tmp_path: Path, mutation: str) -> None:
    """Authenticity failures cannot produce a success-shaped replay frame."""
    receipt = write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame()})
    payload = receipt.manifest_path.parent / "candles-000.parquet"
    if mutation == "manifest":
        receipt.manifest_path.write_bytes(receipt.manifest_path.read_bytes() + b" ")
    elif mutation == "payload":
        payload.write_bytes(payload.read_bytes()[:-8])
    elif mutation == "missing":
        payload.unlink()
    else:
        moved = tmp_path / "other.parquet"
        payload.rename(moved)
        payload.symlink_to(moved)
    with pytest.raises((ValueError, FileNotFoundError)):
        load_startup_candles(receipt.manifest_path, receipt.manifest_sha256, context())


@pytest.mark.parametrize("mutation", ["context", "schema", "files", "path", "symbol", "rows"])
def test_malformed_but_hashed_manifest_refuses_replay(tmp_path: Path, mutation: str) -> None:
    """Authenticated bytes still require exact identity and structural coverage."""
    receipt = write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame()})
    manifest = json.loads(receipt.manifest_path.read_bytes())
    if mutation == "context":
        manifest["context"]["observed_at_ms"] += 1
    elif mutation == "schema":
        manifest["schema_version"] += 1
    elif mutation == "files":
        manifest["files"] = []
    elif mutation == "path":
        manifest["files"][0]["path"] = "../outside.parquet"
    elif mutation == "symbol":
        manifest["files"][0]["symbol"] = "BTC"
    else:
        manifest["files"][0]["rows"] += 1
    encoded = json.dumps(manifest).encode()
    receipt.manifest_path.write_bytes(encoded)
    with pytest.raises(ValueError):
        load_startup_candles(receipt.manifest_path, hashlib.sha256(encoded).hexdigest(), context())


@pytest.mark.parametrize("field,value", [
    ("run_id", "another-run"), ("profile_fingerprint", "c" * 64),
    ("run_fingerprint", "c" * 64), ("observed_at_ms", OBSERVED_MS + 1),
])
def test_external_run_binding_cannot_be_substituted(tmp_path: Path, field: str, value: object) -> None:
    """Replay requires the exact context bound by the authoritative ledger."""
    receipt = write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame()})
    with pytest.raises(ValueError, match="context"):
        load_startup_candles(
            receipt.manifest_path, receipt.manifest_sha256, replace(context(), **{field: value}),
        )


def test_duplicate_run_refuses_overwrite(tmp_path: Path) -> None:
    """A conflicting capture preserves the complete previous bundle."""
    receipt = write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame()})
    original = {p.name: p.read_bytes() for p in receipt.manifest_path.parent.iterdir()}
    with pytest.raises(FileExistsError, match="already exists"):
        write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame(4000)})
    assert original == {p.name: p.read_bytes() for p in receipt.manifest_path.parent.iterdir()}


def test_failed_publication_does_not_expose_partial_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unavailable disk leaves neither an apparent final bundle nor partial frames."""
    def fail_sync(_path: Path) -> None:
        """Simulate a durable-write failure before atomic publication."""
        raise OSError("fixture disk unavailable")

    monkeypatch.setattr("hypervector.live.cohort_startup_candles._sync_directory", fail_sync)
    with pytest.raises(OSError, match="disk unavailable"):
        write_startup_candles(tmp_path, context(), {"xyz:SPCX": candle_frame()})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("mutation", ["symbols", "columns", "column_names", "naive", "duplicate", "oversized"])
def test_invalid_input_cannot_be_labeled_complete(tmp_path: Path, mutation: str) -> None:
    """Wrong source coverage and malformed clocks produce actionable errors."""
    frame = candle_frame()
    frames = {"xyz:SPCX": frame}
    if mutation == "symbols":
        frames = {"BTC": frame}
    elif mutation == "columns":
        frames["xyz:SPCX"] = frame.drop(columns="close")
    elif mutation == "column_names":
        frames["xyz:SPCX"] = frame.rename(columns={"close": "open"})
    elif mutation == "naive":
        frame["timestamp"] = frame.timestamp.dt.tz_localize(None)
    elif mutation == "duplicate":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    else:
        frames["xyz:SPCX"] = candle_frame(20_162)
    with pytest.raises(ValueError, match="startup candle"):
        write_startup_candles(tmp_path, context(), frames)


@pytest.mark.parametrize("field,value", [
    ("run_id", ""), ("profile_id", ""), ("profile_fingerprint", "x"),
    ("symbols", ()), ("symbols", ("BTC", "BTC")), ("symbols", ("",)),
    ("activation_time_ms", True), ("activation_time_ms", -1),
    ("observed_at_ms", OBSERVED_MS - 60_001),
    ("requested_lookback_days", 0), ("requested_lookback_days", float("nan")),
])
def test_invalid_capture_context_is_rejected(field: str, value: object) -> None:
    """The recorder cannot stamp invalid identities or impossible timing."""
    with pytest.raises(ValueError, match="startup candle"):
        replace(context(), **{field: value})
