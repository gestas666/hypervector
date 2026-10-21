"""Reproducible source-bound command input for the actual native packet runner."""

from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest
from test_native_replay_adapter import deny_external_ports
from test_native_replay_sdk_engines import cohort_sdk

from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.research.native_replay_packets import run_packet_scenario
from hypervector.research.native_replay_sdk import ReplaySdk

__all__ = ["deny_external_ports"]


_PACKET_ROWS = 240
_CUTOFF_DELAY_MS = 60_000


def _recorded_packet(root: Path, config: MultiAssetLiveConfig, cutoff_ms: int) -> Path:
    """Write one flat recorded cold poll covering every configured symbol."""
    start = pd.Timestamp(cutoff_ms, unit="ms", tz="UTC") - pd.Timedelta(
        minutes=_PACKET_ROWS
    )
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=_PACKET_ROWS, freq="1min"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
        }
    )
    inputs = root / "profile_inputs" / "cold"
    inputs.mkdir(parents=True)
    frames = []
    for symbol in config.symbols:
        target = inputs / f"{symbol}.parquet"
        frame.to_parquet(target, index=False)
        frames.append(
            {
                "symbol": symbol,
                "rows": _PACKET_ROWS,
                "sha256": sha256(target.read_bytes()).hexdigest(),
            }
        )
    record = {
        "label": "cold",
        "observed_cutoff_utc": pd.Timestamp(cutoff_ms, unit="ms", tz="UTC").isoformat(),
        "elapsed_seconds_with_profiler": 0.01 * len(config.symbols),
        "fetch_calls": [
            {
                "symbol": symbol,
                "timeframe": "1m",
                "lookback_days": float(config.lookback_days),
                "end_ms": cutoff_ms,
                "elapsed_seconds": 0.005,
            }
            for symbol in config.symbols
        ],
        "input_frames": frames,
    }
    path = root / "profile_cold.json"
    path.write_text(json.dumps(record))
    return path


def scenario_file(tmp_path: Path) -> Path:
    """Describe synthetic account quotes around a synthetic authenticated candle packet."""
    config = load_multi_asset_live_config(
        "tests/fixtures/profiles/mixed_crypto_hip3.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    replay = cohort_sdk(config, {})
    packet = _recorded_packet(
        tmp_path / "packets", config, replay.clock.now_ms + _CUTOFF_DELAY_MS
    )
    body = {
        "schema": "native-packet-replay-v1",
        "economic_inputs": "declared_scenario",
        "config": {
            "path": str(config.source_path.resolve()),
            "sha256": sha256(config.source_path.read_bytes()).hexdigest(),
        },
        "initial_time_ms": replay.clock.now_ms,
        "initial_cash_usd": "5000",
        "metadata_by_dex": replay.metadata_by_dex,
        "dexes": replay.dexes,
        "fees": replay.fees,
        "timing": {
            name: getattr(replay.timing, name) for name in replay.timing.__dataclass_fields__
        },
        "maintenance": _maintenance(replay),
        "initial_observations": [
            {
                "symbol": s,
                "time_ms": replay.clock.now_ms,
                "mark": "100",
                "mid": "100",
                "book": replay.observed_books[s],
            }
            for s in config.symbols
        ],
        "packets": [
            {
                "path": str(packet.resolve()),
                "sha256": sha256(packet.read_bytes()).hexdigest(),
            }
        ],
        "execution_sources": [],
        "maximum_book_delay_ms": 5000,
        "events": [],
    }
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(body))
    return path


def _maintenance(replay: ReplaySdk) -> dict[str, list[dict[str, str]]]:
    return {
        s: [
            {
                "lower_notional_usd": str(t.lower_notional_usd),
                "rate": str(t.rate),
                "deduction_usd": str(t.deduction_usd),
            }
            for t in tiers
        ]
        for s, tiers in replay.maintenance.items()
    }


def test_scenario_runs_native_controls_and_retains_explicit_scope(tmp_path: Path) -> None:
    """A successful no-entry capture is reported as such, with all native ledgers retained."""
    path = scenario_file(tmp_path)
    output = tmp_path / "result"
    result = run_packet_scenario(path, output)
    assert result["actions_per_poll"] == [0]
    assert result["filled_orders"] == 0 and result["equity_usd"] == "5000"
    assert (
        result["scope"] == "declared recorded polls; not continuous historical portfolio validation"
    )
    assert result["scenario_sha256"] == sha256(path.read_bytes()).hexdigest()
    assert len(list((output / "live/bidirectional_cohort").glob("*.jsonl"))) == 8
    assert json.loads((output / "run_report.json").read_text()) == result


@pytest.mark.parametrize("failure", ["config_checksum", "empty_packets", "packet_checksum"])
def test_packet_scenario_rejects_bad_source_identity(tmp_path: Path, failure: str) -> None:
    """Incomplete or changed source inputs cannot become successful empty-control reports."""
    path = scenario_file(tmp_path)
    body = json.loads(path.read_text())
    if failure == "config_checksum":
        body["config"]["sha256"] = "0" * 64
    elif failure == "empty_packets":
        body["packets"] = []
    else:
        body["packets"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        run_packet_scenario(path, tmp_path / "result")
    assert not (tmp_path / "result/run_report.json").exists()
