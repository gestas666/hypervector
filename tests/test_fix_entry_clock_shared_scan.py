"""Clocks on one ledger share a single scan with per-clock-identical results.

The reference below is the original per-clock algorithm, kept verbatim so the
shared scan is compared against what every clock used to compute on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random

import pytest

from hypervector.live import cohort_candidate_entry_clock as clock_module
from hypervector.live.cohort_candidate_entry_clock import (
    AcceptedEntryClock,
    CandidateEntryClockStateError,
)

_STRATEGIES = ("btc_structural", "hype_relaxed", "sol_aligned", "other\u00e9")
_SYMBOLS = ("BTC", "HYPE", "SOL")
_PAIRS = [(strategy, symbol) for strategy in _STRATEGIES for symbol in _SYMBOLS]


class _ReferenceError(Exception):
    pass


def _reference_latest(path: Path, strategy_id: str, symbol: str) -> int | None:
    """Scan a whole ledger exactly as one pre-sharing clock did."""
    pieces = path.read_bytes().split(b"\n")
    encoded_rows = [piece + b"\n" for piece in pieces[:-1]] + [p for p in pieces[-1:] if p]
    latest: int | None = None
    for line_number, encoded in enumerate(encoded_rows, start=1):
        if not encoded.endswith(b"\n"):
            raise _ReferenceError("candidate recovery ledger has an incomplete final row")
        try:
            raw = encoded.decode("utf-8")
        except UnicodeDecodeError:
            raise _ReferenceError("candidate recovery ledger is not valid UTF-8") from None
        try:
            row: object = json.loads(raw)
        except json.JSONDecodeError:
            raise _ReferenceError(
                f"candidate recovery ledger line {line_number} is invalid JSON"
            ) from None
        if not isinstance(row, dict):
            raise _ReferenceError(
                f"candidate recovery ledger line {line_number} must be an object"
            )
        if _reference_contains(row, strategy_id, symbol):
            latest = max(_reference_observed_ms(row, line_number), latest or 0)
    return latest


def _reference_contains(row: Mapping[str, object], strategy_id: str, symbol: str) -> bool:
    if row.get("event_type") != "intent_routing":
        return False
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise _ReferenceError("candidate intent_routing payload must be an object")
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise _ReferenceError("candidate intent_routing actions must be a list")
    for action in actions:
        if not isinstance(action, dict):
            raise _ReferenceError("candidate intent_routing action must be an object")
        if (
            action.get("action") == "enter"
            and action.get("strategy_id") == strategy_id
            and action.get("symbol") == symbol
        ):
            return True
    return False


def _reference_observed_ms(row: Mapping[str, object], line_number: int) -> int:
    raw = row.get("observed_at_utc")
    if not isinstance(raw, str):
        raise _ReferenceError(
            f"candidate recovery ledger line {line_number} lacks observed_at_utc"
        )
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise _ReferenceError(
            f"candidate recovery ledger line {line_number} has invalid observed_at_utc"
        ) from None
    if observed.tzinfo is None:
        raise _ReferenceError(
            f"candidate recovery ledger line {line_number} time must be timezone-aware"
        )
    return int(observed.astimezone(timezone.utc).timestamp() * 1_000)


def _reference_outcome(path: Path, pair: tuple[str, str]) -> tuple[str, object]:
    try:
        return ("latest", _reference_latest(path, *pair))
    except _ReferenceError as exc:
        return ("error", str(exc))


def _clock_outcome(clock: AcceptedEntryClock | None, path: Path, pair) -> tuple[str, object]:
    try:
        if clock is None:
            clock = AcceptedEntryClock(path, strategy_id=pair[0], symbol=pair[1])
        else:
            clock.refresh()
    except CandidateEntryClockStateError as exc:
        return ("error", str(exc))
    return ("latest", clock.latest_ms)


def _routing(actions: list[object], observed: object, *, escaped: bool = False) -> str:
    row = {
        "event_type": "intent_routing",
        "observed_at_utc": observed,
        "payload": {"actions": actions, "note": "q\"uote" if escaped else "plain"},
    }
    return json.dumps(row, separators=(",", ":"), ensure_ascii=escaped)


def _enter(pair: tuple[str, str], action: str = "enter") -> dict[str, object]:
    return {"action": action, "strategy_id": pair[0], "symbol": pair[1], "size": 1.25}


def _valid_rows(rng: random.Random, count: int) -> list[str]:
    rows = []
    for index in range(count):
        minute = 1_000 + index
        observed = f"2026-08-04T{(minute // 60) % 24:02d}:{minute % 60:02d}:00+00:00"
        draw = rng.random()
        if draw < 0.45:
            actions = [
                _enter(rng.choice(_PAIRS), rng.choice(["enter", "enter", "skip"]))
                for _ in range(rng.randrange(1, 4))
            ]
            rows.append(_routing(actions, observed, escaped=rng.random() < 0.3))
        elif draw < 0.6:
            rows.append(
                json.dumps(
                    {"event_type": "intent_\\u0072outing", "payload": {"actions": []}}
                ).replace("\\\\", "\\")
            )
        else:
            rows.append(
                json.dumps(
                    {
                        "event_type": rng.choice(["heartbeat", "cohort_snapshot"]),
                        "payload": {"mark": rng.uniform(-1e6, 1e6), "x": [1.5e-07, 2, None]},
                        "note": "mentions intent_routing" if rng.random() < 0.1 else "",
                    },
                    separators=(",", ":"),
                )
            )
    return rows


_DAMAGE = {
    "observed_missing": lambda pair: _routing([_enter(pair)], None),
    "observed_naive": lambda pair: _routing([_enter(pair)], "2026-08-04T10:00:00"),
    "observed_bad": lambda pair: _routing([_enter(pair)], "nonsense"),
    "action_after_match": lambda pair: _routing([_enter(pair), 7], "2026-08-04T11:00:00Z"),
    "action_before_match": lambda pair: _routing([None, _enter(pair)], "2026-08-04T11:00:00Z"),
    "payload_not_object": lambda pair: json.dumps({"event_type": "intent_routing", "payload": []}),
    "actions_not_list": lambda pair: json.dumps(
        {"event_type": "intent_routing", "payload": {"actions": {}}}
    ),
    "invalid_json": lambda pair: '{"event_type":"heartbeat",',
    "not_object": lambda pair: "[1, 2.5]",
    "nan_allowed": lambda pair: '{"event_type":"heartbeat","v":NaN,"w":1e999}',
    "bom": lambda pair: "\ufeff{}",
    "escaped_routing": lambda pair: _routing([_enter(pair)], "2026-08-05T00:00:00Z").replace(
        "intent_routing", "intent\\u005frouting"
    ),
    "pre_epoch": lambda pair: _routing([_enter(pair)], "1969-12-31T23:59:00+00:00"),
}


def _write(path: Path, rows: list[str]) -> None:
    path.write_bytes("".join(row + "\n" for row in rows).encode("utf-8"))


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("damage", sorted(_DAMAGE))
def test_shared_clocks_match_independent_reference(
    tmp_path: Path, seed: int, damage: str
) -> None:
    """Every pair publishes or raises exactly what an independent clock did."""
    rng = random.Random(seed * 1_000 + len(damage))
    ledger = tmp_path / "decisions.jsonl"
    rows = _valid_rows(rng, 40)
    damaged_pair = rng.choice(_PAIRS)
    rows.insert(rng.randrange(len(rows) + 1), _DAMAGE[damage](damaged_pair))
    head, tail = rows[: len(rows) // 2], rows[len(rows) // 2 :]
    _write(ledger, head)
    clocks = {}
    for pair in _PAIRS:
        outcome = _clock_outcome(None, ledger, pair)
        assert outcome == _reference_outcome(ledger, pair), pair
        if outcome[0] == "latest":
            clocks[pair] = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    with ledger.open("ab") as stream:
        stream.write("".join(row + "\n" for row in tail).encode("utf-8"))
    for pair in _PAIRS:
        expected = _reference_outcome(ledger, pair)
        assert _clock_outcome(clocks.get(pair), ledger, pair) == expected, pair
        assert _clock_outcome(None, ledger, pair) == expected, pair


def test_clocks_on_one_ledger_decode_each_row_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three providers on one ledger cost one pass, not one pass per clock."""
    ledger = tmp_path / "decisions.jsonl"
    rows = _valid_rows(random.Random(7), 300)
    _write(ledger, rows)
    original = clock_module._complete_utf8_row
    decoded: list[bytes] = []

    def counting(encoded: bytes) -> str:
        decoded.append(encoded)
        return original(encoded)

    monkeypatch.setattr(clock_module, "_complete_utf8_row", counting)
    clocks = [
        AcceptedEntryClock(ledger, strategy_id=strategy, symbol=symbol)
        for strategy, symbol in _PAIRS[:3]
    ]
    assert len(decoded) == len(rows)
    with ledger.open("ab") as stream:
        stream.write((_routing([_enter(_PAIRS[0])], "2026-09-01T00:00:00Z") + "\n").encode())
    for clock in clocks:
        clock.refresh()
    assert len(decoded) == len(rows) + 1
    assert clocks[0].latest_ms == 1_788_220_800_000
    for clock, pair in zip(clocks, _PAIRS[:3], strict=True):
        assert clock.latest_ms == _reference_latest(ledger, *pair)


def test_early_match_before_malformed_action_keeps_per_clock_outcomes(
    tmp_path: Path,
) -> None:
    """A clock that matched first still succeeds while every other clock fails."""
    ledger = tmp_path / "decisions.jsonl"
    matched, other = _PAIRS[0], _PAIRS[1]
    _write(ledger, [_routing([_enter(matched), "bad"], "2026-08-04T20:00:00Z")])
    clock = AcceptedEntryClock(ledger, strategy_id=matched[0], symbol=matched[1])
    assert clock.latest_ms == 1_785_873_600_000
    with pytest.raises(CandidateEntryClockStateError, match="action must be an object"):
        AcceptedEntryClock(ledger, strategy_id=other[0], symbol=other[1])


def test_pair_failure_precedes_a_later_row_failure(tmp_path: Path) -> None:
    """The first failure on the ledger wins, per pair, as in an independent scan."""
    ledger = tmp_path / "decisions.jsonl"
    pair = _PAIRS[0]
    _write(ledger, [_routing([_enter(pair)], "2026-08-04T20:00:00"), "not json"])
    with pytest.raises(CandidateEntryClockStateError, match="timezone-aware"):
        AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    with pytest.raises(CandidateEntryClockStateError, match="line 2 is invalid JSON"):
        AcceptedEntryClock(ledger, strategy_id=_PAIRS[1][0], symbol=_PAIRS[1][1])


def test_rewritten_ledger_starts_a_fresh_scan_for_new_clocks(tmp_path: Path) -> None:
    """A truncated or replaced file is rescanned by new clocks and refused by old ones."""
    ledger = tmp_path / "decisions.jsonl"
    pair = _PAIRS[0]
    _write(
        ledger,
        [
            _routing([_enter(pair)], "2026-08-04T20:00:00Z"),
            _routing([_enter(pair)], "2026-08-04T21:00:00Z"),
        ],
    )
    old = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    _write(ledger, [_routing([_enter(pair)], "2026-08-04T19:00:00Z")])
    fresh = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    assert fresh.latest_ms == 1_785_870_000_000
    with pytest.raises(CandidateEntryClockStateError, match="truncated"):
        old.refresh()
    replacement = tmp_path / "replacement.jsonl"
    _write(
        replacement,
        [
            _routing([_enter(pair)], "2026-08-04T18:00:00Z"),
            _routing([_enter(pair)], "2026-08-04T18:30:00Z"),
        ],
    )
    os.replace(replacement, ledger)
    replaced = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    assert replaced.latest_ms == 1_785_868_200_000


def test_same_size_rewrite_is_not_mistaken_for_the_consumed_prefix(
    tmp_path: Path,
) -> None:
    """New clocks rescan when consumed boundary bytes no longer match."""
    ledger = tmp_path / "decisions.jsonl"
    pair = _PAIRS[0]
    _write(ledger, [_routing([_enter(pair)], "2026-08-04T20:00:00Z")])
    first = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    with ledger.open("r+b") as stream:
        content = stream.read()
        stream.seek(0)
        stream.write(content.replace(b"T20:", b"T08:"))
    second = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    assert first.latest_ms == 1_785_873_600_000
    assert second.latest_ms == 1_785_830_400_000


def test_middle_rewrite_is_refused_by_a_later_clock(tmp_path: Path) -> None:
    """A later clock joins only a byte-identical prefix, not just matching ends."""
    ledger = tmp_path / "decisions.jsonl"
    pair = _PAIRS[0]
    padding = json.dumps({"event_type": "heartbeat", "pad": "x" * 9_000})
    _write(
        ledger,
        [padding, _routing([_enter(pair)], "2026-08-04T20:00:00Z"), padding],
    )
    first = AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    with ledger.open("r+b") as stream:
        content = stream.read()
        stream.seek(0)
        stream.write(content.replace(b"T20:00:00Z", b"T20:00:00 "))
    with pytest.raises(CandidateEntryClockStateError, match="line 2 has invalid observed_at_utc"):
        AcceptedEntryClock(ledger, strategy_id=pair[0], symbol=pair[1])
    first.refresh()
    assert first.latest_ms == 1_785_873_600_000
