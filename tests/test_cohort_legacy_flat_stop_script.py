"""CLI tests for the exact-run legacy flat-to-STOP watcher."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from hypervector.live.cohort_legacy_flat_stop import LegacyFlatStopEvidence

_SCRIPT = Path(__file__).parents[1] / "scripts" / "cohort_legacy_flat_stop.py"
_PROFILE = "c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b"
_RUN_ID = "bidirectional-live-1785826133777"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("cohort_legacy_flat_stop_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_mode_observes_without_writing_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The watcher remains report-only unless the operator adds --write-stop."""
    module = _load_module()
    evidence = _evidence()
    monkeypatch.setattr(
        module, "watch_legacy_flat_boundary", lambda *_a, **_k: evidence
    )
    stop = tmp_path / "STOP"

    result = module.run(module.build_parser().parse_args(_args(tmp_path, stop)))

    assert result == 0
    assert not stop.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "flat_boundary_observed"
    assert payload["stop_written"] is False
    assert payload["execution_authority"] == "none"


def test_explicit_write_stop_uses_the_verified_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The explicit mutation writes only the exact qualified transition row."""
    module = _load_module()
    evidence = _evidence()
    monkeypatch.setattr(
        module, "watch_legacy_flat_boundary", lambda *_a, **_k: evidence
    )
    stop = tmp_path / "STOP"

    result = module.run(
        module.build_parser().parse_args([*_args(tmp_path, stop), "--write-stop"])
    )

    assert result == 0
    assert json.loads(stop.read_text(encoding="utf-8"))["source_sequence"] == 70001
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "stop_requested"
    assert payload["stop_written"] is True


def _args(root: Path, stop: Path) -> list[str]:
    return [
        "--ledger",
        str(root / "decisions.jsonl"),
        "--stop-file",
        str(stop),
        "--expected-profile-fingerprint",
        _PROFILE,
        "--expected-run-id",
        _RUN_ID,
        "--expected-symbol",
        "BTC",
        "--expected-symbol",
        "ETH",
        "--expected-symbol",
        "SOL",
        "--expected-symbol",
        "HYPE",
    ]


def _evidence() -> LegacyFlatStopEvidence:
    return LegacyFlatStopEvidence(
        run_id=_RUN_ID,
        profile_fingerprint=_PROFILE,
        observed_at_utc="2026-08-05T20:00:00+00:00",
        symbols=("BTC", "ETH", "SOL", "HYPE"),
        source_sequence=70001,
    )
