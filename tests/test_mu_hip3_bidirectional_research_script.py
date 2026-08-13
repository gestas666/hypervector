"""Immutable report-only command contract for MU HIP-3 qualification."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from hypervector.data.hl import fetch_hl_ohlcv_snapshot
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

_SCRIPT = Path("scripts/mu_hip3_bidirectional_research.py")
_SPEC = importlib.util.spec_from_file_location("mu_hip3_research_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def test_default_candle_boundary_uses_full_retained_snapshot() -> None:
    defaults = _MODULE.run_command.__kwdefaults__

    assert defaults is not None
    assert defaults["candle_fetcher"] is fetch_hl_ohlcv_snapshot


def _candles() -> pd.DataFrame:
    index = pd.date_range("2026-01-05", periods=480, freq="15min", tz="UTC")
    close = 100.0 + np.sin(np.arange(480) / 13.0) * 8.0
    open_price = np.roll(close, 1)
    open_price[0] = close[0]
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": open_price,
            "high": np.maximum(open_price, close) + 1.0,
            "low": np.minimum(open_price, close) - 1.0,
            "close": close,
            "volume": 100.0,
            "source": "hl",
        }
    )


def _funding() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-05T00:00:00Z", "2026-01-10T23:00:00Z", freq="h"
            ),
            "funding_rate": 0.00001,
            "source": "hl_funding_history",
        }
    )


def _inputs(root: Path) -> tuple[Path, Path, Path, Path]:
    qualification = root / "qualification.json"
    liquidity = root / "liquidity.json"
    regular_audit = root / "regular.json"
    outside_audit = root / "outside.json"
    qualification.write_text(
        json.dumps(
            {
                "markets": [{"symbol": "xyz:MU", "max_leverage": 10}],
                "source": {"requested_end_ms": 1768003200000},
            }
        )
    )
    liquidity.write_text(
        json.dumps(
            {
                "profile": {
                    "symbol": "xyz:MU",
                    "fees": {"effective_taker_rate": 0.0000864},
                    "sessions": [
                        {
                            "session": "us_regular_hours",
                            "samples": 12,
                            "spread_bps": {"p90": 8.0, "p99": 12.0},
                        },
                        {
                            "session": "outside_us_regular_hours",
                            "samples": 12,
                            "spread_bps": {"p90": 16.0, "p99": 24.0},
                        },
                    ],
                    "notionals": [
                        {
                            "notional_usd": 75.0,
                            "both_complete_rate": 1.0,
                        }
                    ],
                }
            }
        )
    )
    regular_audit.write_text(json.dumps({"complete": True, "book_snapshots": 1}))
    outside_audit.write_text(json.dumps({"complete": True, "book_snapshots": 1}))
    return qualification, liquidity, regular_audit, outside_audit


def test_command_writes_immutable_report_and_sidecars(tmp_path: Path) -> None:
    qualification, liquidity, regular_audit, outside_audit = _inputs(tmp_path)
    report_path = tmp_path / "report.json"
    trades_path = tmp_path / "trades.parquet"
    sources_path = tmp_path / "sources.parquet"
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--regular-audit-report",
            str(regular_audit),
            "--outside-audit-report",
            str(outside_audit),
            "--output",
            str(report_path),
            "--trades-output",
            str(trades_path),
            "--sources-output",
            str(sources_path),
        ]
    )
    configs = (
        SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),
        SwingHaSignalConfig(9, 26, 5, "onset", "alignment_loss"),
    )

    report = _MODULE.run_command(
        args,
        candle_fetcher=lambda *_args, **_kwargs: _candles(),
        funding_fetcher=lambda *_args, **_kwargs: _funding(),
        configs=configs,
    )

    assert report_path.is_file() and trades_path.is_file() and sources_path.is_file()
    assert report["symbol"] == "xyz:MU"
    assert report["execution_authority"] == "none"
    assert report["automatic_promotion"] is False
    assert report["assessment"]["status"] == "RECENT_PROBE_DIAGNOSTIC_ONLY"
    assert report["assessment"]["research_supportive"] is False
    assert report["place_attempted"] is False
    assert report["proposed_provider_id"] == (
        "hip3_mu_recent_candle_probe_swing_ha_bidirectional_v1"
    )
    assert report["proposed_profile_id"] == (
        "mu_recent_candle_probe_swing_ha_bidirectional_research_v1"
    )
    assert set(report["partitions"]) == {"development", "validation", "holdout"}
    assert set(report["partitions"]["holdout"]["nominal"]["diagnostics"]) >= {
        "long",
        "short",
        "us_regular_hours",
        "outside_us_regular_hours",
    }
    assert report["source_sidecar"]["sha256"]
    assert report["trade_sidecar"]["sha256"]


def test_command_refuses_to_overwrite_immutable_outputs(tmp_path: Path) -> None:
    qualification, liquidity, regular_audit, outside_audit = _inputs(tmp_path)
    output = tmp_path / "exists.json"
    output.write_text("{}")
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--regular-audit-report",
            str(regular_audit),
            "--outside-audit-report",
            str(outside_audit),
            "--output",
            str(output),
            "--trades-output",
            str(tmp_path / "trades.parquet"),
            "--sources-output",
            str(tmp_path / "sources.parquet"),
        ]
    )

    try:
        _MODULE.run_command(
            args,
            candle_fetcher=lambda *_args, **_kwargs: _candles(),
            funding_fetcher=lambda *_args, **_kwargs: _funding(),
            configs=(SwingHaSignalConfig(),),
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("MU command overwrote immutable evidence")


def test_recent_probe_rejects_wrong_source_and_conflicting_duplicates() -> None:
    wrong_source = _candles()
    wrong_source["source"] = "binance"
    with pytest.raises(ValueError, match="Hyperliquid source"):
        _MODULE._official_bars(wrong_source)

    conflicting = pd.concat([_candles(), _candles().iloc[[0]]], ignore_index=True)
    conflicting.loc[conflicting.index[-1], "close"] += 1.0
    with pytest.raises(ValueError, match="conflicting duplicate"):
        _MODULE._official_bars(conflicting)


def test_recent_probe_records_identical_duplicate_count() -> None:
    duplicate = pd.concat([_candles(), _candles().iloc[[0]]], ignore_index=True)

    bars = _MODULE._official_bars(duplicate)

    assert bars.attrs["identical_duplicates_dropped"] == 1


def test_recent_probe_excludes_incomplete_terminal_candle() -> None:
    candles = _candles().iloc[:101].copy()
    last_open = pd.Timestamp(candles.iloc[-1]["timestamp"])
    cutoff = last_open + pd.Timedelta(minutes=10)

    bars = _MODULE._official_bars(
        candles,
        requested_end_ms=int(cutoff.timestamp() * 1_000),
    )

    assert len(bars) == 100
    assert last_open not in bars.index


def test_recent_probe_rejects_duplicate_output_paths(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    with pytest.raises(ValueError, match="distinct"):
        _MODULE._require_new(duplicate, duplicate, tmp_path / "source.parquet")


def test_recent_probe_report_failure_is_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    qualification, liquidity, regular, outside = _inputs(tmp_path)
    finals = (
        tmp_path / "atomic.json",
        tmp_path / "atomic.trades.parquet",
        tmp_path / "atomic.sources.parquet",
    )
    args = _MODULE.build_parser().parse_args(
        [
            "--qualification-report",
            str(qualification),
            "--liquidity-report",
            str(liquidity),
            "--regular-audit-report",
            str(regular),
            "--outside-audit-report",
            str(outside),
            "--output",
            str(finals[0]),
            "--trades-output",
            str(finals[1]),
            "--sources-output",
            str(finals[2]),
        ]
    )
    original = _MODULE._report
    monkeypatch.setattr(
        _MODULE,
        "_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")),
    )
    kwargs = {
        "candle_fetcher": lambda *_args, **_kwargs: _candles(),
        "funding_fetcher": lambda *_args, **_kwargs: _funding(),
        "configs": (SwingHaSignalConfig(7, 21, 3, "state", "ha_flip"),),
    }

    with pytest.raises(RuntimeError, match="injected"):
        _MODULE.run_command(args, **kwargs)
    assert not any(path.exists() for path in finals)

    monkeypatch.setattr(_MODULE, "_report", original)
    report = _MODULE.run_command(args, **kwargs)
    assert report["assessment"]["status"] == "RECENT_PROBE_DIAGNOSTIC_ONLY"
