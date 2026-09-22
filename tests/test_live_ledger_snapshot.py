"""Stable-prefix behavior for actively appended live decision ledgers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hypervector.research import live_ledger_snapshot
from hypervector.research.live_ledger_snapshot import snapshot_decision_ledger


def _line(sequence: int) -> bytes:
    return (json.dumps({"sequence": sequence, "payload": {}}) + "\n").encode()


def _run_line(
    sequence: int,
    run_id: str,
    event_type: str,
) -> bytes:
    return (
        json.dumps(
            {
                "sequence": sequence,
                "event_type": event_type,
                "run_id": run_id,
                "live_armed": True,
                "execution_authority": "hyperliquid_mainnet",
                "payload": {},
            }
        )
        + "\n"
    ).encode()


def _identity_line(
    sequence: int,
    run_id: str,
    *,
    profile_id: str,
    profile_fingerprint: str,
    run_fingerprint: str,
) -> bytes:
    return (
        json.dumps(
            {
                "sequence": sequence,
                "event_type": "configuration_identity",
                "run_id": run_id,
                "profile_id": profile_id,
                "profile_fingerprint": profile_fingerprint,
                "run_fingerprint": run_fingerprint,
                "live_armed": True,
                "execution_authority": "hyperliquid_mainnet",
                "payload": {},
            }
        )
        + "\n"
    ).encode()


def _compatible_history() -> tuple[bytes, bytes, bytes, bytes]:
    old = _identity_line(
        1,
        "run-old",
        profile_id="profile-old",
        profile_fingerprint="profile-fp-old",
        run_fingerprint="run-fp-old",
    ) + _run_line(2, "run-old", "heartbeat")
    first = _identity_line(
        3,
        "run-compatible",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    ) + _run_line(4, "run-compatible", "fill")
    intervening = _identity_line(
        5,
        "run-intervening",
        profile_id="profile-other",
        profile_fingerprint="profile-fp-other",
        run_fingerprint="run-fp-other",
    ) + _run_line(6, "run-intervening", "heartbeat")
    current = _identity_line(
        7,
        "run-current",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    ) + _run_line(8, "run-current", "position")
    return old, first, intervening, current


def test_complete_ledger_preserves_all_rows_and_reports_source_bytes(
    tmp_path: Path,
) -> None:
    """A complete file has identical observed and stable evidence."""
    path = tmp_path / "decisions.jsonl"
    content = _line(1) + _line(2)
    path.write_bytes(content)

    with snapshot_decision_ledger(path) as (rows, evidence):
        assert [row["sequence"] for row in rows] == [1, 2]
        assert evidence == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }


def test_strict_snapshot_rejects_incomplete_final_record(tmp_path: Path) -> None:
    """Final immutable audits cannot silently accept a torn ledger tail."""
    path = tmp_path / "decisions.jsonl"
    path.write_bytes(_line(1) + b'{"sequence":2')

    with pytest.raises(ValueError, match="incomplete trailing JSONL record"):
        with snapshot_decision_ledger(path):
            pass


def test_rolling_snapshot_drops_only_incomplete_tail(tmp_path: Path) -> None:
    """A rolling reader retains complete rows and discloses the torn suffix."""
    path = tmp_path / "decisions.jsonl"
    suffix = b'{"sequence":2'
    path.write_bytes(_line(1) + suffix)

    with snapshot_decision_ledger(
        path,
        allow_incomplete_tail=True,
    ) as (rows, evidence):
        assert [row["sequence"] for row in rows] == [1]
        assert evidence["source_bytes_observed"] == len(_line(1) + suffix)
        assert evidence["stable_bytes"] == len(_line(1))
        assert evidence["bytes"] == len(_line(1))
        assert evidence["dropped_tail_bytes"] == len(suffix)
        assert evidence["incomplete_tail_dropped"] is True


def test_latest_armed_run_snapshot_excludes_prior_run_bytes(tmp_path: Path) -> None:
    """The rolling cockpit reads only the latest armed run's stable suffix."""
    path = tmp_path / "decisions.jsonl"
    old = _run_line(1, "run-old", "configuration_identity") + _run_line(
        2, "run-old", "heartbeat"
    )
    current = _run_line(1, "run-current", "configuration_identity") + _run_line(
        2, "run-current", "heartbeat"
    )
    path.write_bytes(old + current)

    with snapshot_decision_ledger(
        path,
        latest_armed_run=True,
    ) as (rows, evidence):
        assert [row["run_id"] for row in rows] == ["run-current", "run-current"]
        assert evidence["source_start_offset"] == len(old)
        assert evidence["selected_run_id"] == "run-current"
        assert evidence["source_bytes_observed"] == len(old + current)
        assert evidence["bytes"] == len(current)


def test_explicit_run_snapshot_requires_matching_configuration_identity(
    tmp_path: Path,
) -> None:
    """Asset snapshots bind to the cohort run rather than a neighboring run."""
    path = tmp_path / "btc.jsonl"
    path.write_bytes(
        _run_line(1, "run-old", "configuration_identity")
        + _run_line(1, "run-current", "configuration_identity")
        + _run_line(2, "run-current", "position")
    )

    with snapshot_decision_ledger(path, run_id="run-current") as (rows, evidence):
        assert [row["event_type"] for row in rows] == [
            "configuration_identity",
            "position",
        ]
        assert evidence["selected_run_id"] == "run-current"

    with pytest.raises(ValueError, match="configuration identity not found"):
        with snapshot_decision_ledger(path, run_id="missing"):
            pass


def test_compatible_execution_snapshot_starts_at_earliest_matching_identity(
    tmp_path: Path,
) -> None:
    """A rolling audit keeps adopted history without decoding older contracts."""
    path = tmp_path / "btc.jsonl"
    old, first_compatible, intervening, current = _compatible_history()
    path.write_bytes(old + first_compatible + intervening + current)

    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path,
        run_id="run-current",
    ) as (rows, evidence):
        assert [row["sequence"] for row in rows] == [1, 2, 3, 4, 5, 6]
        assert [row["run_id"] for row in rows] == [
            "run-compatible",
            "run-compatible",
            "run-intervening",
            "run-intervening",
            "run-current",
            "run-current",
        ]
        assert evidence["snapshot_scope"] == "compatible_execution_history"
        assert evidence["selected_run_id"] == "run-current"
        assert evidence["selected_profile_id"] == "profile-current"
        assert evidence["selected_profile_fingerprint"] == "profile-fp-current"
        assert evidence["selected_run_fingerprint"] == "run-fp-current"
        assert evidence["source_start_offset"] == len(old)
        assert evidence["source_sequence_start"] == 3
        assert evidence["source_sequence_end"] == 8
        assert evidence["source_bytes_observed"] == len(
            old + first_compatible + intervening + current
        )
        assert evidence["bytes"] == len(first_compatible + intervening + current)


def test_compatible_execution_snapshot_reuses_validated_start_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Later rolling snapshots must not rescan immutable historical bytes."""
    path = tmp_path / "btc.jsonl"
    old = _identity_line(
        1,
        "run-old",
        profile_id="profile-old",
        profile_fingerprint="profile-fp-old",
        run_fingerprint="run-fp-old",
    )
    current = _identity_line(
        2,
        "run-current",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    )
    path.write_bytes(old + current)
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ) as (_, first_evidence):
        assert first_evidence["source_start_offset_cache_hit"] is False

    def unexpected_scan(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("compatible execution history was rescanned")

    monkeypatch.setattr(
        live_ledger_snapshot,
        "_earliest_identity_offset",
        unexpected_scan,
    )
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ) as (rows, evidence):
        assert [row["run_id"] for row in rows] == ["run-current"]
        assert evidence["source_start_offset"] == len(old)
        assert evidence["source_start_offset_cache_hit"] is True


def test_compatible_execution_snapshot_rejects_cached_source_truncation(
    tmp_path: Path,
) -> None:
    """A cached boundary cannot hide removal of already observed suffix bytes."""
    path = tmp_path / "btc.jsonl"
    old = _identity_line(
        1,
        "run-old",
        profile_id="profile-old",
        profile_fingerprint="profile-fp-old",
        run_fingerprint="run-fp-old",
    )
    current = _identity_line(
        2,
        "run-current",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    )
    position = _run_line(3, "run-current", "position")
    path.write_bytes(old + current + position)
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ):
        pass

    path.write_bytes(old + current)

    with pytest.raises(ValueError, match="truncated after caching"):
        with live_ledger_snapshot.snapshot_compatible_execution_ledger(
            path, run_id="run-current"
        ):
            pass


def test_compatible_execution_snapshot_caches_zero_start_boundary(
    tmp_path: Path,
) -> None:
    """A compatible identity at byte zero must retain cache provenance."""
    path = tmp_path / "btc.jsonl"
    path.write_bytes(
        _identity_line(
            1,
            "run-current",
            profile_id="profile-current",
            profile_fingerprint="profile-fp-current",
            run_fingerprint="run-fp-current",
        )
    )

    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ) as (_, first):
        assert first["source_start_offset_cache_hit"] is False
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ) as (_, second):
        assert second["source_start_offset_cache_hit"] is True


def test_compatible_execution_snapshot_rejects_replaced_cached_source(
    tmp_path: Path,
) -> None:
    """Replacing an append-only source cannot inherit its cached boundary."""
    path = tmp_path / "btc.jsonl"
    content = _identity_line(
        1,
        "run-current",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    )
    path.write_bytes(content)
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ):
        pass
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(content)
    replacement.replace(path)

    with pytest.raises(ValueError, match="identity changed after caching"):
        with live_ledger_snapshot.snapshot_compatible_execution_ledger(
            path, run_id="run-current"
        ):
            pass


def test_compatible_execution_snapshot_rejects_changed_cached_boundary(
    tmp_path: Path,
) -> None:
    """A same-identity mutation at the cached start row must fail closed."""
    path = tmp_path / "btc.jsonl"
    content = _identity_line(
        1,
        "run-current",
        profile_id="profile-current",
        profile_fingerprint="profile-fp-current",
        run_fingerprint="run-fp-current",
    )
    path.write_bytes(content)
    with live_ledger_snapshot.snapshot_compatible_execution_ledger(
        path, run_id="run-current"
    ):
        pass
    path.write_bytes(content.replace(b'"payload": {}', b'"payload": {"x": 1}'))

    with pytest.raises(ValueError, match="boundary changed after caching"):
        with live_ledger_snapshot.snapshot_compatible_execution_ledger(
            path, run_id="run-current"
        ):
            pass


def test_every_reverse_reader_ignores_a_torn_final_line(tmp_path: Path) -> None:
    """`_reverse_complete_lines` promises complete lines; it must deliver them.

    The guard was added at one call site only, so the sibling readers that share
    this generator still parsed a partially written final record.
    """
    path = tmp_path / "decisions.jsonl"
    complete = _line(1) + _line(2)
    path.write_bytes(complete + b'{"sequence":3, "payl')

    located = list(live_ledger_snapshot._reverse_complete_lines(path))

    assert [json.loads(raw)["sequence"] for _offset, raw in located] == [2, 1]
    assert all(offset + len(raw) < len(complete) + 1 for offset, raw in located)


def test_a_newline_terminated_ledger_yields_every_record(tmp_path: Path) -> None:
    """Skipping the tail must never drop a legitimately terminated final row."""
    path = tmp_path / "decisions.jsonl"
    path.write_bytes(_line(1) + _line(2) + _line(3))

    located = list(live_ledger_snapshot._reverse_complete_lines(path))

    assert [json.loads(raw)["sequence"] for _offset, raw in located] == [3, 2, 1]
