"""Standalone prospective HIP-3 signal-source parity command tests."""

from __future__ import annotations

from argparse import Namespace
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
from pytest import raises

from hypervector.data.hl_events import (
    AssetContextEvent,
    BookLevel,
    L2SnapshotEvent,
    PublicTradeEvent,
)
from hypervector.data.oxa_storage import file_evidence
from hypervector.research.hip3_prospective_candle_parity import (
    Hip3ProspectiveCandleParityConfig,
    build_hip3_prospective_candle_parity,
)
from hypervector.research.hip3_prospective_path_audit import (
    Hip3ProspectivePathAuditConfig,
    build_hip3_prospective_path_audit,
)

_SCRIPT = Path(__file__).parents[1] / "scripts/hip3_prospective_signal_parity.py"
_BAR_MS = 15 * 60_000
_START_MS = 1_800_000_000_000
_END_MS = _START_MS + 5 * _BAR_MS
_SYMBOL = "xyz:MU"
_V51_INDEX_SPEC = (
    Path(__file__).parents[1]
    / "docs/research-journal/v51-index-source-parity-forward-v1.json"
)


class _Archive:
    def replay_trades(self) -> tuple[PublicTradeEvent, ...]:
        return _trades()

    def replay_l2(self) -> tuple[L2SnapshotEvent, ...]:
        return _books()


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


def test_command_binds_route_and_publishes_report_only_signal_parity(
    tmp_path: Path,
) -> None:
    module = _module()
    path_audit, candle_parity, diagnostic = _evidence(tmp_path)
    output = tmp_path / "signal.json"

    report = module.run_command(
        _args(path_audit, candle_parity, diagnostic, output),
        archive=_Archive(),
        candle_source=_Candles(),
    )

    assert report["scope"]["provider_id"] == "mu_prospective_test_v1"
    assert report["technical_assessment"] == {
        "prospective_signal_source_parity_resolved": True,
        "prospective_entry_signal_parity_non_vacuous": True,
        "prospective_risk_path_coverage_resolved": True,
        "unresolved_pressure_bars": 0,
        "signal_disagreement_bars": 0,
    }
    assert report["contract"]["execution_authority"] == "none"
    assert json.loads(output.read_text()) == report


def test_command_keeps_mark_gap_as_promotion_blocker_not_signal_blocker(
    tmp_path: Path,
) -> None:
    """Signal parity remains measurable while exact risk-path status stays false."""
    module = _module()
    path_audit, candle_parity, diagnostic = _evidence(tmp_path)
    payload = json.loads(path_audit.read_text())
    payload["technical_assessment"] = {
        "prospective_bar_path_coverage_resolved": False,
        "unresolved_bars": 1,
    }
    path_audit.write_text(json.dumps(payload))
    _write_candle_parity(candle_parity, path_audit)

    report = module.run_command(
        _args(path_audit, candle_parity, diagnostic, tmp_path / "signal.json"),
        archive=_Archive(),
        candle_source=_Candles(),
    )

    assert (
        report["technical_assessment"]["prospective_signal_source_parity_resolved"]
        is True
    )
    assert (
        report["technical_assessment"]["prospective_risk_path_coverage_resolved"]
        is False
    )


def test_command_rejects_selected_route_symbol_alias(tmp_path: Path) -> None:
    module = _module()
    path_audit, candle_parity, diagnostic = _evidence(tmp_path)
    payload = json.loads(diagnostic.read_text())
    payload["symbol"] = "xyz:SKHX"
    diagnostic.write_text(json.dumps(payload))

    with raises(ValueError, match="selected route symbol"):
        module.run_command(
            _args(path_audit, candle_parity, diagnostic, tmp_path / "signal.json"),
            archive=_Archive(),
            candle_source=_Candles(),
        )


def test_v51_index_route_spec_freezes_exact_sp500_signal_identity() -> None:
    """Prospective parity must not alias v3 index inputs to an older provider."""
    module = _module()

    config = module._route_config(_V51_INDEX_SPEC, "xyz:SP500")

    assert config.symbol == "xyz:SP500"
    assert config.provider_id == (
        "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3"
    )
    assert config.profile_id == "sp500_fresh15_pressure_shadow_research_v3"
    assert config.breakout.breakout_lookback_bars == 32
    assert config.breakout.fast_ema == 21
    assert config.breakout.slow_ema == 55
    assert config.breakout.minimum_abs_imbalance == 0.1
    assert config.breakout.maximum_stop_bps == 120.0


def test_command_rejects_l2_prefix_that_differs_from_path_audit(
    tmp_path: Path,
) -> None:
    module = _module()
    path_audit, candle_parity, diagnostic = _evidence(tmp_path)

    class _MissingBookArchive(_Archive):
        def replay_l2(self) -> tuple[L2SnapshotEvent, ...]:
            return _books()[:-1]

    with raises(ValueError, match="L2 evidence does not match path audit"):
        module.run_command(
            _args(path_audit, candle_parity, diagnostic, tmp_path / "signal.json"),
            archive=_MissingBookArchive(),
            candle_source=_Candles(),
        )


def test_command_rejects_refetched_candles_that_differ_from_frozen_parity(
    tmp_path: Path,
) -> None:
    module = _module()
    path_audit, candle_parity, diagnostic = _evidence(tmp_path)

    class _ChangedCandles(_Candles):
        def completed_candles(self, **kwargs: object) -> pd.DataFrame:
            candles = super().completed_candles(**kwargs)
            candles.loc[0, "close"] = 99.9
            return candles

    with raises(ValueError, match="candle evidence changed since parity audit"):
        module.run_command(
            _args(path_audit, candle_parity, diagnostic, tmp_path / "signal.json"),
            archive=_Archive(),
            candle_source=_ChangedCandles(),
        )


def _module() -> ModuleType:
    spec = spec_from_file_location("hip3_prospective_signal_parity_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(
    path_audit: Path, candle_parity: Path, diagnostic: Path, output: Path
) -> Namespace:
    return Namespace(
        symbol=_SYMBOL,
        data_root=Path("data"),
        path_audit=path_audit,
        candle_parity=candle_parity,
        development_diagnostic=diagnostic,
        output=output,
    )


def _evidence(tmp_path: Path) -> tuple[Path, Path, Path]:
    path_audit = tmp_path / "path.json"
    candle_parity = tmp_path / "candle.json"
    diagnostic = tmp_path / "development.json"
    path_report = build_hip3_prospective_path_audit(
        l2_snapshots=_books(),
        public_trades=_trades(),
        asset_contexts=_marks(),
        stream_gaps=(),
        observed_at_ms=_END_MS,
        config=Hip3ProspectivePathAuditConfig(_SYMBOL),
    )
    path_audit.write_text(json.dumps(path_report))
    _write_candle_parity(candle_parity, path_audit)
    _write_diagnostic(diagnostic)
    return path_audit, candle_parity, diagnostic


def _write_candle_parity(path: Path, audit_path: Path) -> None:
    report = build_hip3_prospective_candle_parity(
        public_trades=_trades(),
        candles=_candles(),
        config=Hip3ProspectiveCandleParityConfig(_SYMBOL, _START_MS, _END_MS, _END_MS),
    )
    report["path_audit_evidence"] = {
        "path": str(audit_path.resolve()),
        **file_evidence(audit_path),
    }
    path.write_text(json.dumps(report))


def _write_diagnostic(path: Path) -> None:
    payload = {
        "schema_version": "hip3_development_only_diagnostic_v1",
        "symbol": _SYMBOL,
        "execution_authority": "none",
        "report_only": True,
        "development_selected_track": {
            "symbol": _SYMBOL,
            "family": "breakout_pressure",
            "timeframe": "15m",
            "provider_id": "mu_prospective_test_v1",
            "profile_id": "mu_prospective_profile_test_v1",
            "config": {
                "breakout_lookback_bars": 2,
                "fast_ema": 2,
                "slow_ema": 3,
                "minimum_abs_imbalance": 0.1,
                "maximum_stop_bps": 80.0,
            },
        },
    }
    path.write_text(json.dumps(payload))


def _candles() -> pd.DataFrame:
    close = [100.0, 101.0, 102.0, 104.0, 103.0]
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [_START_MS + offset * _BAR_MS for offset in range(5)],
                unit="ms",
                utc=True,
            ),
            "open": close,
            "high": [100.5, 101.5, 102.5, 104.5, 103.5],
            "low": [99.5, 100.5, 101.5, 101.5, 102.5],
            "close": close,
        }
    )


def _trades() -> tuple[PublicTradeEvent, ...]:
    rows: list[PublicTradeEvent] = []
    for bar, candle in _candles().iterrows():
        bar_open = _START_MS + bar * _BAR_MS
        for offset, field in enumerate(("open", "high", "low", "close"), start=1):
            timestamp = bar_open + offset * 1_000
            trade_id = bar * 10 + offset
            rows.append(_trade(timestamp, trade_id, float(candle[field])))
    return tuple(rows)


def _books() -> tuple[L2SnapshotEvent, ...]:
    rows: list[L2SnapshotEvent] = []
    for bar in range(5):
        bar_open = _START_MS + bar * _BAR_MS
        for offset in range(0, _BAR_MS, 10_000):
            rows.append(_book(bar_open + offset, positive=bar >= 3))
    return tuple(rows)


def _marks() -> tuple[AssetContextEvent, ...]:
    return tuple(
        _mark(_START_MS + offset) for offset in range(0, _END_MS - _START_MS, 5_000)
    )


def _trade(timestamp: int, trade_id: int, price: float) -> PublicTradeEvent:
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


def _book(timestamp: int, *, positive: bool) -> L2SnapshotEvent:
    bid_size, ask_size = (9.0, 1.0) if positive else (5.0, 5.0)
    return L2SnapshotEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 1_000,
        tuple(BookLevel(99.0 - offset, bid_size, 1) for offset in range(10)),
        tuple(BookLevel(101.0 + offset, ask_size, 1) for offset in range(10)),
    )


def _mark(timestamp: int) -> AssetContextEvent:
    return AssetContextEvent(
        _SYMBOL,
        timestamp,
        timestamp * 1_000_000 + 2_000,
        100.0,
        100.1,
        0.00001,
        10_000.0,
        100.0,
    )
