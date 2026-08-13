"""Exact-v39 stop-recovery diagnostic CLI tests."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path("scripts/v39_stop_recovery_sensitivity.py")
_PROFILE_ID = (
    "multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39"
)
_FINGERPRINT = "8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5"


def test_report_binds_exact_checkpoint_and_publishes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report binds its v39 input bytes and cannot be replaced."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "stop-recovery.json"
    payload = _checkpoint()
    raw = (json.dumps(payload) + "\n").encode()
    checkpoint.write_bytes(raw)
    monkeypatch.setattr(module, "build_stop_recovery_sensitivity", _report)
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(output)]
    )

    report = module.run_report(args)
    module.write_immutable_json(output, report)

    persisted = json.loads(output.read_text())
    assert persisted["evidence"]["checkpoint"]["sha256"] == sha256(raw).hexdigest()
    reflected = persisted["evidence"]["reflected_trades"]
    assert reflected["rows"] == [{"lifecycle_id": "trade-1"}]
    canonical = b'[{"lifecycle_id":"trade-1"}]'
    assert reflected["sha256"] == sha256(canonical).hexdigest()
    assert reflected["bytes"] == len(canonical)
    assert persisted["source"]["profile_id"] == _PROFILE_ID
    generator_paths = {
        Path(row["path"]).name for row in persisted["generator_identity"]["files"]
    }
    assert "cohort_live_audit_values.py" in generator_paths
    with pytest.raises(FileExistsError, match="immutable JSON output exists"):
        module.write_immutable_json(output, report)


def test_wrong_profile_is_rejected(tmp_path: Path) -> None:
    """A checkpoint from another strategy generation cannot be relabeled v39."""
    module = _module()
    checkpoint = tmp_path / "checkpoint.json"
    payload = _checkpoint()
    payload["audit"]["run"]["profile_id"] = "wrong-profile"
    checkpoint.write_text(json.dumps(payload))
    args = module.build_parser().parse_args(
        ["--checkpoint", str(checkpoint), "--out", str(tmp_path / "out.json")]
    )

    with pytest.raises(ValueError, match="exact v39 profile"):
        module.run_report(args)


def _checkpoint() -> dict[str, object]:
    return {
        "audit": {
            "run": {
                "run_id": "run-v39",
                "profile_id": _PROFILE_ID,
                "profile_fingerprint": _FINGERPRINT,
            },
            "trade_reflections": {"trades": [{"lifecycle_id": "trade-1"}]},
        }
    }


def _report(trades: object, *, stop_widths_bps: object) -> dict[str, object]:
    assert trades == [{"lifecycle_id": "trade-1"}]
    assert stop_widths_bps == (80.0, 100.0, 125.0, 150.0, 200.0)
    return {"contract": {"report_only": True, "execution_authority": "none"}}


def _module() -> ModuleType:
    if not _SCRIPT.exists():
        pytest.fail("v39 stop-recovery script is missing")
    spec = spec_from_file_location("v39_stop_recovery_sensitivity_script", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load v39 stop-recovery script")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
