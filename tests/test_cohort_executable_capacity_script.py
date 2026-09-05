"""Offline publication and provenance checks for executable capacity reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_CONFIG = Path(
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)


def test_capacity_command_binds_source_and_refuses_replacement(tmp_path: Path) -> None:
    """The offline command preserves exact evidence and immutable output."""
    source = _snapshot(tmp_path)
    output = tmp_path / "result.json"
    command = _command(source, output)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    content = output.read_bytes()
    report = json.loads(content)
    assert (
        report["evidence"]["venue_snapshot"]["sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert report["venue_observed_at_utc"] == "2026-09-05T15:30:46+00:00"
    assert report["scenarios"][1]["slippage_bps"] == 120
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert output.read_bytes() == content


@pytest.mark.parametrize("defect", ["fingerprint", "duplicate_asset", "unknown_fee"])
def test_capacity_command_rejects_ambiguous_evidence(
    tmp_path: Path, defect: str
) -> None:
    """Wrong profile, duplicate symbols and missing fees cannot yield a report."""
    source = _snapshot(tmp_path)
    snapshot = json.loads(source.read_text())
    if defect == "fingerprint":
        snapshot["identity"]["candidate_profile_fingerprint"] = "wrong"
    elif defect == "duplicate_asset":
        snapshot["assets"].append(snapshot["assets"][0])
    else:
        snapshot["assets"][0]["venue"]["one_way_taker_fee_bps"] = None
    source.write_text(json.dumps(snapshot))
    output = tmp_path / "result.json"
    result = subprocess.run(_command(source, output), capture_output=True, check=False)
    assert result.returncode != 0
    assert not output.exists()


def _snapshot(tmp_path: Path) -> Path:
    config = load_multi_asset_live_config(_CONFIG, mode="observe")
    source = tmp_path / "snapshot.json"
    source.write_text(
        json.dumps(
            {
                "observed_at_utc": "2026-09-05T15:30:46+00:00",
                "identity": {
                    "candidate_profile_fingerprint": config.profile_fingerprint
                },
                "portfolio": {"sizing_reference_equity_usd": 4857.58724349},
                "assets": [
                    {"symbol": asset.symbol, "venue": {"one_way_taker_fee_bps": 4.32}}
                    for asset in config.assets
                ],
            }
        )
    )
    return source


def _command(source: Path, output: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/cohort_executable_capacity.py",
        "--config",
        str(_CONFIG),
        "--venue-snapshot",
        str(source),
        "--out",
        str(output),
        "--slippage-bps",
        "120",
        "--funding-bps",
        "20",
    ]
