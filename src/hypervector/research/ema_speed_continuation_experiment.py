"""Frozen development-only orchestration for EMA-speed continuation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping

import pandas as pd

from hypervector.data.oxa_storage import file_evidence
from hypervector.research.ema_speed_continuation_data import load_ema_speed_inputs
from hypervector.research.ema_speed_continuation_replay import (
    EmaSpeedSymbolResult,
    combine_ema_speed_reports,
    evaluate_ema_speed_symbol,
)
from hypervector.research.liquidity_sweep_experiment import (
    DevelopmentFold,
    build_development_folds,
)
from hypervector.research.market_cipher_data import (
    attach_hourly_funding,
    load_verified_hourly_funding,
)
from hypervector.research.shared_trade_portfolio import SharedTradeReplayReport


_START = pd.Timestamp("2025-05-01T00:00:00Z")
_END = pd.Timestamp("2026-05-01T00:00:00Z")
_SYMBOLS = ("BTC", "SOL")
_SCENARIOS = {"nominal": 2.0, "stress": 5.0}


@dataclass(frozen=True)
class EmaSpeedDevelopmentResult:
    """Immutable report payload plus exact lifecycle sidecar rows."""

    report: dict[str, object]
    trades: pd.DataFrame


def registered_development_folds() -> tuple[DevelopmentFold, ...]:
    """Return the three purged intervals fixed before result inspection."""
    return build_development_folds(_START.to_pydatetime(), _END.to_pydatetime())


def assess_ema_speed_development(
    *,
    pooled_nominal: Mapping[str, object],
    pooled_stress: Mapping[str, object],
    stress_folds: tuple[Mapping[str, object], ...],
    side_stress: Mapping[str, Mapping[str, object]],
    technical_ready: bool,
) -> dict[str, object]:
    """Apply only the preregistered economic and technical conditions."""
    pooled_pass = _pooled_pass(pooled_nominal) and _pooled_pass(pooled_stress)
    folds_pass = len(stress_folds) == 3 and all(
        _number(fold, "net_pnl_usd") > 0.0 for fold in stress_folds
    )
    sides_pass = set(side_stress) == {"long", "short"} and all(
        _number(side_stress[side], "net_pnl_usd") > 0.0 for side in ("long", "short")
    )
    economic = pooled_pass and folds_pass and sides_pass
    status = "validation_eligible_not_opened"
    if not economic:
        status = "rejected_development_economics"
    elif not technical_ready:
        status = "not_suitable_technical_path_unresolved"
    return {
        "economic_acceptance": economic,
        "technical_acceptance": technical_ready,
        "validation_open_authorized": economic and technical_ready,
        "retuning_authorized": False,
        "status": status,
    }


def run_ema_speed_development(
    database_path: Path,
    funding_paths: Mapping[str, tuple[Path, ...]],
) -> EmaSpeedDevelopmentResult:
    """Evaluate only the frozen development scope under nominal and stress costs."""
    _validate_funding_paths(funding_paths)
    generator_before = _generator_evidence()
    funding_before = _funding_evidence(funding_paths)
    markets = {
        symbol: _load_market(database_path, symbol, funding_paths[symbol])
        for symbol in _SYMBOLS
    }
    full, folds = _evaluate_all(markets)
    report = _build_report(database_path, markets, full, folds, funding_before)
    trades = _trade_rows(full, folds)
    if generator_before != _generator_evidence():
        raise RuntimeError("EMA-speed generator changed during development replay")
    if funding_before != _funding_evidence(funding_paths):
        raise RuntimeError("EMA-speed funding evidence changed during replay")
    return EmaSpeedDevelopmentResult(report, trades)


def _load_market(
    database_path: Path,
    symbol: str,
    funding_paths: tuple[Path, ...],
) -> pd.DataFrame:
    inputs = load_ema_speed_inputs(
        database_path,
        symbol,
        _START.to_pydatetime(),
        _END.to_pydatetime(),
    )
    funding = load_verified_hourly_funding(list(funding_paths), _START, _END)
    return attach_hourly_funding(inputs.bars, funding)


def _evaluate_all(
    markets: Mapping[str, pd.DataFrame],
) -> tuple[
    dict[str, tuple[EmaSpeedSymbolResult, ...]],
    dict[str, tuple[tuple[EmaSpeedSymbolResult, ...], ...]],
]:
    full: dict[str, tuple[EmaSpeedSymbolResult, ...]] = {}
    folded: dict[str, tuple[tuple[EmaSpeedSymbolResult, ...], ...]] = {}
    folds = registered_development_folds()
    for scenario, slippage in _SCENARIOS.items():
        full[scenario] = _evaluate_markets(markets, slippage)
        folded[scenario] = tuple(
            _evaluate_markets(_slice_markets(markets, fold), slippage) for fold in folds
        )
    return full, folded


def _evaluate_markets(
    markets: Mapping[str, pd.DataFrame],
    slippage: float,
) -> tuple[EmaSpeedSymbolResult, ...]:
    return tuple(
        evaluate_ema_speed_symbol(markets[symbol], symbol, slippage)
        for symbol in _SYMBOLS
    )


def _slice_markets(
    markets: Mapping[str, pd.DataFrame],
    fold: DevelopmentFold,
) -> dict[str, pd.DataFrame]:
    return {
        symbol: frame.loc[
            frame.index.to_series().ge(fold.start_utc)
            & frame.index.to_series().lt(fold.end_utc)
        ].copy()
        for symbol, frame in markets.items()
    }


def _build_report(
    database_path: Path,
    markets: Mapping[str, pd.DataFrame],
    full: Mapping[str, tuple[EmaSpeedSymbolResult, ...]],
    folds: Mapping[str, tuple[tuple[EmaSpeedSymbolResult, ...], ...]],
    funding_evidence: dict[str, object],
) -> dict[str, object]:
    pooled = {
        scenario: _pooled_summary(
            combine_ema_speed_reports(results, initial_equity_usd=5_000.0)
        )
        for scenario, results in full.items()
    }
    fold_summaries = {
        scenario: [
            _pooled_summary(
                combine_ema_speed_reports(results, initial_equity_usd=5_000.0)
            )
            for results in groups
        ]
        for scenario, groups in folds.items()
    }
    sides = {scenario: _side_summaries(results) for scenario, results in full.items()}
    technical = _technical_summary(full["nominal"])
    assessment = assess_ema_speed_development(
        pooled_nominal=pooled["nominal"],
        pooled_stress=pooled["stress"],
        stress_folds=tuple(fold_summaries["stress"]),
        side_stress=sides["stress"],
        technical_ready=bool(technical["qualification_ready"]),
    )
    return _report_payload(
        database_path,
        markets,
        pooled,
        fold_summaries,
        sides,
        technical,
        assessment,
        funding_evidence,
    )


def _report_payload(
    database_path: Path,
    markets: Mapping[str, pd.DataFrame],
    pooled: dict[str, object],
    folds: dict[str, object],
    sides: dict[str, object],
    technical: dict[str, object],
    assessment: dict[str, object],
    funding: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "ema_speed_continuation_development_v1",
        "hypothesis_id": "V57_BTC_SOL_EMA5_SPEED_CONTINUATION_15M_V1",
        "mode": "development_only_report",
        "execution_authority": "none",
        "report_only": True,
        "runtime_strategy_changed": False,
        "development_start_utc": _START.isoformat(),
        "development_end_utc": _END.isoformat(),
        "validation_and_holdout": "WITHHELD_NOT_EVALUATED",
        "folds": [_fold_record(fold) for fold in registered_development_folds()],
        "frozen_scenarios": _SCENARIOS,
        "pooled": pooled,
        "fold_summaries": folds,
        "side_summaries": sides,
        "technical_path": technical,
        "assessment": assessment,
        "inputs": _input_evidence(database_path, markets, funding),
        "generator_identity": _generator_evidence(),
        "limitations": _limitations(),
    }


def _pooled_summary(report: SharedTradeReplayReport) -> dict[str, object]:
    values = report.to_dict()
    winners = [trade.net_pnl_usd for trade in report.trades if trade.net_pnl_usd > 0]
    largest = max(winners, default=0.0)
    values["largest_winner_usd"] = largest if winners else None
    values["net_pnl_excluding_largest_winner_usd"] = report.net_pnl_usd - largest
    return values


def _fold_record(fold: DevelopmentFold) -> dict[str, object]:
    return {
        "fold_id": fold.fold_id,
        "start_utc": fold.start_utc.isoformat(),
        "end_utc": fold.end_utc.isoformat(),
    }


def _side_summaries(
    results: tuple[EmaSpeedSymbolResult, ...],
) -> dict[str, dict[str, object]]:
    return {
        side: _trade_summary(
            [
                trade.net_pnl_usd
                for result in results
                for trade in result.report.trades
                if trade.direction == side
            ]
        )
        for side in ("long", "short")
    }


def _trade_summary(values: list[float]) -> dict[str, object]:
    profits = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    largest = max(profits, default=0.0)
    return {
        "trades": len(values),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(values),
        "profit_factor": sum(profits) / sum(losses) if losses else None,
        "net_pnl_excluding_largest_winner_usd": sum(values) - largest,
    }


def _technical_summary(
    results: tuple[EmaSpeedSymbolResult, ...],
) -> dict[str, object]:
    completed = sum(result.report.completed_trades for result in results)
    l2_unresolved = sum(
        int(result.technical_path["l2_unresolved_lifecycles"]) for result in results
    )
    return {
        "completed_lifecycles": completed,
        "l2_unresolved_lifecycles": l2_unresolved,
        "mark_unresolved_lifecycles": completed,
        "mark_path_status": "unresolved_not_available",
        "qualification_ready": False,
    }


def _trade_rows(
    full: Mapping[str, tuple[EmaSpeedSymbolResult, ...]],
    folds: Mapping[str, tuple[tuple[EmaSpeedSymbolResult, ...], ...]],
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for scenario, results in full.items():
        records.extend(_result_trade_rows(results, scenario, "development"))
    for scenario, groups in folds.items():
        for fold_id, results in enumerate(groups):
            records.extend(_result_trade_rows(results, scenario, f"fold_{fold_id}"))
    return pd.DataFrame(records)


def _result_trade_rows(
    results: tuple[EmaSpeedSymbolResult, ...],
    scenario: str,
    partition: str,
) -> list[dict[str, object]]:
    return [
        {
            "scenario": scenario,
            "partition": partition,
            "symbol": result.symbol,
            **asdict(trade),
        }
        for result in results
        for trade in result.report.trades
    ]


def _input_evidence(
    database_path: Path,
    markets: Mapping[str, pd.DataFrame],
    funding: dict[str, object],
) -> dict[str, object]:
    return {
        "database_path": str(database_path),
        "market_frames": {
            symbol: {"rows": len(frame), "sha256": _frame_sha256(frame)}
            for symbol, frame in markets.items()
        },
        "funding_files": funding,
    }


def _frame_sha256(frame: pd.DataFrame) -> str:
    digest = sha256()
    digest.update("\x1f".join(map(str, frame.columns)).encode())
    digest.update(pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes())
    return digest.hexdigest()


def _funding_evidence(
    paths: Mapping[str, tuple[Path, ...]],
) -> dict[str, object]:
    return {
        symbol: [file_evidence(path) | {"path": str(path)} for path in values]
        for symbol, values in paths.items()
    }


def _generator_evidence() -> dict[str, object]:
    root = Path(__file__).parent
    names = (
        "ema_speed_continuation.py",
        "ema_speed_continuation_data.py",
        "ema_speed_continuation_replay.py",
        "ema_speed_continuation_experiment.py",
    )
    return {name: file_evidence(root / name) for name in names}


def _validate_funding_paths(paths: Mapping[str, tuple[Path, ...]]) -> None:
    if set(paths) != set(_SYMBOLS):
        raise ValueError("EMA-speed funding paths must exactly match BTC and SOL")
    for symbol, values in paths.items():
        if not values or any(not path.is_file() for path in values):
            raise FileNotFoundError(
                f"EMA-speed {symbol} funding evidence is incomplete"
            )


def _pooled_pass(summary: Mapping[str, object]) -> bool:
    profit_factor = summary.get("profit_factor")
    return (
        _number(summary, "net_pnl_usd") > 0.0
        and isinstance(profit_factor, (int, float))
        and float(profit_factor) > 1.0
        and _number(summary, "net_pnl_excluding_largest_winner_usd") > 0.0
    )


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"EMA-speed assessment {key} must be numeric")
    return float(value)


def _limitations() -> list[str]:
    return [
        "exact historical venue mark path is unavailable for technical qualification",
        "L2 barrier replay does not prove mark-based liquidation chronology",
        "development evidence cannot authorize live execution or open OOS partitions",
        "first-pass parameters are frozen; no result-driven rescue grid is allowed",
    ]
