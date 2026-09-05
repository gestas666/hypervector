"""Report-only periodic HIP-3 mark snapshot recorder tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import json

from hypervector.data.event_archive import EventArchive
from hypervector.data.hip3_mark_snapshot_recorder import (
    HIP3_REST_MARK_SOURCE,
    Hip3MarkRecorderConfig,
    run_hip3_mark_recorder,
)

_SYMBOLS = ("xyz:SP500", "xyz:SPCX")
_RECEIVED_NS = 1_800_000_000_123_456_789


class _Info:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, path: str, payload: dict[str, object]) -> object:
        self.calls.append((path, payload))
        return self.response


def test_bounded_recorder_archives_exact_rest_mark_receipts(tmp_path: Path) -> None:
    """One public response produces exact immutable rows for both symbols."""
    info = _Info(_response())
    statuses: list[dict[str, object]] = []
    config = Hip3MarkRecorderConfig(
        symbols=_SYMBOLS,
        data_root=tmp_path,
        poll_seconds=4.0,
        max_polls=1,
    )

    polls = run_hip3_mark_recorder(
        config,
        info=info,
        clock_ns=lambda: _RECEIVED_NS,
        sleeper=lambda _seconds: None,
        status_sink=statuses.append,
    )

    assert polls == 1
    assert info.calls == [("/info", {"type": "metaAndAssetCtxs", "dex": "xyz"})]
    assert statuses[-1]["execution_authority"] == "none"
    for symbol, expected in zip(_SYMBOLS, (7_801.8, 142.22), strict=True):
        rows = EventArchive(
            data_root=tmp_path,
            symbol=symbol,
            batch_size=100,
        ).replay_asset_contexts()
        assert len(rows) == 1
        assert rows[0].symbol == symbol
        assert rows[0].mark_price == expected
        assert rows[0].received_ts_ns == _RECEIVED_NS
        assert rows[0].source == HIP3_REST_MARK_SOURCE


def test_recorder_rejects_ambiguous_or_misaligned_contexts(tmp_path: Path) -> None:
    """Metadata/context position drift cannot silently relabel a mark."""
    response = _response()
    response[0]["universe"].append({"name": "xyz:SP500"})
    response[1].append(dict(response[1][0]))
    config = Hip3MarkRecorderConfig(_SYMBOLS, tmp_path, max_polls=1)

    try:
        run_hip3_mark_recorder(
            config,
            info=_Info(response),
            clock_ns=lambda: _RECEIVED_NS,
            sleeper=lambda _seconds: None,
            status_sink=lambda _row: None,
        )
    except ValueError as exc:
        assert "exactly once" in str(exc)
    else:
        raise AssertionError("ambiguous HIP-3 metadata must fail closed")


def test_command_preserves_exact_two_symbol_report_only_scope(tmp_path: Path) -> None:
    """CLI configuration cannot acquire broader symbols or live authority."""
    script = _script()
    args = script.build_parser().parse_args(
        [
            "--symbol",
            "xyz:SP500",
            "--symbol",
            "xyz:SPCX",
            "--data-root",
            str(tmp_path),
            "--max-polls",
            "1",
        ]
    )

    config = script.config_from_args(args)

    assert config.symbols == _SYMBOLS
    assert config.data_root == tmp_path
    assert config.poll_seconds == 3.0
    assert config.max_polls == 1


def test_command_status_sink_is_durable_and_authority_none(tmp_path: Path) -> None:
    """Continuous capture exposes a latest atomic health record."""
    script = _script()
    path = tmp_path / "latest.json"
    row = {
        "event_type": "hip3_mark_recorder_heartbeat",
        "execution_authority": "none",
        "report_only": True,
    }

    script.status_sink(path)(row)

    assert json.loads(path.read_text(encoding="utf-8")) == row


def _script() -> ModuleType:
    path = Path("scripts/hip3_mark_snapshot_recorder.py")
    spec = importlib.util.spec_from_file_location("hip3_mark_snapshot_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HIP-3 mark snapshot script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _response() -> list[object]:
    return [
        {
            "universe": [
                {"name": "xyz:SP500"},
                {"name": "xyz:OTHER"},
                {"name": "xyz:SPCX"},
            ]
        },
        [
            _context("7801.8", "7804.4", "0.0000062254", "69248.422"),
            _context("10", "10", "0", "1"),
            _context("142.22", "142.27", "-0.0000263715", "1773591.24"),
        ],
    ]


def _context(mark: str, oracle: str, funding: str, interest: str) -> dict[str, str]:
    return {
        "markPx": mark,
        "oraclePx": oracle,
        "funding": funding,
        "openInterest": interest,
        "midPx": mark,
    }
