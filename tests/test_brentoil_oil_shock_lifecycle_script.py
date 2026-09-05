"""Command tests for immutable BRENTOIL oil-shock lifecycle evidence."""

from __future__ import annotations

from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Mapping

from pytest import raises


class _MarkSource:
    def __init__(self) -> None:
        self.revalidated = False

    def load(
        self, *, data_root: Path, symbol: str, start_ms: int, end_ms: int
    ) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
        assert data_root.name == "ws"
        assert symbol == "xyz:BRENTOIL"
        assert end_ms > start_ms
        return (), {"rows": 0, "files": [{"path": "mark-part", "sha256": "a"}]}

    def require_unchanged(self, evidence: Mapping[str, object]) -> None:
        assert evidence["rows"] == 0
        self.revalidated = True


def test_command_publishes_authority_none_waiting_report(tmp_path: Path) -> None:
    """A quiet prospective prefix publishes exact canary-bound evidence."""
    paths = _inputs(tmp_path)
    output = tmp_path / "report.json"
    source = _MarkSource()

    report = _script().run_command(_args(paths, output), mark_source=source)

    assert output.is_file()
    assert source.revalidated is True
    assert report["execution_authority"] == "none"
    assert report["technical_assessment"]["status"] == "WAITING_ELIGIBLE_ONSET"
    assert report["source"]["eligible_decisions"] == 0
    assert report["contract"]["notional_usd"] == 750.0
    assert report["contract"]["target_bps"] == 40.0
    assert report["contract"]["stop_bps"] == 30.0
    assert report["contract"]["stress_residual_bps_per_side"] == 8.464583786205068
    assert report["input_evidence"]["live_canary"]["path"].endswith("canary.json")
    assert report["input_evidence"]["decision_prefix"]["rows"] == 2
    assert report["source"]["observed_decisions"] == 1
    assert report["source"]["legacy_quiet_decisions_excluded"] == 1
    assert report["generator_identity"]


def test_build_report_does_not_publish_destination(tmp_path: Path) -> None:
    """A watcher can build exact evidence without creating a final artifact."""
    paths = _inputs(tmp_path)
    destination = tmp_path / "status.json"
    source = _MarkSource()

    report = _script().build_report(
        _args(paths, destination),
        destination=destination,
        mark_source=source,
    )

    assert report["technical_assessment"]["status"] == "WAITING_ELIGIBLE_ONSET"
    assert source.revalidated is True
    assert not destination.exists()


def test_command_rejects_canary_friction_mismatch_before_publish(
    tmp_path: Path,
) -> None:
    """A development stress value not backed by canary data fails closed."""
    paths = _inputs(tmp_path)
    development = json.loads(paths["development"].read_text())
    development["friction_contract"]["applied_strategy_execution"][
        "stress_slippage_bps_per_side"
    ] = 2.0
    paths["development"].write_text(json.dumps(development))
    output = tmp_path / "report.json"

    with raises(ValueError, match="stress"):
        _script().run_command(_args(paths, output), mark_source=_MarkSource())

    assert not output.exists()


def test_command_rejects_development_exit_contract_mismatch(tmp_path: Path) -> None:
    """A report cannot relabel a different tested exit as the frozen shadow."""
    paths = _inputs(tmp_path)
    development = json.loads(paths["development"].read_text())
    development["friction_contract"]["applied_strategy_execution"][
        "target_distance_bps"
    ] = 80.0
    paths["development"].write_text(json.dumps(development))

    with raises(ValueError, match="execution contract"):
        _script().run_command(
            _args(paths, tmp_path / "report.json"), mark_source=_MarkSource()
        )


def _script() -> ModuleType:
    path = Path("scripts/brentoil_oil_shock_lifecycle.py")
    spec = importlib.util.spec_from_file_location("brentoil_lifecycle_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("BRENTOIL lifecycle script is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _args(paths: dict[str, Path], output: Path) -> Namespace:
    return Namespace(
        journal=paths["journal"],
        candle_ledger=paths["candles"],
        book_ledger=paths["books"],
        mark_data_root=paths["mark_root"],
        development=paths["development"],
        live_canary=paths["canary"],
        observed_at_ms=1_800_000_300_500,
        output=output,
    )


def _inputs(root: Path) -> dict[str, Path]:
    paths = {
        "journal": root / "decisions.jsonl",
        "candles": root / "candles.jsonl",
        "books": root / "books.jsonl",
        "mark_root": root / "ws",
        "development": root / "development.json",
        "canary": root / "canary.json",
    }
    _jsonl(paths["journal"], _legacy_decision(), _decision())
    _jsonl(paths["candles"], _candle())
    _jsonl(paths["books"], _book())
    paths["development"].write_text(json.dumps(_development()))
    paths["canary"].write_text(json.dumps(_canary()))
    return paths


def _jsonl(path: Path, *rows: dict[str, object]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _legacy_decision() -> dict[str, object]:
    row = _decision()
    decision = row["decision"]
    if not isinstance(decision, dict):
        raise TypeError("decision fixture is invalid")
    decision["decision_time_ms"] = 1_800_000_000_000
    decision["observed_at_ms"] = 1_800_000_000_500
    for key in (
        "candle_open",
        "candle_high",
        "candle_low",
        "candle_close",
        "candle_volume",
        "signal_window_sha256",
        "signal_ohlc_source",
    ):
        decision.pop(key)
    row["event_id"] = "legacy-quiet"
    return row


def _decision() -> dict[str, object]:
    provider = "hip3_brentoil_oil_shock_reversion_bidirectional_5m_shadow_v1"
    decision_ms = 1_800_000_300_000
    return {
        "event_type": "brentoil_oil_shock_shadow_decision",
        "event_id": f"{provider}|xyz:BRENTOIL|{decision_ms}",
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": {
            "provider_id": provider,
            "profile_id": "brentoil_oil_shock_reversion_5m_shadow_v1",
            "symbol": "xyz:BRENTOIL",
            "decision_time_ms": decision_ms,
            "observed_at_ms": decision_ms + 500,
            "side": None,
            "eligible": False,
            "prospective": True,
            "non_action_reason": "no_shock_onset",
            "candle_open": 100.0,
            "candle_high": 100.3,
            "candle_low": 99.8,
            "candle_close": 100.1,
            "candle_volume": 20.0,
            "signal_window_sha256": "a" * 64,
            "signal_ohlc_source": "hyperliquid_public_candleSnapshot_5m",
            "execution_authority": "none",
        },
    }


def _candle() -> dict[str, object]:
    decision_ms = 1_800_000_300_000
    return {
        "schema_version": 1,
        "event_type": "brentoil_oil_shock_candle_observation",
        "symbol": "xyz:BRENTOIL",
        "source": "hyperliquid_public_candleSnapshot_5m",
        "bar_open_ms": decision_ms - 300_000,
        "bar_close_ms": decision_ms,
        "observed_at_ms": decision_ms + 500,
        "open": 100.0,
        "high": 100.3,
        "low": 99.8,
        "close": 100.1,
        "volume": 20.0,
        "historical_warmup": False,
        "prospective": True,
        "execution_authority": "none",
    }


def _book() -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": "brentoil_oil_shock_rest_books_v1",
        "execution_authority": "none",
        "payload": {
            "symbol": "xyz:BRENTOIL",
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": 1_800_000_300_498,
            "recv_ts_ms": 1_800_000_300_500,
            "bids": [
                {"price": 100.0 - index * 0.01, "size": 100.0} for index in range(10)
            ],
            "asks": [
                {"price": 100.2 + index * 0.01, "size": 100.0} for index in range(10)
            ],
        },
    }


def _development() -> dict[str, object]:
    return {
        "schema_version": "hip3_oil_shock_reversion_development_v1",
        "symbol": "xyz:BRENTOIL",
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "strategy_identity": {
            "timeframe": "5m",
            "config": {
                "return_lookback_bars": 12,
                "threshold_lookback_bars": 2016,
                "minimum_history_bars": 1000,
                "shock_quantile": 0.95,
                "target_bps": 40.0,
                "stop_bps": 30.0,
                "maximum_hold_bars": 12,
            },
        },
        "friction_contract": {
            "effective_taker_fee_rate": 0.0000864,
            "live_slippage_observations": 6,
            "live_stress_floor_bps_per_side": 8.464583786205068,
            "scaled_notional_usd": 750.0,
            "applied_strategy_execution": {
                "nominal_slippage_bps_per_side": 1.2230537631076595,
                "stress_slippage_bps_per_side": 8.464583786205068,
                "target_distance_bps": 40.0,
                "stop_distance_bps": 30.0,
                "maximum_hold_seconds": 3600,
            },
        },
        "scaled_account_hypothesis": {
            "account_equity_usd": 5000.0,
            "notional_usd": 750.0,
            "leverage": 5.0,
        },
    }


def _canary() -> dict[str, object]:
    return {
        "schema_version": "brentoil_live_canary_lifecycle_reconciliation_v1",
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "runtime_strategy_changed": False,
        "symbol": "xyz:BRENTOIL",
        "ledger_coverage": {
            "raw_fill_events": 7,
            "reconciled_closed_lifecycles": 3,
        },
        "current_liquidity_snapshot": {
            "global_hip3_volume_rank": 6,
            "day_notional_volume_usd": 49_403_551.84,
        },
        "conclusion": {"asset_data_available": True},
        "lifecycles": [
            {
                "entry": {"slippage_bps": 0.12},
                "exit": {"slippage_bps": -0.64},
            },
            {"entry": {"slippage_bps": -2.52}, "exit": {"slippage_bps": 6.37}},
            {
                "entry": {"slippage_bps": -1.49},
                "exit": {"slippage_bps": 8.464583786205068},
            },
        ],
    }
