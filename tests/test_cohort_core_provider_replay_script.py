"""Offline integration of current-provider extraction and immutable publication."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

_CONFIG = (
    "configs/multi_asset_growth_first_5000_seven_asset_failed_routes_retired_v86.toml"
)
_START = pd.Timestamp("2026-05-19T00:00:00Z")
_SYMBOLS = ("BTC", "ETH", "SOL", "HYPE")


def test_command_extracts_all_core_routes_and_refuses_replacement(
    tmp_path: Path,
) -> None:
    """Actual production collectors publish explicit source and parity limits."""
    _write_bars(tmp_path)
    command = _command(tmp_path)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    manifest = tmp_path / "output/manifest.json"
    content = manifest.read_bytes()
    report = json.loads(content)
    assert report["execution_authority"] == "none"
    assert report["profitability_evaluated"] is False
    assert {row["symbol"] for row in report["routes"]} == set(_SYMBOLS)
    assert sum(row["batches"][0]["decisions"] for row in report["routes"]) == 181
    assert all(row["parity_checks"] == 0 for row in report["routes"])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert manifest.read_bytes() == content


def test_source_failure_does_not_publish_success_shaped_manifest(
    tmp_path: Path,
) -> None:
    """Partial symbol extraction cannot become a completed portfolio artifact."""
    _write_bars(tmp_path)
    path = tmp_path / "cache/ETH_1m_365d.parquet"
    bars = pd.read_parquet(path)
    bars.loc[0, "source"] = "unverified"
    bars.to_parquet(path, index=False)
    result = subprocess.run(
        _command(tmp_path), capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "source must explicitly identify" in result.stderr
    assert not (tmp_path / "output").exists()


def test_sndk_diagnostic_records_current_discrepancy_without_claiming_loss(
    tmp_path: Path,
) -> None:
    """The synthetic scenario exposes entry disagreement using both real engines."""
    output = tmp_path / "sndk.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/sndk_pressure_onset_diagnostic.py",
            "--out",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["synthetic"] is True
    assert report["private_fills_inferred"] is False
    assert [row["mismatched_boundaries"] for row in report["cases"]] == [2, 2]
    assert all(row["canonical_total_entries"] == 1 for row in report["cases"])


def _write_bars(root: Path) -> None:
    times = pd.date_range(
        _START - pd.Timedelta(days=14), _START + pd.Timedelta(minutes=59), freq="min"
    )
    bars = pd.DataFrame(
        {
            "timestamp": times,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 10.0,
            "source": "hl",
        }
    )
    (root / "cache").mkdir()
    for symbol in _SYMBOLS:
        bars.to_parquet(root / "cache" / f"{symbol}_1m_365d.parquet", index=False)


def _command(root: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/cohort_core_provider_replay.py",
        "--config",
        _CONFIG,
        "--data-root",
        str(root),
        "--backtest-lab-root",
        str(root / "unused-lab"),
        "--start",
        str(_START),
        "--end",
        str(_START + pd.Timedelta(hours=1)),
        "--out-dir",
        str(root / "output"),
    ]
