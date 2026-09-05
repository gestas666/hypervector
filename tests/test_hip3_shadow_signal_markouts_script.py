"""Immutable publication boundary for HIP-3 prospective markouts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType


def _script() -> ModuleType:
    path = Path("scripts/hip3_shadow_signal_markouts.py")
    spec = importlib.util.spec_from_file_location("hip3_shadow_markouts_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HIP-3 markout script is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _decision() -> dict[str, object]:
    provider = "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1"
    return {
        "schema_version": 1,
        "event_type": "mu_hip3_breakout_shadow_decision",
        "event_id": f"{provider}|xyz:MU|900000",
        "report_only": True,
        "execution_authority": "none",
        "intents": [],
        "runtime_strategy_changed": False,
        "decision": {
            "provider_id": provider,
            "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
            "symbol": "xyz:MU",
            "decision_time_ms": 900_000,
            "observed_at_ms": 900_010,
            "side": "long",
            "eligible": True,
            "prospective": True,
            "pressure_fresh": True,
            "pressure_scan_complete": True,
            "pressure_state_history_complete": True,
            "execution_authority": "none",
        },
    }


def _book(recv_ms: int, bid: float, ask: float) -> dict[str, object]:
    return {
        "event_type": "book_observation",
        "profile_id": "mu_breakout_shadow_xyz:mu",
        "execution_authority": "none",
        "payload": {
            "symbol": "xyz:MU",
            "source": "hyperliquid_mainnet_l2_rest",
            "exchange_ts_ms": recv_ms - 1,
            "recv_ts_ms": recv_ms,
            "bids": [{"price": bid - index * 0.01, "size": 1.0} for index in range(10)],
            "asks": [{"price": ask + index * 0.01, "size": 1.0} for index in range(10)],
        },
    }


def _diagnostic() -> dict[str, object]:
    return {
        "schema_version": "mu_development_path_threshold_diagnostic_v1",
        "symbol": "xyz:MU",
        "execution_authority": "none",
        "automatic_promotion": False,
        "validation_accessed": False,
        "holdout_accessed": False,
        "qualification_abort_preserved": True,
        "diagnostic": {
            "track": {
                "provider_id": "hip3_mu_full_l2_breakout_pressure_bidirectional_15m_v1",
                "profile_id": "mu_full_l2_breakout_pressure_bidirectional_15m_research_v1",
                "timeframe": "15m",
                "family": "breakout_pressure",
                "config": {
                    "breakout_lookback_bars": 32,
                    "fast_ema": 9,
                    "slow_ema": 21,
                    "minimum_abs_imbalance": 0.1,
                    "maximum_stop_bps": 80.0,
                },
            }
        },
        "inputs": {"nominal_latency_bps_per_side": 1.0},
    }


def _arguments(tmp_path: Path) -> tuple[ModuleType, list[str], Path]:
    script = _script()
    journal, books = tmp_path / "journal.jsonl", tmp_path / "books.jsonl"
    diagnostic, fee = tmp_path / "diagnostic.json", tmp_path / "fee.json"
    output = tmp_path / "markouts.json"
    _write_jsonl(journal, [_decision()])
    _write_jsonl(
        books,
        [_book(900_011, 100.0, 100.2), _book(1_800_011, 101.0, 101.2)],
    )
    diagnostic.write_text(json.dumps(_diagnostic()))
    fee.write_text(
        json.dumps(
            {
                "report_only": True,
                "execution_authority": "none",
                "profile": {
                    "symbol": "xyz:MU",
                    "fees": {"one_way_taker_fee_bps": 0.864},
                },
            }
        )
    )
    arguments = [
        "--symbol",
        "xyz:MU",
        "--journal",
        str(journal),
        "--book-ledger",
        str(books),
        "--development-diagnostic",
        str(diagnostic),
        "--fee-evidence",
        str(fee),
        "--output",
        str(output),
        "--horizon-minutes",
        "15",
    ]
    return script, arguments, output


def test_script_binds_frozen_route_friction_and_immutable_inputs(
    tmp_path: Path,
) -> None:
    """Published markouts must retain exact route and evidence hashes."""
    script, arguments, output = _arguments(tmp_path)
    args = script.build_parser().parse_args(arguments)

    report = script.run_command(args)

    assert report["symbol"] == "xyz:MU"
    assert report["contract"]["fee_bps_per_side"] == 0.864
    assert report["contract"]["residual_latency_bps_per_side"] == 1.0
    assert report["markouts"]["horizons"]["15"]["coverage"]["resolved"] == 1
    assert set(report["input_evidence"]) == {
        "journal",
        "book_ledger",
        "development_diagnostic",
        "fee_evidence",
    }
    assert output.is_file()
