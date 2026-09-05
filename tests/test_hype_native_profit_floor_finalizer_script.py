"""Tests for automatic finalization of the HYPE profit-floor transfer."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from hashlib import sha256
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/hype_native_profit_floor_finalizer.py")


def test_missing_resolution_waits_without_running_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    args = _args(tmp_path, module)
    monkeypatch.setattr(
        module,
        "_run_transfer",
        lambda *_args: pytest.fail("transfer must wait for exact resolution"),
    )

    completed = module.finalize_once(args)

    assert completed is False
    status = json.loads(args.status.read_text(encoding="utf-8"))
    assert status["state"] == "waiting_for_exact_resolution"
    assert status["execution_authority"] == "none"


def test_exact_resolution_publishes_complete_floor_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    args = _args(tmp_path, module)
    snapshot = tmp_path / "closed-snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    args.resolution.write_text(
        json.dumps(
            {
                "evidence": {
                    "lifecycle_status": {
                        "path": str(snapshot),
                        "sha256": sha256(snapshot.read_bytes()).hexdigest(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def transfer(values: object, source: Path) -> None:
        captured["source"] = source
        values.output.write_text(
            json.dumps(
                {
                    "mode": "hype_native_mature_profit_floor_transfer_v1",
                    "contract": {"report_only": True, "execution_authority": "none"},
                    "comparison": {"status": "complete", "trades": 3},
                    "source_evidence": {
                        "prospective_status": {
                            "sha256": sha256(source.read_bytes()).hexdigest()
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(module, "_run_transfer", transfer)

    completed = module.finalize_once(args)

    assert completed is True
    status = json.loads(args.status.read_text(encoding="utf-8"))
    assert status["state"] == "complete_floor_comparison_published"
    assert status["trades"] == 3
    assert captured["source"] == snapshot


def test_transfer_command_requires_immutable_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    args = _args(tmp_path, module)
    captured: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> None:
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr(module.subprocess, "run", run)

    module._run_transfer(args, tmp_path / "snapshot.json")

    assert "--immutable" in captured["command"]
    assert captured["kwargs"] == {
        "check": True,
        "capture_output": True,
        "text": True,
    }


def test_technical_resolution_publishes_terminal_floor_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    args = _args(tmp_path, module)
    snapshot = tmp_path / "closed-snapshot.json"
    snapshot.write_text("{}", encoding="utf-8")
    for path in (*args.closed_path, *args.closed_funded):
        path.write_text("{}", encoding="utf-8")
    args.resolution.write_text(
        json.dumps(
            {
                "resolution_status": "technical_evidence_rejected",
                "contract": {"report_only": True, "execution_authority": "none"},
                "evidence": {
                    "lifecycle_status": {
                        "path": str(snapshot),
                        "sha256": sha256(snapshot.read_bytes()).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "_run_transfer",
        lambda *_args: pytest.fail("rejected evidence cannot run a comparison"),
    )

    completed = module.finalize_once(args)

    assert completed is True
    report = json.loads(args.output.read_text(encoding="utf-8"))
    status = json.loads(args.status.read_text(encoding="utf-8"))
    assert report["comparison"]["status"] == "technically_unresolved"
    assert report["decision"] == "reject_profit_floor_live_change"
    assert status["state"] == "technical_evidence_rejected_no_floor_promotion"


def _args(tmp_path: Path, module: ModuleType) -> object:
    return module.build_parser().parse_args(
        [
            "--closed-path",
            str(tmp_path / "path.json"),
            "--closed-funded",
            str(tmp_path / "funded.json"),
            "--lifecycle-status",
            str(tmp_path / "lifecycle.json"),
            "--resolution",
            str(tmp_path / "resolution.json"),
            "--output",
            str(tmp_path / "output.json"),
            "--status",
            str(tmp_path / "status.json"),
            "--max-cycles",
            "1",
        ]
    )


def _load_script() -> ModuleType:
    spec = spec_from_file_location("hype_native_profit_floor_finalizer_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
