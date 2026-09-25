"""Restart replay skips already-validated rows it cannot select, with identical results.

Six full json decodes of every ledger ran before any engine started. The ledger
constructor's pass stays the single full validation; the recovery passes after it
declare which event types or which profile they select, and rows this instance
already validated outside that declaration are no longer decoded again.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import random

import pytest

from hypervector.live import sol_range_onset_ledger as ledger_module
from hypervector.live import sol_range_onset_startup
from hypervector.live.cohort_durable_decision_recovery import durable_decision_records
from hypervector.live.cohort_funding_recovery import recover_funding_cursor
from hypervector.live.cohort_funding_window import committed_funding_window
from hypervector.live.multi_asset_cohort_history import compatible_execution_rows
from hypervector.live.sol_range_onset_ledger import (
    SOL_LIVE_EVENT_TYPES,
    SolLiveLedger,
    SolLiveLedgerError,
)

_START = datetime(2026, 9, 1, tzinfo=UTC)
_PROFILES = (("profile-a", "a" * 64), ("profile-b", "b" * 64), ("profile-a", "c" * 64))
_TRICKY = (
    "plain",
    '"event_type":"fill"',
    '"profile_fingerprint":"' + "a" * 64 + '"',
    '"event_type":"funding_reconciliation_window","payload":{',
    "}}",
    "unicode é ☃ 𝄞",
    'back\\slash and "quotes"',
    "line\nbreak\r\ttab",
)
_RECOVERY_TELEMETRY = frozenset({"fill", "fee", "funding"})
_DURABLE = frozenset(
    {
        "maximum_hold_decision",
        "provider_exit_decision",
        "profit_lock_decision",
        "adaptive_exit_observation",
    }
)
_FUNDING = frozenset({"configuration_identity", "funding_reconciliation_window"})


def _ledger(path: Path, profile: int, run: str, mode: str = "live") -> SolLiveLedger:
    profile_id, fingerprint = _PROFILES[profile]
    return SolLiveLedger(
        path=path,
        profile_id=profile_id,
        profile_fingerprint=fingerprint,
        run_fingerprint=f"run-{fingerprint[:4]}",
        run_id=run,
        execution_mode=mode,  # type: ignore[arg-type]
    )


def _payload(rng: random.Random, event_type: str, index: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "n": index,
        "price": round(rng.uniform(1.0, 1_000.0), 6),
        "text": rng.choice(_TRICKY),
        "nested": {"levels": [[rng.random(), rng.randint(1, 9)] for _ in range(3)]},
    }
    if event_type == "fill":
        payload["trade_id"] = 10_000 + index
    elif event_type == "fee":
        payload.update(source=rng.choice(["fill", "venue_fee_schedule"]))
        payload["trade_id"] = 10_000 + index
    elif event_type == "funding":
        payload.update(transaction_hash=f"hash-{index}", venue_timestamp_ms=index)
    elif event_type == "adaptive_exit_observation":
        payload["lifecycle_id"] = rng.choice(["life-1", "life-2", "life-3"])
    elif event_type == "funding_reconciliation_window":
        start = 1_790_000_000_000 + index * 1_000
        payload = committed_funding_window(
            start, start + 500, start + 600, 0
        ).as_payload()
    return payload


def _write_history(root: Path, rows: int, seed: int) -> Path:
    """Write mixed runs, profiles and modes through the production writer."""
    rng = random.Random(seed)
    path = root / "live/bidirectional_cohort/decisions.jsonl"
    types = sorted(SOL_LIVE_EVENT_TYPES)
    observed = _START
    for segment in range(6):
        profile = segment % len(_PROFILES)
        mode = "observe" if segment == 4 else "live"
        writer = _ledger(path, profile, f"run-{segment}", mode)
        armed = mode == "live" and segment != 1
        for index in range(rows):
            event_type = rng.choice(types)
            observed += timedelta(seconds=rng.randint(1, 90))
            writer.append(
                event_type=event_type,
                observed_at_utc=observed.isoformat(),
                live_armed=armed,
                execution_authority="hyperliquid_mainnet" if armed else "none",
                payload=_payload(rng, event_type, segment * rows + index),
            )
    return path


_SELECTIONS: tuple[
    tuple[str, Callable[[Mapping[str, object]], bool], dict[str, object]], ...
] = (
    (
        "asset telemetry recovery",
        lambda row: row.get("sequence") == 1
        or row.get("event_type") in _RECOVERY_TELEMETRY,
        {"event_types": _RECOVERY_TELEMETRY},
    ),
    (
        "asset profile recovery",
        lambda row: row.get("profile_fingerprint") == "a" * 64,
        {"profile_fingerprint": "a" * 64},
    ),
    (
        "durable decisions",
        lambda row: row.get("event_type") in _DURABLE,
        {"event_types": _DURABLE},
    ),
    (
        "funding cursor",
        lambda row: row.get("profile_fingerprint") == "a" * 64
        and row.get("event_type") in _FUNDING,
        {"event_types": _FUNDING, "profile_fingerprint": "a" * 64},
    ),
)


@pytest.mark.parametrize("seed", [3, 17, 2026])
@pytest.mark.parametrize("label", [label for label, _, _ in _SELECTIONS])
def test_declared_selection_equals_the_full_validated_read(
    tmp_path: Path, seed: int, label: str
) -> None:
    path = _write_history(tmp_path, rows=60, seed=seed)
    reader = _ledger(path, 0, "reader")
    _, predicate, declared = next(item for item in _SELECTIONS if item[0] == label)

    assert reader.read_matching(predicate, **declared) == reader.read_matching(
        predicate
    )


def test_the_declared_selection_skips_decoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The speedup: rows outside the declaration are not decoded a second time."""
    path = _write_history(tmp_path, rows=60, seed=5)
    reader = _ledger(path, 0, "reader")
    decoded: list[int] = []
    original = ledger_module._decode_record

    def counting(line: str, line_number: int) -> dict[str, object]:
        decoded.append(line_number)
        return original(line, line_number)

    monkeypatch.setattr(ledger_module, "_decode_record", counting)
    selected = reader.read_matching(
        lambda row: row.get("event_type") in _FUNDING, event_types=_FUNDING
    )

    assert 1 in decoded
    assert len(decoded) < 60
    assert len(decoded) >= len(selected)
    decoded.clear()
    reader.read_matching(lambda row: row.get("event_type") in _FUNDING)
    assert len(decoded) == 360


def test_first_row_is_always_decoded_for_the_start_anchor(tmp_path: Path) -> None:
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    writer = _ledger(path, 0, "run")
    for event_type in ("book_observation", "fill", "heartbeat"):
        writer.append(
            event_type=event_type,
            observed_at_utc=_START.isoformat(),
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"trade_id": 7},
        )
    reader = _ledger(path, 0, "reader")
    predicate, declared = _SELECTIONS[0][1], _SELECTIONS[0][2]

    rows = reader.read_matching(predicate, **declared)

    assert [row["event_type"] for row in rows] == ["book_observation", "fill"]


def _raw(sequence: int, event_type: str, fingerprint: str, **extra: object) -> str:
    row = {
        "payload": {"n": sequence},
        "event_type": event_type,
        "schema_version": 1,
        "sequence": sequence,
        "profile_fingerprint": fingerprint,
        "observed_at_utc": _START.isoformat(),
        **extra,
    }
    return json.dumps(row, indent=None) + "\n"


def test_hand_written_rows_select_by_their_decoded_values(tmp_path: Path) -> None:
    """Reordered keys, spacing and a duplicated key select by what JSON decodes."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    path.parent.mkdir(parents=True)
    duplicated = (
        '{"schema_version":1,"sequence":4,"event_type":"heartbeat",'
        '"profile_fingerprint":"' + "b" * 64 + '","payload":{"n":4},'
        '"event_type":"funding_reconciliation_window",'
        '"profile_fingerprint":"' + "a" * 64 + '","payload":{"n":5}}\n'
    )
    path.write_text(
        _raw(1, "heartbeat", "a" * 64)
        + _raw(2, "configuration_identity", "a" * 64)
        + _raw(3, "configuration_identity", "b" * 64)
        + duplicated
        + _raw(5, "heartbeat", "a" * 64),
        encoding="utf-8",
    )
    reader = _ledger(path, 0, "reader")
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]

    rows = reader.read_matching(predicate, **declared)

    assert rows == reader.read_matching(predicate)
    assert [row["sequence"] for row in rows] == [2, 4]
    assert rows[1]["payload"] == {"n": 5}


def test_rows_appended_by_this_instance_are_selected(tmp_path: Path) -> None:
    path = _write_history(tmp_path, rows=20, seed=11)
    reader = _ledger(path, 0, "reader")
    for event_type in ("configuration_identity", "heartbeat"):
        reader.append(
            event_type=event_type,
            observed_at_utc=_START.isoformat(),
            live_armed=True,
            execution_authority="hyperliquid_mainnet",
            payload={"n": 1},
        )
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]

    rows = reader.read_matching(predicate, **declared)

    assert rows == reader.read_matching(predicate)
    assert rows[-1]["run_id"] == "reader"


def test_rows_appended_elsewhere_are_always_decoded(tmp_path: Path) -> None:
    """Only rows this instance validated may be skipped; later rows are checked."""
    path = _write_history(tmp_path, rows=20, seed=13)
    reader = _ledger(path, 0, "reader")
    other = _ledger(path, 1, "other")
    other.append(
        event_type="heartbeat",
        observed_at_utc=_START.isoformat(),
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"n": 1},
    )
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]
    assert reader.read_matching(predicate, **declared) == reader.read_matching(
        predicate
    )

    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"sequence": "not a row"\n')
    with pytest.raises(SolLiveLedgerError, match="invalid JSON"):
        reader.read_matching(predicate, **declared)
    with pytest.raises(SolLiveLedgerError, match="invalid JSON"):
        reader.read_matching(predicate)


def test_a_sequence_break_after_construction_still_raises(tmp_path: Path) -> None:
    path = _write_history(tmp_path, rows=10, seed=19)
    reader = _ledger(path, 0, "reader")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_raw(999, "heartbeat", "b" * 64))
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]

    with pytest.raises(SolLiveLedgerError, match="sequence must equal 61"):
        reader.read_matching(predicate, **declared)


# --------------------------------------------------------------------------- #
# the recovery call sites, before and after
# --------------------------------------------------------------------------- #


def _compare_every_read(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[dict[str, object], bool]]:
    """Also run each read undeclared, recording whether the two results agree."""
    calls: list[tuple[dict[str, object], bool]] = []
    original = SolLiveLedger.read_matching

    def checked(
        self: SolLiveLedger,
        predicate: Callable[[Mapping[str, object]], bool],
        **declared: object,
    ) -> list[dict[str, object]]:
        reference = original(self, predicate)
        selected = original(self, predicate, **declared)  # type: ignore[arg-type]
        calls.append((declared, selected == reference and bool(reference)))
        return reference

    monkeypatch.setattr(SolLiveLedger, "read_matching", checked)
    return calls


def test_recovery_call_sites_declare_and_reproduce_their_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_history(tmp_path, rows=80, seed=23)
    reader = _ledger(path, 0, "reader")
    calls = _compare_every_read(monkeypatch)

    durable_decision_records(reader)
    recover_funding_cursor(reader, "a" * 64)
    compatible_execution_rows(reader)
    try:
        sol_range_onset_startup._profile_recovery_records(reader, "a" * 64)
    except Exception:  # noqa: BLE001 - random history is not a coherent lifecycle
        pass  # The read under test already ran and was recorded.

    assert calls == [
        ({"event_types": _DURABLE}, True),
        ({"event_types": _FUNDING, "profile_fingerprint": "a" * 64}, True),
        ({"profile_fingerprint": "a" * 64}, True),
        ({"profile_fingerprint": "a" * 64}, True),
    ]


def test_telemetry_recovery_declares_and_reproduces_its_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from hypervector.live.sol_range_onset_config import load_sol_range_onset_config
    from hypervector.live.sol_range_onset_live_telemetry import SolLiveTelemetry

    path = _write_history(tmp_path, rows=80, seed=29)
    config = replace(
        load_sol_range_onset_config(
            Path("configs/sol_range_onset_canary.toml"),
            mode="live",
            enabled=True,
            accepts_live_risk=True,
        ),
        live_ledger=path,
    )
    reader = _ledger(path, 0, "reader")
    calls = _compare_every_read(monkeypatch)

    telemetry = SolLiveTelemetry(config=config, ledger=reader, now_fn=lambda: _START)

    assert calls == [({"event_types": _RECOVERY_TELEMETRY}, True)]
    assert telemetry._seen_fills and telemetry._seen_funding


def test_a_file_without_a_final_newline_is_never_skipped(tmp_path: Path) -> None:
    """An append onto an unterminated last row merges the two on one line.

    That merged line is invalid JSON, and the full read rejects it. A declared
    read must reject it too, rather than pass over it by its old envelope.
    """
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        _raw(1, "configuration_identity", "a" * 64)
        + _raw(2, "heartbeat", "b" * 64).rstrip("\n"),
        encoding="utf-8",
    )
    writer = _ledger(path, 0, "writer")
    writer.append(
        event_type="configuration_identity",
        observed_at_utc=_START.isoformat(),
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"n": 3},
    )
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]

    with pytest.raises(SolLiveLedgerError, match="line 2 is invalid JSON"):
        writer.read_matching(predicate)
    with pytest.raises(SolLiveLedgerError, match="line 2 is invalid JSON"):
        writer.read_matching(predicate, **declared)


def test_a_terminated_file_still_skips_after_this_instance_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_history(tmp_path, rows=10, seed=31)
    writer = _ledger(path, 0, "writer")
    writer.append(
        event_type="heartbeat",
        observed_at_utc=_START.isoformat(),
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"n": 1},
    )
    decoded: list[int] = []
    original = ledger_module._decode_record

    def counting(line: str, line_number: int) -> dict[str, object]:
        decoded.append(line_number)
        return original(line, line_number)

    monkeypatch.setattr(ledger_module, "_decode_record", counting)
    predicate, declared = _SELECTIONS[3][1], _SELECTIONS[3][2]

    rows = writer.read_matching(predicate, **declared)

    assert len(decoded) < 61
    monkeypatch.setattr(ledger_module, "_decode_record", original)
    assert rows == writer.read_matching(predicate)
