from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

import pandas as pd
import pytest

from hypervector.research.sol_range_onset_backward_challenge import (
    evaluate_sol_backward_challenge,
    prepare_gap_safe_blocks,
)

SCRIPT = Path(__file__).parents[1] / "scripts" / "sol_range_onset_backward_challenge.py"


def _load_script() -> ModuleType:
    spec = spec_from_file_location("sol_range_onset_backward_challenge", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bars(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )


def _signals(bars: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(
        False,
        index=bars.index,
        columns=("long_entry", "short_entry", "long_exit", "short_exit"),
    )
    result["long_signal_name"] = "fixture_long"
    result["short_signal_name"] = "fixture_short"
    eligible = bars.index[bars.index >= bars.index[0] + pd.Timedelta(hours=30)]
    if len(eligible) >= 62:
        result.loc[eligible[0], "long_entry"] = True
        result.loc[eligible[60], "long_exit"] = True
    return result


def _write_inputs(
    root: Path,
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> tuple[Path, Path]:
    bars_dir = root / "bars"
    funding_dir = root / "funding"
    bars_dir.mkdir()
    funding_dir.mkdir()
    bars_path = bars_dir / "candles.parquet"
    funding_path = funding_dir / "funding.parquet"
    bars.to_parquet(bars_path, index=False)
    hours = pd.date_range(start, end, freq="1h", inclusive="left")
    pd.DataFrame(
        {
            "timestamp": hours,
            "funding_rate": 0.0,
            "source": "hl_funding_history",
        }
    ).to_parquet(funding_path, index=False)
    _write_manifest(
        bars_dir / "manifest.json",
        bars_path,
        source="0xarchive_hyperliquid_candles",
        start=start,
        end=end,
        row_count=len(bars),
    )
    _write_manifest(
        funding_dir / "manifest.json",
        funding_path,
        source="hl_funding_history",
        start=start,
        end=end,
        row_count=len(hours),
    )
    return bars_path, funding_path


def _write_manifest(
    path: Path,
    data_path: Path,
    *,
    source: str,
    start: datetime,
    end: datetime,
    row_count: int,
) -> None:
    payload = {
        "source": source,
        "venue": "hyperliquid",
        "symbol": "SOL",
        "interval": "1m" if "candle" in source else None,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "row_count": row_count,
        "complete": True,
        "files": {
            data_path.name: {
                "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_gap_blocks_repair_bounded_holes_and_split_outages() -> None:
    start = pd.Timestamp("2025-03-01T00:00:00Z")
    offsets = (0, 1, 3, 4, 40, 41)
    frame = _bars(pd.DatetimeIndex(start + pd.Timedelta(minutes=n) for n in offsets))

    blocks = prepare_gap_safe_blocks(frame, max_gap_minutes=30)

    assert len(blocks) == 2
    assert len(blocks[0].bars) == 5
    assert blocks[0].gap_fill_rows == 1
    assert (
        blocks[0].bars.loc[start + pd.Timedelta(minutes=2), "source"] == "hl_gap_fill"
    )
    assert blocks[1].gap_fill_rows == 0
    assert blocks[1].start == start + pd.Timedelta(minutes=40)


def test_backward_challenge_is_gap_causal_and_execution_incapable(
    tmp_path: Path,
) -> None:
    start = datetime(2025, 3, 1, tzinfo=UTC)
    first_end = pd.Timestamp(start) + pd.Timedelta(hours=32)
    second_start = first_end + pd.Timedelta(hours=2)
    end = second_start + pd.Timedelta(minutes=30)
    first = pd.date_range(start, first_end, freq="1min", inclusive="left")
    second = pd.date_range(second_start, end, freq="1min", inclusive="left")
    bars_path, funding_path = _write_inputs(
        tmp_path,
        _bars(first.append(second)),
        start,
        end.to_pydatetime(),
    )

    report = evaluate_sol_backward_challenge(
        bars_path=bars_path,
        funding_path=funding_path,
        start=start,
        end=end.to_pydatetime(),
        signal_builder=_signals,
    )

    assert report["execution_authority"] == "none"
    assert report["model_authority"] == "none"
    assert report["place_attempted"] is False
    assert report["submitted"] is False
    assert report["block_count"] == 2
    assert report["complete_block_count"] == 1
    assert report["insufficient_warmup_block_count"] == 1
    assert report["aggregate"]["completed_trades"] == 1
    assert report["aggregate"]["forced_end_exits"] == 0
    assert report["blocks"][1]["status"] == "insufficient_warmup"


def test_backward_challenge_rejects_incomplete_hourly_funding(
    tmp_path: Path,
) -> None:
    start = datetime(2025, 3, 1, tzinfo=UTC)
    end = datetime(2025, 3, 3, tzinfo=UTC)
    bars = _bars(pd.date_range(start, end, freq="1min", inclusive="left"))
    bars_path, funding_path = _write_inputs(tmp_path, bars, start, end)
    funding = pd.read_parquet(funding_path).iloc[:-1]
    funding.to_parquet(funding_path, index=False)
    manifest_path = funding_path.parent / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["files"][funding_path.name]["sha256"] = hashlib.sha256(
        funding_path.read_bytes()
    ).hexdigest()
    payload["row_count"] = len(funding)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="funding is incomplete"):
        evaluate_sol_backward_challenge(
            bars_path=bars_path,
            funding_path=funding_path,
            start=start,
            end=end,
            signal_builder=_signals,
        )


def test_backward_challenge_script_writes_report_once(tmp_path: Path) -> None:
    start = datetime(2025, 3, 1, tzinfo=UTC)
    end = datetime(2025, 3, 3, tzinfo=UTC)
    bars = _bars(pd.date_range(start, end, freq="1min", inclusive="left"))
    bars_path, funding_path = _write_inputs(tmp_path, bars, start, end)
    output = tmp_path / "report.json"
    module = _load_script()
    arguments = [
        "--bars",
        str(bars_path),
        "--funding",
        str(funding_path),
        "--start",
        start.isoformat(),
        "--end",
        end.isoformat(),
        "--out",
        str(output),
    ]

    assert module.main(arguments) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["execution_authority"] == "none"
    assert module.main(arguments) == 1
