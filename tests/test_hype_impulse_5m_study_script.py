"""Integration tests for the HYPE five-minute impulse study command."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


def _command_module():
    from hypervector.research import hype_impulse_5m_study_command

    return hype_impulse_5m_study_command


def _write_inputs(root: Path) -> tuple[Path, Path]:
    candles = root / "candles.parquet"
    funding = root / "funding.parquet"
    timestamps = pd.date_range("2026-01-01", periods=625, freq="1min", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * len(timestamps),
            "high": [100.1] * len(timestamps),
            "low": [99.9] * len(timestamps),
            "close": [100.0] * len(timestamps),
            "volume": [10.0] * len(timestamps),
            "source": ["hl"] * len(timestamps),
        }
    ).to_parquet(candles, index=False)
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=11, freq="1h", tz="UTC"),
            "funding_rate": [0.00001] * 11,
            "source": ["hl_funding_history"] * 11,
            "event_ts_ms": range(11),
        }
    ).to_parquet(funding, index=False)
    return candles, funding


def test_command_publishes_source_bound_report_only_evidence(tmp_path: Path) -> None:
    command = _command_module()
    candles, funding = _write_inputs(tmp_path)
    output = tmp_path / "report.json"

    assert (
        command.main(
            ["--candles", str(candles), "--funding", str(funding), "--out", str(output)]
        )
        == 0
    )

    report = json.loads(output.read_text())
    assert report["contract"]["execution_authority"] == "none"
    assert report["inputs"]["candles"]["sha256"]
    assert report["inputs"]["funding"]["sha256"]
    assert report["input_summary"]["completed_5m_bars"] == 125
    assert report["input_summary"]["hourly_funding_rows"] == 11


def test_command_refuses_to_overwrite_immutable_report(tmp_path: Path) -> None:
    command = _command_module()
    candles, funding = _write_inputs(tmp_path)
    output = tmp_path / "report.json"
    output.write_text("preserve")

    with pytest.raises(FileExistsError):
        command.main(
            [
                "--candles",
                str(candles),
                "--funding",
                str(funding),
                "--out",
                str(output),
            ]
        )

    assert output.read_text() == "preserve"
