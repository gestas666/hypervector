#!/usr/bin/env python3
"""Replay frozen BTC and SOL completed outcomes through one shared account."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from hypervector.data.oxa_storage import file_evidence, write_immutable_json
from hypervector.research.shared_trade_portfolio import (
    SharedTradeOutcome,
    SharedTradeReplayConfig,
    SharedTradeReplayReport,
    replay_shared_trade_outcomes,
)

_INITIAL_EQUITY_USD = 15_000.0
_BTC_MARGIN_FRACTION = 0.35
_BTC_LEVERAGE = 30.0
_BTC_ENTRY_FEE_RATE = 0.00015
_SOL_MARGIN_FRACTION = 0.03
_SOL_LEVERAGE = 5.0
_SOL_EFFECTIVE_EXPOSURE = _SOL_MARGIN_FRACTION * _SOL_LEVERAGE
_SOL_CAPITAL_BASE_CAP_USD = 15_000.0
_SOL_NOTIONAL_CAP_USD = _SOL_CAPITAL_BASE_CAP_USD * _SOL_EFFECTIVE_EXPOSURE
_SOL_TRIAL_ID = "stop=60__exposure=0.15"


def experiment_contract() -> dict[str, object]:
    """Return the immutable report-only comparison boundary."""
    return {
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "observe",
        "runtime_strategy_changed": False,
        "initial_equity_usd": _INITIAL_EQUITY_USD,
        "one_position_per_symbol": True,
        "maximum_symbols_concurrent": 2,
        "btc_margin_fraction": _BTC_MARGIN_FRACTION,
        "btc_leverage": _BTC_LEVERAGE,
        "sol_margin_fraction": _SOL_MARGIN_FRACTION,
        "sol_leverage": _SOL_LEVERAGE,
        "sol_effective_exposure": _SOL_EFFECTIVE_EXPOSURE,
        "sol_capital_base_cap_usd": _SOL_CAPITAL_BASE_CAP_USD,
        "sol_notional_cap_usd": _SOL_NOTIONAL_CAP_USD,
        "evidence_lane_caps_each_trade_at_source_equity": True,
    }


def btc_outcomes(payload: dict[str, object]) -> tuple[SharedTradeOutcome, ...]:
    """Adapt the frozen 35%/30x source-follow completed trades."""
    contract = _mapping(payload, "experiment_contract")
    _expect_number(contract, "allocation_fraction", _BTC_MARGIN_FRACTION)
    _expect_number(contract, "leverage", _BTC_LEVERAGE)
    _expect_number(contract, "initial_equity", _INITIAL_EQUITY_USD)
    replay = _mapping(_mapping(payload, "event_replays"), "strict_tuned")
    trades = _mapping_rows(replay, "trades")
    return tuple(_btc_outcome(index, trade) for index, trade in enumerate(trades))


def _btc_outcome(index: int, trade: dict[str, object]) -> SharedTradeOutcome:
    margin = _number(trade, "margin")
    notional = _number(trade, "notional")
    entry_fee = notional * _BTC_ENTRY_FEE_RATE
    if entry_fee > _number(trade, "fees") + 1e-9:
        raise ValueError("BTC derived entry fee exceeds total trade fees")
    return SharedTradeOutcome(
        trade_id=f"btc-{index:04d}-{_text(trade, 'entry_time_utc')}",
        symbol="BTC",
        entry_time_ms=_timestamp_ms(_text(trade, "entry_time_utc")),
        exit_time_ms=_timestamp_ms(_text(trade, "exit_time_utc")),
        source_equity_usd=margin / _BTC_MARGIN_FRACTION,
        margin_fraction=_BTC_MARGIN_FRACTION,
        entry_fee_usd=entry_fee,
        net_pnl_usd=_number(trade, "net_pnl"),
        outcome=_text(trade, "status"),
    )


def sol_outcomes(
    payloads: tuple[dict[str, object], ...],
) -> tuple[SharedTradeOutcome, ...]:
    """Adapt every non-overlapping frozen SOL clean-block outcome."""
    outcomes = [
        _sol_outcome(block_index, trade_index, trade)
        for block_index, payload in enumerate(payloads)
        for trade_index, trade in enumerate(_sol_trade_rows(payload))
    ]
    return tuple(outcomes)


def _sol_trade_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    if _text(payload, "symbol") != "SOL":
        raise ValueError("SOL artifact symbol mismatch")
    if _text(payload, "execution_authority") != "none":
        raise ValueError("SOL artifact has execution authority")
    continuous = _mapping(payload, "continuous")
    trials = _mapping_rows(continuous, "trials")
    trial = next(
        (row for row in trials if row.get("trial_id") == _SOL_TRIAL_ID),
        None,
    )
    if trial is None:
        raise ValueError(f"SOL artifact is missing {_SOL_TRIAL_ID}")
    replay = _mapping(trial, "event_replay")
    if _text(replay, "status") != "complete":
        raise ValueError("SOL public event replay must be complete")
    return _mapping_rows(replay, "trades")


def _sol_outcome(
    block_index: int,
    trade_index: int,
    trade: dict[str, object],
) -> SharedTradeOutcome:
    source_equity = _number(trade, "equity_before_usd")
    margin = _number(trade, "isolated_margin_usd")
    margin_fraction = margin / source_equity
    if not math.isclose(margin_fraction, _SOL_MARGIN_FRACTION, abs_tol=1e-9):
        raise ValueError("SOL trade does not use the frozen 3% margin fraction")
    return SharedTradeOutcome(
        trade_id=f"sol-{block_index:02d}-{trade_index:03d}",
        symbol="SOL",
        entry_time_ms=_integer(trade, "entry_snapshot_time_ms"),
        exit_time_ms=_integer(trade, "exit_snapshot_time_ms"),
        source_equity_usd=source_equity,
        margin_fraction=margin_fraction,
        entry_fee_usd=_number(trade, "entry_fee_usd"),
        net_pnl_usd=_number(trade, "net_pnl_usd"),
        outcome=_text(trade, "exit_reason"),
    )


def build_report(
    btc_payload: dict[str, object],
    sol_payloads: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Build capped and uncapped shared-capital diagnostics."""
    btc = btc_outcomes(btc_payload)
    sol = sol_outcomes(sol_payloads)
    all_outcomes = btc + sol
    dynamic = SharedTradeReplayConfig(_INITIAL_EQUITY_USD)
    capped = SharedTradeReplayConfig(
        _INITIAL_EQUITY_USD,
        {"SOL": _SOL_CAPITAL_BASE_CAP_USD},
    )
    evidence_capped = SharedTradeReplayConfig(
        _INITIAL_EQUITY_USD,
        {"SOL": _SOL_CAPITAL_BASE_CAP_USD},
        cap_at_source_equity=True,
    )
    reports = {
        "btc_only": replay_shared_trade_outcomes(btc, dynamic),
        "sol_only_dynamic": replay_shared_trade_outcomes(sol, dynamic),
        "combined_dynamic": replay_shared_trade_outcomes(all_outcomes, dynamic),
        "combined_sol_capacity_capped": replay_shared_trade_outcomes(
            all_outcomes,
            capped,
        ),
        "combined_evidence_capped": replay_shared_trade_outcomes(
            all_outcomes,
            evidence_capped,
        ),
    }
    _verify_btc_identity(btc_payload, reports["btc_only"])
    return _render_report(reports, len(btc), len(sol))


def _render_report(
    reports: dict[str, SharedTradeReplayReport],
    btc_count: int,
    sol_count: int,
) -> dict[str, object]:
    btc = reports["btc_only"]
    capped = reports["combined_sol_capacity_capped"]
    evidence = reports["combined_evidence_capped"]
    return {
        "schema": "btc_sol_shared_trade_diagnostic_v1",
        "experiment_contract": experiment_contract(),
        "input_trade_counts": {"BTC": btc_count, "SOL": sol_count},
        "reports": {name: report.to_dict() for name, report in reports.items()},
        "comparison": {
            "capped_combined_minus_btc_final_equity_usd": (
                capped.final_equity_usd - btc.final_equity_usd
            ),
            "capped_combined_minus_btc_drawdown_pct": (
                capped.realized_maximum_drawdown_pct - btc.realized_maximum_drawdown_pct
            ),
            "evidence_combined_minus_btc_final_equity_usd": (
                evidence.final_equity_usd - btc.final_equity_usd
            ),
            "evidence_combined_minus_btc_drawdown_pct": (
                evidence.realized_maximum_drawdown_pct
                - btc.realized_maximum_drawdown_pct
            ),
        },
        "limitations": [
            "completed outcomes are scaled linearly rather than re-matched at new size",
            "funding is applied at exit because per-settlement rows are absent here",
            "realized equity excludes concurrent intratrade mark-to-market movement",
            "SOL is absent during declared provider gaps rather than imputed",
            "five SOL blocks remain sampled-mark censored",
            "fresh no-submit shared forward evidence is required before execution",
        ],
    }


def _verify_btc_identity(
    payload: dict[str, object],
    report: SharedTradeReplayReport,
) -> None:
    summary = _mapping(_mapping(payload, "summaries"), "strict_tuned")
    expected = _number(summary, "final_equity")
    if not math.isclose(report.final_equity_usd, expected, abs_tol=0.01):
        raise ValueError("shared adapter does not reproduce BTC source final equity")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse immutable source artifacts and output path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btc-artifact", type=Path, required=True)
    parser.add_argument("--sol-artifact", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _load(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"shared diagnostic input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"shared diagnostic input must be an object: {path}")
    return payload


def _mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _mapping_rows(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{key} must be an object list")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be non-empty text")
    return value


def _expect_number(payload: dict[str, object], key: str, expected: float) -> None:
    if not math.isclose(_number(payload, key), expected, abs_tol=1e-12):
        raise ValueError(f"{key} must be {expected}")


def _timestamp_ms(value: str) -> int:
    from datetime import datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("trade timestamp must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def main(argv: list[str] | None = None) -> int:
    """Run the report-only shared outcome diagnostic."""
    args = parse_args(argv)
    btc = _load(args.btc_artifact)
    sol = tuple(_load(path) for path in args.sol_artifact)
    payload = build_report(btc, sol)
    payload["source_evidence"] = {
        "btc": file_evidence(args.btc_artifact),
        "sol": [file_evidence(path) for path in args.sol_artifact],
    }
    write_immutable_json(args.output, payload)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
