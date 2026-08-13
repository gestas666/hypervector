"""Standalone prospective HIP-3 candle-parity command tests."""

from __future__ import annotations

from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
from pytest import raises

from hypervector.data.hl_events import PublicTradeEvent
from hypervector.research.hip3_prospective_candle_parity import (
    Hip3ProspectiveCandleParityConfig,
    build_hip3_prospective_candle_parity,
)

_SCRIPT = Path(__file__).parents[1] / "scripts" / "hip3_prospective_candle_parity.py"
_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_END_MS = _START_MS + _BAR_MS
_SYMBOL = "xyz:SKHX"


class _Archive:
    def __init__(self, trades: tuple[PublicTradeEvent, ...]) -> None:
        self._trades = trades

    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        return self._trades


class _Candles:
    def completed_candles(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        observed_at_ms: int,
    ) -> pd.DataFrame:
        assert (symbol, start_ms, end_ms, observed_at_ms) == (
            _SYMBOL,
            _START_MS,
            _END_MS,
            _END_MS,
        )
        return _candles()


def test_command_binds_path_audit_and_publishes_no_authority_report(
    tmp_path: Path,
) -> None:
    module = _module()
    trades = _trades()
    path_audit = tmp_path / "path.json"
    output = tmp_path / "parity.json"
    _write_path_audit(path_audit, trades)

    report = module.run_command(
        _args(path_audit, output),
        archive=_Archive(trades),
        candle_source=_Candles(),
    )

    assert report["technical_assessment"] == {
        "candle_ohlc_parity_resolved": True,
        "prospective_risk_path_coverage_resolved": True,
        "unresolved_bars": 0,
    }
    assert report["path_audit_evidence"]["path"] == str(path_audit.resolve())
    assert report["contract"]["execution_authority"] == "none"
    assert json.loads(output.read_text()) == report
    with raises(FileExistsError):
        module.run_command(
            _args(path_audit, output),
            archive=_Archive(trades),
            candle_source=_Candles(),
        )


def test_command_reports_candle_parity_despite_independent_mark_gap(
    tmp_path: Path,
) -> None:
    """Missing mark risk evidence must not suppress exact candle comparison."""
    module = _module()
    trades = _trades()
    path_audit = tmp_path / "path.json"
    _write_path_audit(path_audit, trades)
    payload = json.loads(path_audit.read_text())
    payload["technical_assessment"] = {
        "prospective_bar_path_coverage_resolved": False,
        "unresolved_bars": 1,
    }
    path_audit.write_text(json.dumps(payload))

    report = module.run_command(
        _args(path_audit, tmp_path / "parity.json"),
        archive=_Archive(trades),
        candle_source=_Candles(),
    )

    assert report["technical_assessment"] == {
        "candle_ohlc_parity_resolved": True,
        "prospective_risk_path_coverage_resolved": False,
        "unresolved_bars": 0,
    }


def test_command_rejects_path_audit_symbol_mismatch(tmp_path: Path) -> None:
    module = _module()
    trades = _trades()
    path_audit = tmp_path / "path.json"
    output = tmp_path / "parity.json"
    _write_path_audit(path_audit, trades, symbol="xyz:MU")

    with raises(ValueError, match="path audit symbol"):
        module.run_command(
            _args(path_audit, output),
            archive=_Archive(trades),
            candle_source=_Candles(),
        )


def test_command_rejects_archive_trade_identity_mismatch(tmp_path: Path) -> None:
    module = _module()
    trades = _trades()
    path_audit = tmp_path / "path.json"
    output = tmp_path / "parity.json"
    _write_path_audit(path_audit, trades)

    with raises(ValueError, match="trade evidence does not match path audit"):
        module.run_command(
            _args(path_audit, output),
            archive=_Archive(trades[:-1]),
            candle_source=_Candles(),
        )


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_prospective_candle_parity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(path_audit: Path, output: Path) -> Namespace:
    return Namespace(
        symbol=_SYMBOL,
        data_root=Path("data"),
        path_audit=path_audit,
        output=output,
    )


def _write_path_audit(
    path: Path,
    trades: tuple[PublicTradeEvent, ...],
    *,
    symbol: str = _SYMBOL,
) -> None:
    parity = build_hip3_prospective_candle_parity(
        public_trades=trades,
        candles=_candles(),
        config=Hip3ProspectiveCandleParityConfig(
            _SYMBOL,
            _START_MS,
            _END_MS,
            _END_MS,
        ),
    )
    payload = {
        "schema_version": "hip3_prospective_path_audit_v1",
        "contract": {"report_only": True, "execution_authority": "none"},
        "source": {"symbol": symbol, "observed_at_ms": _END_MS},
        "coverage": {
            "first_full_bar_open_ms": _START_MS,
            "completed_bar_end_ms": _END_MS,
            "completed_bars": 1,
            "timeframe_minutes": 15,
        },
        "evidence_identity": {
            "trades": {
                "rows": len(trades),
                "sha256": parity["source"]["trade_sha256"],
            },
            "completed_bar_trades": {
                "rows": parity["source"]["comparison_trade_rows"],
                "sha256": parity["source"]["comparison_trade_sha256"],
            },
        },
        "technical_assessment": {
            "prospective_bar_path_coverage_resolved": True,
            "unresolved_bars": 0,
        },
    }
    path.write_text(json.dumps(payload))


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([_START_MS], unit="ms", utc=True),
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
        }
    )


def _trades() -> tuple[PublicTradeEvent, ...]:
    return tuple(
        _trade(offset_ms, trade_id, price)
        for offset_ms, trade_id, price in (
            (10_000, 1, 100.0),
            (20_000, 2, 102.0),
            (30_000, 3, 99.0),
            (40_000, 4, 101.0),
        )
    )


def _trade(offset_ms: int, trade_id: int, price: float) -> PublicTradeEvent:
    timestamp = _START_MS + offset_ms
    return PublicTradeEvent(
        _SYMBOL,
        "buy",
        price,
        1.0,
        f"0x{trade_id}",
        timestamp,
        timestamp * 1_000_000 + 1_000,
        trade_id,
        "buyer",
        "seller",
    )
