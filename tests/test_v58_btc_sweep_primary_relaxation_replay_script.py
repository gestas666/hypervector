"""Immutable command tests for the frozen V58 BTC causal replay."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
)


def test_command_publishes_hashed_report_and_trade_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One command must bind sources, generator, report, and lifecycle rows."""
    module = _load_module()
    bars, funding, prereg = _inputs(tmp_path)
    boundaries = pd.date_range("2025-01-01", periods=4, freq="72h", tz="UTC")
    partitions = tuple(
        BtcSweepHistoricalPartition(name, boundaries[index], boundaries[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    monkeypatch.setattr(
        module,
        "frozen_btc_sweep_historical_partitions",
        lambda: partitions,
    )
    output = tmp_path / "immutable_replay"
    args = module.build_parser().parse_args(
        [
            "--bars",
            str(bars),
            "--funding",
            str(funding),
            "--preregistration",
            str(prereg),
            "--output",
            str(output),
        ]
    )
    published = module.run_command(args)
    assert published == output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report["authority"]["execution_authority"] == "none"
    assert report["input_evidence"]["bars"]["sha256"]
    assert report["generator_identity"]["aggregate_sha256"]
    assert set(manifest["files"]) == {"report.json", "trades.parquet"}
    assert (output / "trades.parquet").is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        module.run_command(args)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    bars = _market(216).reset_index(names="timestamp")
    bars["source"] = "hl"
    bars_path = tmp_path / "bars.parquet"
    bars.to_parquet(bars_path, index=False)
    funding_index = pd.date_range("2025-01-01", periods=216, freq="1h", tz="UTC")
    funding = pd.DataFrame(
        {
            "timestamp": funding_index,
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    )
    funding_path = tmp_path / "funding.parquet"
    funding.to_parquet(funding_path, index=False)
    prereg = tmp_path / "prereg.json"
    prereg.write_text(
        json.dumps(
            {
                "schema_version": "cohort_strategy_preregistration_v1",
                "hypothesis_id": "V58_BTC_SWEEP_PRIMARY_RELAXATION_CAUSAL_REPLAY_V1",
            }
        ),
        encoding="utf-8",
    )
    return bars_path, funding_path, prereg


def _market(hours: int) -> pd.DataFrame:
    hourly_index = pd.date_range("2025-01-01", periods=hours, freq="1h", tz="UTC")
    hourly = pd.DataFrame(index=hourly_index)
    hourly["close"] = [120.0 + 0.05 * position for position in range(hours)]
    hourly["open"] = hourly["close"] - 0.025
    hourly["high"] = hourly["close"] + 0.1
    hourly["low"] = hourly["open"] - 0.1
    hourly["volume"] = 60.0
    hourly.iloc[[60, 132, 204], hourly.columns.get_loc("volume")] = 120.0
    rows: list[dict[str, float]] = []
    times: list[pd.Timestamp] = []
    for timestamp, row in hourly.iterrows():
        for minute in range(60):
            times.append(timestamp + pd.Timedelta(minutes=minute))
            rows.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) / 60.0,
                }
            )
    return pd.DataFrame(rows, index=pd.DatetimeIndex(times))


def _load_module() -> ModuleType:
    path = Path("scripts/v58_btc_sweep_primary_relaxation_replay.py")
    spec = importlib.util.spec_from_file_location("v58_btc_relaxation_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
