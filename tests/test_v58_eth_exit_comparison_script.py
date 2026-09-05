"""Immutable CLI publication for the first V58 ETH exit comparison."""

from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from test_v58_eth_exit_comparison import _close_report, _duration_report


def test_publishes_source_bound_report_only_comparison(tmp_path: Path) -> None:
    """The CLI must publish stable input and generator evidence atomically."""
    module = _load_script()
    close = _write_json(tmp_path / "close.json", _close_report())
    duration = _write_json(tmp_path / "duration.json", _duration_report())
    preregistration = _write_json(
        tmp_path / "preregistration.json", _preregistration(duration)
    )
    output = tmp_path / "comparison.json"
    args = argparse.Namespace(
        close=close,
        duration=duration,
        preregistration=preregistration,
        preregistration_sha256=_sha256(preregistration),
        out=output,
    )

    report = module.publish_report(args)

    assert json.loads(output.read_text()) == report
    assert report["contract"]["execution_authority"] == "none"
    assert {row["label"] for row in report["source_evidence"]} == {
        "comparison_preregistration",
        "live_close_reconciliation",
        "duration_checkpoint",
    }
    assert report["generator_identity"]


def test_rejects_preregistration_for_another_lifecycle(tmp_path: Path) -> None:
    """A changed frozen lifecycle must fail before immutable publication."""
    module = _load_script()
    close = _write_json(tmp_path / "close.json", _close_report())
    duration = _write_json(tmp_path / "duration.json", _duration_report())
    payload = _preregistration(duration)
    payload["frozen_identity"] = {**payload["frozen_identity"], "side": "short"}
    preregistration = _write_json(tmp_path / "preregistration.json", payload)
    output = tmp_path / "comparison.json"
    args = argparse.Namespace(
        close=close,
        duration=duration,
        preregistration=preregistration,
        preregistration_sha256=_sha256(preregistration),
        out=output,
    )

    with pytest.raises(ValueError, match="preregistration identity differs"):
        module.publish_report(args)

    assert not output.exists()


def _load_script() -> object:
    """Load the comparison CLI module from its project path."""
    script = Path("scripts/v58_eth_exit_comparison.py")
    assert script.exists(), "V58 ETH exit comparison CLI is missing"
    spec = spec_from_file_location("v58_eth_exit_comparison_script", script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    """Write one compact JSON fixture."""
    path.write_text(json.dumps(payload, sort_keys=True))
    return path


def _preregistration(duration: Path) -> dict[str, object]:
    """Return one frozen comparison preregistration fixture."""
    return {
        "scope": "v58_eth_first_live_exit_duration_comparison_preregistration",
        "hypothesis_id": "v58_eth_first_live_exit_duration_comparison_v1",
        "status": "being_tested",
        "contract": _close_report()["contract"],
        "frozen_identity": _close_report()["frozen_identity"],
        "frozen_inputs": {
            "duration_checkpoint": {
                "path": str(duration),
                "bytes": duration.stat().st_size,
                "sha256": _sha256(duration),
            }
        },
    }


def _sha256(path: Path) -> str:
    """Return one fixture SHA-256 digest."""
    return sha256(path.read_bytes()).hexdigest()
