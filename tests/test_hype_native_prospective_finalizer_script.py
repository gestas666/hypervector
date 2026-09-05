"""Automatic report-only finalization of the open HYPE-native lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_prospective_finalizer.py")


def test_open_status_waits_without_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open lifecycle cannot trigger speculative external acquisition."""
    module = _load_script()
    args = _args(tmp_path, module)
    args.lifecycle_status.write_text(
        json.dumps({"watch_state": "tracking_open_lifecycle", "snapshot": None}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "_ensure_funding",
        lambda *_args: pytest.fail("funding must not be acquired while open"),
    )

    completed = module.finalize_once(args)

    assert completed is False
    status = json.loads(args.finalizer_status.read_text(encoding="utf-8"))
    assert status["state"] == "waiting_for_closed_lifecycle"
    assert status["execution_authority"] == "none"


def test_closed_snapshot_acquires_exact_bounds_and_runs_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The finalizer derives deterministic mark and hourly funding windows."""
    module = _load_script()
    args = _args(tmp_path, module)
    snapshot = tmp_path / "closed.json"
    entry_ms = int(
        datetime(2026, 8, 18, 6, 30, 17, 371000, tzinfo=UTC).timestamp() * 1000
    )
    exit_ms = int(
        datetime(2026, 8, 18, 14, 30, 17, 371000, tzinfo=UTC).timestamp() * 1000
    )
    snapshot.write_text(json.dumps(_closed_report(entry_ms, exit_ms)), encoding="utf-8")
    args.lifecycle_status.write_text(
        json.dumps(
            {
                "watch_state": "resolved_proxy_lifecycle_evidence_available",
                "snapshot": str(snapshot),
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def funding(request: object, _root: Path) -> Path:
        captured["funding"] = request
        return tmp_path / "funding.parquet"

    def prices(request: object, _root: Path) -> Path:
        captured["prices"] = request
        return tmp_path / "prices.parquet"

    def resolution(*values: object) -> None:
        captured["resolution"] = values

    def decision(*values: object) -> None:
        captured["decision"] = values

    monkeypatch.setattr(module, "_ensure_funding", funding)
    monkeypatch.setattr(module, "_ensure_prices", prices)
    monkeypatch.setattr(module, "_run_resolution", resolution)
    monkeypatch.setattr(module, "_run_decision", decision)

    completed = module.finalize_once(args)

    _assert_requests(captured, entry_ms, exit_ms, args.resolution_out)
    assert completed is True
    status = json.loads(args.finalizer_status.read_text(encoding="utf-8"))
    assert status["state"] == "resolved_exact_evidence_and_decision_published"


def test_matching_existing_resolution_is_restart_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after immutable publication can resume without overwriting evidence."""
    module = _load_script()
    args = _args(tmp_path, module)
    snapshot = tmp_path / "closed.json"
    snapshot.write_text('{"closed":true}', encoding="utf-8")
    args.resolution_out.write_text(
        json.dumps(
            {
                "mode": "hype_native_v54_exact_post_close_resolution_report_only",
                "contract": {"report_only": True, "execution_authority": "none"},
                "evidence": {
                    "lifecycle_status": {
                        "sha256": sha256(snapshot.read_bytes()).hexdigest()
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("matching output must be reused"),
    )
    price_request = module.OxaPriceRequest(
        "HYPE",
        datetime(2026, 8, 18, 6, tzinfo=UTC),
        datetime(2026, 8, 18, 7, tzinfo=UTC),
    )

    module._run_resolution(snapshot, tmp_path / "funding.parquet", price_request, args)


def _closed_report(entry_ms: int, exit_ms: int) -> dict[str, object]:
    return {
        "lifecycles": [
            {
                "entry_book_time_ms": entry_ms,
                "exit_book_time_ms": exit_ms,
                "technical_path_resolved": True,
            }
        ]
    }


def _assert_requests(
    captured: dict[str, object], entry_ms: int, exit_ms: int, resolution: Path
) -> None:
    funding_request = captured["funding"]
    price_request = captured["prices"]
    assert funding_request.start == datetime(2026, 8, 18, 6, tzinfo=UTC)
    assert funding_request.end == datetime(2026, 8, 18, 15, tzinfo=UTC)
    assert price_request.start.timestamp() * 1000 == entry_ms
    assert price_request.end.timestamp() * 1000 == exit_ms + 1
    assert captured["decision"][0] == resolution


def _args(tmp_path: Path, module: ModuleType) -> object:
    return module.build_parser().parse_args(
        [
            "--lifecycle-status",
            str(tmp_path / "latest.json"),
            "--data-root",
            str(tmp_path / "data"),
            "--resolution-out",
            str(tmp_path / "resolution.json"),
            "--finalizer-status",
            str(tmp_path / "finalizer.json"),
            "--decision-journal",
            str(tmp_path / "journal.json"),
            "--decision-out",
            str(tmp_path / "decision.json"),
            "--max-cycles",
            "1",
        ]
    )


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_prospective_finalizer_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
