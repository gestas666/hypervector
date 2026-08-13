"""Contracts for close-triggered v39 dual-MTF evidence capture."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v39_dual_mtf_reversal_monitor.py")
_RUN_ID = "bidirectional-live-1786453934555"
_PROFILE = "8" * 64


def test_bootstrap_uses_verified_artifact_without_replaying(
    tmp_path: Path,
) -> None:
    """A missing cursor starts at the frozen baseline rather than replaying it."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=4)
    _write_artifact(args.bootstrap_artifact, closed=4)
    calls: list[Path] = []

    result = module.refresh(args, publish_fn=lambda _, out: calls.append(out))

    assert result["state"] == "initialized"
    assert calls == []
    cursor = json.loads(args.cursor.read_text())
    assert cursor["analyzed_closed_trades"] == 4
    assert cursor["execution_authority"] == "none"


def test_new_close_publishes_then_advances_cursor(tmp_path: Path) -> None:
    """A new close advances durable state only after a valid artifact exists."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=5)
    _write_artifact(args.bootstrap_artifact, closed=4)
    _write_cursor(args.cursor, closed=4)

    def publish(_: object, output: Path) -> None:
        _write_artifact(output, closed=5)

    result = module.refresh(args, publish_fn=publish)

    assert result["state"] == "published"
    assert result["closed_trades"] == 5
    cursor = json.loads(args.cursor.read_text())
    assert cursor["analyzed_closed_trades"] == 5
    assert Path(cursor["artifact"]["path"]).is_file()


def test_publish_failure_preserves_prior_cursor(tmp_path: Path) -> None:
    """A failed analysis cannot success-shape the new close as processed."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=5)
    _write_artifact(args.bootstrap_artifact, closed=4)
    _write_cursor(args.cursor, closed=4)
    before = args.cursor.read_bytes()

    def fail(_: object, __: Path) -> None:
        raise RuntimeError("analysis failed")

    with pytest.raises(RuntimeError, match="analysis failed"):
        module.refresh(args, publish_fn=fail)
    assert args.cursor.read_bytes() == before


def test_wrong_runtime_identity_fails_before_publish(tmp_path: Path) -> None:
    """A different run cannot be analyzed under the frozen v39 cursor."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=5, run_id="other-run")
    _write_artifact(args.bootstrap_artifact, closed=4)

    with pytest.raises(ValueError, match="run identity"):
        module.refresh(args, publish_fn=lambda *_: None)
    assert not args.cursor.exists()


def test_candidate_artifact_must_remain_report_only(tmp_path: Path) -> None:
    """A success-shaped artifact with selected authority is rejected."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=5)
    _write_artifact(args.bootstrap_artifact, closed=4)
    _write_cursor(args.cursor, closed=4)

    def publish(_: object, output: Path) -> None:
        _write_artifact(output, closed=5, selected="dual_mtf_p1")

    with pytest.raises(ValueError, match="selected_policy"):
        module.refresh(args, publish_fn=publish)
    assert json.loads(args.cursor.read_text())["analyzed_closed_trades"] == 4


def test_existing_cursor_revalidates_its_artifact(tmp_path: Path) -> None:
    """A changed baseline cannot silently preserve an analyzed count."""
    module = _module()
    args = _args(module, tmp_path)
    _write_checkpoint(args.checkpoint, closed=4)
    _write_artifact(args.bootstrap_artifact, closed=4)
    _write_cursor(args.cursor, closed=4)
    args.bootstrap_artifact.write_text("{}")

    with pytest.raises(ValueError, match="cursor artifact"):
        module.refresh(args, publish_fn=lambda *_: None)


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v39 dual-MTF monitor script is missing")
    spec = spec_from_file_location("v39_dual_mtf_monitor", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v39 dual-MTF monitor")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(module: ModuleType, root: Path) -> object:
    return module.build_parser().parse_args(
        [
            "--checkpoint",
            str(root / "checkpoint.json"),
            "--ledger-root",
            str(root / "ledgers"),
            "--run-id",
            _RUN_ID,
            "--profile-fingerprint",
            _PROFILE,
            "--bootstrap-artifact",
            str(root / "baseline.json"),
            "--cursor",
            str(root / "cursor.json"),
            "--artifact-dir",
            str(root / "artifacts"),
            "--once",
        ]
    )


def _write_checkpoint(path: Path, *, closed: int, run_id: str = _RUN_ID) -> None:
    trades = [
        {"source_run_id": run_id, "lifecycle_id": f"ETH:{i}"} for i in range(closed)
    ]
    payload = {
        "lifecycle": {"state": "running_consistent"},
        "configuration_generation": {
            "matches_runtime": True,
            "current_profile_fingerprint": _PROFILE,
        },
        "audit": {
            "run": {"run_id": run_id, "profile_fingerprint": _PROFILE},
            "trade_reflections": {"trades": trades},
        },
    }
    path.write_text(json.dumps(payload))


def _write_artifact(path: Path, *, closed: int, selected: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract": {
            "automatic_promotion": False,
            "execution_authority": "none",
            "report_only": True,
            "runtime_strategy_changed": False,
            "selected_policy": selected,
        },
        "current_profile": {"source_profile_fingerprint": _PROFILE},
        "current_run": {
            "source_run_id": _RUN_ID,
            "policies": {
                "dual_mtf_p1": {
                    "eligible_lifecycles": closed,
                    "withheld_lifecycles": 0,
                }
            },
        },
    }
    path.write_text(json.dumps(payload))


def _write_cursor(path: Path, *, closed: int) -> None:
    artifact = path.parent / "baseline.json"
    raw = artifact.read_bytes()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "v39_dual_mtf_reversal_close_monitor_v1",
                "run_id": _RUN_ID,
                "profile_fingerprint": _PROFILE,
                "analyzed_closed_trades": closed,
                "artifact": {
                    "path": str(artifact.resolve()),
                    "sha256": sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
                "execution_authority": "none",
                "runtime_strategy_changed": False,
            }
        )
    )
