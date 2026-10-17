"""Ledger construction validates once, without recursion, with identical results.

The reference below is the original construction: decode every line with
``json.loads``, require an object, walk it recursively for non-finite numbers,
check the sequence and record the envelope. Both the faster screen and the
in-process validated-prefix cache must reproduce it exactly, including every
error message.
"""

from __future__ import annotations

from array import array
import json
import math
import os
from pathlib import Path
import random

import pytest

from hypervector.live import sol_range_onset_ledger as ledger_module
from hypervector.live.sol_range_onset_ledger import SolLiveLedger, SolLiveLedgerError

_FINGERPRINTS = ("a" * 64, "b" * 64)


def _reference_validate(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise SolLiveLedgerError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reference_validate(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            _reference_validate(item, path=f"{path}.{key}")
        return
    raise SolLiveLedgerError(f"{path} contains a non-JSON value")


def _reference_decode(line: str, line_number: int) -> dict[str, object]:
    try:
        value: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SolLiveLedgerError(
            f"live ledger line {line_number} is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SolLiveLedgerError(f"live ledger line {line_number} must be an object")
    _reference_validate(value, path=f"line {line_number}")
    return value


def _reference_construction(path: Path) -> tuple[str, object]:
    """Return the original constructor's sequence and envelope codes, or its error."""
    codes = array("I")
    code_by_key: dict[object, int] = {}
    keys: list[object] = [None]
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise SolLiveLedgerError(f"live ledger line {line_number} is empty")
                record = _reference_decode(line, line_number)
                if record.get("sequence") != line_number:
                    raise SolLiveLedgerError(
                        f"live ledger line {line_number} sequence must equal {line_number}"
                    )
                key = (record.get("event_type"), record.get("profile_fingerprint"))
                try:
                    code = code_by_key.get(key)
                except TypeError:
                    codes.append(0)
                    continue
                if code is None:
                    code = len(keys)
                    code_by_key[key] = code
                    keys.append(key)
                codes.append(code)
    except (SolLiveLedgerError, ValueError) as exc:
        return ("error", f"{type(exc).__name__}: {exc}")
    return ("ok", (len(codes) + 1, list(codes), keys))


def _construction(path: Path) -> tuple[str, object]:
    try:
        ledger = _open(path)
    except (SolLiveLedgerError, ValueError) as exc:
        return ("error", f"{type(exc).__name__}: {exc}")
    return (
        "ok",
        (ledger._next_sequence, list(ledger._envelope_codes), ledger._envelope_keys),
    )


def _open(path: Path, run_id: str = "reader") -> SolLiveLedger:
    return SolLiveLedger(
        path=path,
        profile_id="profile",
        profile_fingerprint=_FINGERPRINTS[0],
        run_fingerprint="r" * 64,
        run_id=run_id,
    )


def _row(sequence: int, rng: random.Random, **override: object) -> str:
    record: dict[str, object] = {
        "schema_version": 1,
        "sequence": sequence,
        "event_type": rng.choice(["heartbeat", "fill", "cohort_snapshot", "fee"]),
        "observed_at_utc": "2026-09-01T00:00:00+00:00",
        "profile_fingerprint": rng.choice(_FINGERPRINTS),
        "payload": {
            "price": rng.uniform(-1e5, 1e5),
            "tiny": rng.choice([1.5e-07, 2.5e-12, 0.0, -0.0]),
            "big": rng.choice([1e16, 3.2e20, 12345678901234567890]),
            "nested": [{"x": rng.random(), "s": "\u00e9\u2603"}, [1, 2.5, None, True]],
        },
    }
    record.update(override)
    return json.dumps(record, ensure_ascii=rng.random() < 0.5)


# Each damage replaces one line's text; ``{n}`` is that line's sequence number.
_DAMAGE = {
    "nan_constant": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":[1,NaN]}}',
    "infinity": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":{{"q":Infinity}}}}',
    "neg_infinity": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":-Infinity}}',
    "overflow_exponent": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":[0.5,1e400]}}',
    "overflow_negative": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":-2.5E+309}}',
    "overflow_digits": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":'
    + "9" * 320
    + '.5}}',
    "underflow_is_finite": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":1e-400}}',
    "long_finite_digits": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f","p":'
    + "1"
    + "0" * 300
    + '.25}}',
    "float_sequence": '{{"sequence":{n}.0,"event_type":"fee","profile_fingerprint":"f"}}',
    "float_event_type": '{{"sequence":{n},"event_type":1.5,"profile_fingerprint":"f"}}',
    "float_fingerprint": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":2.5}}',
    "null_envelope": '{{"sequence":{n},"event_type":null,"profile_fingerprint":null}}',
    "list_event_type": '{{"sequence":{n},"event_type":[1.5,"x"],"profile_fingerprint":"f"}}',
    "bool_sequence": '{{"sequence":true,"event_type":"fee","profile_fingerprint":"f"}}',
    "duplicate_keys": '{{"sequence":0,"event_type":1.5,"sequence":{n},"event_type":"fee",'
    '"profile_fingerprint":"f"}}',
    "invalid_json": '{{"sequence":{n},"event_type":"fee",',
    "invalid_escape": '{{"sequence":{n},"event_type":"f\\x"}}',
    "control_character": '{{"sequence":{n},"event_type":"f\tq"}}',
    "not_object": "[{n}, 1.5]",
    "bom": "\ufeff{{\"sequence\":{n}}}",
    "huge_integer": '{{"sequence":{n},"p":' + "7" * 4400 + "}}",
    "wrong_sequence": '{{"sequence":999999,"event_type":"fee","profile_fingerprint":"f"}}',
    "blank": "   ",
    "carriage_return_split": '{{"sequence":{n},"event_type":"fee",\r"profile_fingerprint":"f"}}',
    "crlf_terminated": '{{"sequence":{n},"event_type":"fee","profile_fingerprint":"f"}}\r',
}


def _history(rng: random.Random, rows: int) -> list[str]:
    return [_row(sequence, rng) for sequence in range(1, rows + 1)]


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(line + "\n" for line in lines).encode("utf-8"))


@pytest.mark.parametrize("damage", sorted(_DAMAGE))
def test_screen_and_fast_decode_match_the_reference_for_every_line(damage: str) -> None:
    """Accepted envelopes, decoded values and refusals are identical line by line."""
    line = _DAMAGE[damage].format(n=7)
    try:
        expected: tuple[str, object] = ("ok", _reference_decode(line, 7))
    except (SolLiveLedgerError, ValueError) as exc:
        expected = ("error", f"{type(exc).__name__}: {exc}")
    for decode in (ledger_module._decode_record, ledger_module._EnvelopeScreen().record):
        try:
            value = decode(line, 7)
        except (SolLiveLedgerError, ValueError) as exc:
            assert expected == ("error", f"{type(exc).__name__}: {exc}"), decode
            continue
        assert expected[0] == "ok", decode
        reference = expected[1]
        assert isinstance(reference, dict)
        if decode is ledger_module._decode_record:
            assert value == reference
        for field in ("sequence", "event_type", "profile_fingerprint"):
            assert value.get(field) == reference.get(field)
            assert type(value.get(field)) is type(reference.get(field))


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("damage", sorted(_DAMAGE))
def test_construction_matches_the_reference_with_and_without_the_cache(
    tmp_path: Path, seed: int, damage: str
) -> None:
    """First, repeated and post-append constructions all equal a full validation."""
    rng = random.Random(seed)
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    lines = _history(rng, 30)
    position = rng.randrange(len(lines))
    head = lines[:position]
    _write(path, head)
    assert _construction(path) == _reference_construction(path)
    damaged = [*lines[position:]]
    damaged[0] = _DAMAGE[damage].format(n=position + 1)
    with path.open("ab") as stream:
        stream.write("".join(line + "\n" for line in damaged).encode("utf-8"))
    expected = _reference_construction(path)
    assert _construction(path) == expected
    assert _construction(path) == expected


def test_float_accuracy_is_preserved_by_fast_reads(tmp_path: Path) -> None:
    """Read paths still return exact float values and refuse non-finite rows."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    rng = random.Random(3)
    _write(path, _history(rng, 25))
    reader = _open(path)
    expected = [
        _reference_decode(line, number)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
    ]
    assert reader.read_all() == expected
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"sequence":26,"payload":{"rows":[{"p":1e999}]}}\n')
    with pytest.raises(SolLiveLedgerError, match=r"line 26.payload.rows\[0\].p contains"):
        reader.read_all()


def test_construction_does_not_walk_rows_recursively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every row is validated without the recursive per-value walk."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    _write(path, _history(random.Random(5), 40))
    walked: list[str] = []
    original = ledger_module._validate_json_value

    def counting(value: object, *, path: str) -> None:
        walked.append(path)
        original(value, path=path)

    monkeypatch.setattr(ledger_module, "_validate_json_value", counting)
    ledger = _open(path)
    assert ledger._next_sequence == 41
    assert walked == []


def test_reconstruction_reuses_the_validated_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second construction decodes only rows appended after the first one."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    rng = random.Random(9)
    _write(path, _history(rng, 50))
    _open(path)
    decoded: list[str] = []
    original = json.JSONDecoder.decode

    def counting(self: json.JSONDecoder, text: str, *args: object) -> object:
        decoded.append(text)
        return original(self, text, *args)

    monkeypatch.setattr(json.JSONDecoder, "decode", counting)
    second = _open(path, run_id="second")
    assert decoded == []
    second.append(
        event_type="heartbeat",
        observed_at_utc="2026-09-01T00:00:00+00:00",
        live_armed=True,
        execution_authority="hyperliquid_mainnet",
        payload={"n": 1.25},
    )
    third = _open(path, run_id="third")
    assert len(decoded) == 1
    monkeypatch.setattr(json.JSONDecoder, "decode", original)
    assert _construction(path) == _reference_construction(path)
    assert third._next_sequence == 52


def test_changed_prefix_bytes_force_full_validation(tmp_path: Path) -> None:
    """In-place damage to already validated rows is still refused on reconstruction."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    _write(path, _history(random.Random(13), 20))
    _open(path)
    content = path.read_bytes()
    damaged = content.replace(b'"sequence": 10,', b'"sequence": 11,', 1)
    assert damaged != content and len(damaged) == len(content)
    path.write_bytes(damaged)
    with pytest.raises(SolLiveLedgerError, match="line 10 sequence must equal 10"):
        _open(path)


def test_truncated_or_replaced_ledgers_are_fully_validated(tmp_path: Path) -> None:
    """A shorter file or a different file at the same path is never trusted."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    rng = random.Random(17)
    _write(path, _history(rng, 20))
    _open(path)
    _write(path, _history(rng, 5))
    assert _open(path)._next_sequence == 6
    replacement = path.with_name("replacement.jsonl")
    _write(replacement, [*_history(rng, 3), '{"sequence": 4, "p": NaN}'])
    os.replace(replacement, path)
    with pytest.raises(SolLiveLedgerError, match="line 4.p contains a non-finite"):
        _open(path)


def test_unterminated_last_row_is_revalidated_after_an_append(tmp_path: Path) -> None:
    """The cached boundary never covers a row that lacks its newline."""
    path = tmp_path / "live/bidirectional_cohort/decisions.jsonl"
    rng = random.Random(19)
    lines = _history(rng, 4)
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    assert _open(path)._next_sequence == 5
    with path.open("a", encoding="utf-8") as stream:
        stream.write(_row(5, rng) + "\n")
    expected = _reference_construction(path)
    assert expected[0] == "error"
    assert _construction(path) == expected


def test_overflow_screen_is_exact_at_the_double_boundary() -> None:
    """Exponent-free literals below 309 characters can never overflow."""
    largest_finite = format(1.7976931348623157e308, ".1f")
    assert len(largest_finite) == 311
    assert not ledger_module._may_overflow(["1" + "9" * 307 + ".5"])
    assert not ledger_module._may_overflow([largest_finite])
    assert ledger_module._may_overflow(["1" + "0" * 309 + ".0"])
    assert ledger_module._may_overflow(["1e309"])
    assert not ledger_module._may_overflow(["1e308", "-1E-999"])
    assert math.isinf(float("1" + "0" * 309 + ".0"))
