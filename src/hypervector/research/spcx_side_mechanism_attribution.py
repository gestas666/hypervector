"""Exact, report-only SPCX side and entry-timing attribution."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import pandas as pd

from hypervector.data.oxa_storage import file_evidence

Record = Mapping[str, object]

_PHASES = ("development", "validation")
_FRICTIONS = ("nominal", "stress")
_MODES = (
    "provider_exact",
    "alignment_onset",
    "next_bar_confirmation",
    "first_fast_ema_pullback",
)
_SIDES = ("long", "short")
_REQUIRED_COLUMNS = frozenset(
    {
        "strategy_id",
        "symbol",
        "phase",
        "friction",
        "timing_mode",
        "direction",
        "net_pnl_usd",
    }
)
_CONTRACT: dict[str, object] = {
    "report_only": True,
    "execution_authority": "none",
    "model_authority": "none",
    "automatic_promotion": False,
    "automatic_retuning": False,
    "runtime_strategy_changed": False,
}


@dataclass(frozen=True)
class _AttributionSpec:
    label: str
    strategy_id: str
    symbol: str
    schema_version: str
    mode: str


_SPCX_SPEC = _AttributionSpec(
    "SPCX",
    "hip3_swing_ha_sp500_spcx_bidirectional_v2",
    "xyz:SPCX",
    "spcx_side_mechanism_attribution_v1",
    "spcx_side_mechanism_attribution",
)
_GOLD_SPEC = _AttributionSpec(
    "GOLD",
    "hip3_swing_ha_sndk_gold_brent_bidirectional_v1",
    "xyz:GOLD",
    "gold_side_mechanism_attribution_v1",
    "gold_side_mechanism_attribution",
)


def build_spcx_side_mechanism_attribution(
    source_report: Path,
    trade_sidecar: Path,
) -> dict[str, object]:
    """Attribute frozen SPCX timing outcomes without changing live authority."""
    return _build_attribution(source_report, trade_sidecar, _SPCX_SPEC)


def build_gold_side_mechanism_attribution(
    source_report: Path,
    trade_sidecar: Path,
) -> dict[str, object]:
    """Attribute frozen GOLD timing outcomes without changing live authority."""
    return _build_attribution(source_report, trade_sidecar, _GOLD_SPEC)


def _build_attribution(
    source_report: Path,
    trade_sidecar: Path,
    spec: _AttributionSpec,
) -> dict[str, object]:
    report = _load_report(source_report, spec)
    case = _validated_case(report, spec)
    trades = pd.read_parquet(trade_sidecar)
    _validate_sidecar(report, trade_sidecar, trades, spec)
    exact = _exact_trade_rows(trades, spec)
    cells = _cells(exact)
    arms = _arms(cells)
    stable = [key for key, value in arms.items() if value["stable"] is True]
    return {
        "schema_version": spec.schema_version,
        "mode": spec.mode,
        "contract": dict(_CONTRACT),
        "route": {"strategy_id": spec.strategy_id, "symbol": spec.symbol},
        "source": {
            "report": {
                "path": str(source_report.resolve()),
                **file_evidence(source_report),
            },
            "trade_sidecar": {
                "path": str(trade_sidecar.resolve()),
                "rows": len(trades),
                **file_evidence(trade_sidecar),
            },
            "timing_contract": dict(
                _mapping(case.get("timing_contract"), "timing contract")
            ),
            "windows": dict(_mapping(case.get("windows"), "windows")),
            "holdout": dict(_mapping(case.get("holdout"), "holdout")),
        },
        "cells": cells,
        "arms": arms,
        "assessment": {
            "tested_side_timing_arms": len(arms),
            "stable_side_timing_arms": stable,
            "unstable_side_timing_arms": [key for key in arms if key not in stable],
            "holdout_opened": False,
            "shared_router_replayed": False,
        },
        "decision": (
            "tested_side_timing_set_falsified_requires_new_mechanism_identity"
            if not stable
            else "stable_side_timing_arm_requires_preregistered_holdout_test"
        ),
        "limitations": _limitations(spec),
    }


def _load_report(path: Path, spec: _AttributionSpec) -> Record:
    if not path.is_file():
        raise FileNotFoundError(f"{spec.label} timing report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = _mapping(payload, f"{spec.label} timing report")
    _validate_contract(report, "source report", include_model=True)
    if report.get("schema_version") != "hip3_entry_timing_challenger_v1":
        raise ValueError(f"{spec.label} source report schema is unsupported")
    return report


def _validated_case(report: Record, spec: _AttributionSpec) -> Record:
    cases = _mapping(report.get("cases"), "source cases")
    case = _mapping(cases.get(spec.strategy_id), f"{spec.label} timing case")
    if case.get("strategy_id") != spec.strategy_id:
        raise ValueError(f"{spec.label} timing case strategy identity mismatch")
    _validate_contract(case, f"{spec.label} timing case", include_model=False)
    holdout = _mapping(case.get("holdout"), f"{spec.label} holdout")
    if holdout.get("status") != "sealed_not_evaluated":
        raise ValueError(f"{spec.label} timing holdout must remain sealed")
    if holdout.get("metrics_accessed") is not False:
        raise ValueError(f"{spec.label} timing holdout metrics must remain unaccessed")
    _validate_results(case.get("results"), spec)
    return case


def _validate_contract(value: Record, label: str, *, include_model: bool) -> None:
    required = {
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
    }
    if include_model:
        required.update({"report_only": True, "model_authority": "none"})
    mismatches = [
        key for key, expected in required.items() if value.get(key) != expected
    ]
    if mismatches:
        raise ValueError(f"{label} violates report-only contract: {mismatches}")


def _validate_results(value: object, spec: _AttributionSpec) -> None:
    results = _mapping(value, f"{spec.label} timing results")
    if set(results) != set(_PHASES):
        raise ValueError(
            f"{spec.label} timing results require development and validation"
        )
    for phase in _PHASES:
        frictions = _mapping(results.get(phase), f"{phase} results")
        if set(frictions) != set(_FRICTIONS):
            raise ValueError(f"{spec.label} {phase} results require nominal and stress")
        for friction in _FRICTIONS:
            modes = _mapping(frictions.get(friction), f"{phase} {friction} modes")
            if set(modes) != set(_MODES):
                raise ValueError(
                    f"{spec.label} timing results lack exact mode coverage"
                )
            for mode in _MODES:
                symbols = _mapping(modes.get(mode), f"{mode} symbols")
                if spec.symbol not in symbols:
                    raise ValueError(f"{spec.label} timing results omit {spec.symbol}")


def _validate_sidecar(
    report: Record,
    path: Path,
    trades: pd.DataFrame,
    spec: _AttributionSpec,
) -> None:
    expected = _mapping(report.get("trade_sidecar"), "trade sidecar evidence")
    actual = file_evidence(path)
    expected_path = expected.get("path")
    evidence_matches = all(
        expected.get(key) == actual[key] for key in ("bytes", "sha256")
    )
    if expected_path != str(path.resolve()) or not evidence_matches:
        raise ValueError(f"{spec.label} trade sidecar evidence mismatch")
    if expected.get("rows") != len(trades):
        raise ValueError(f"{spec.label} trade sidecar row count mismatch")
    missing = _REQUIRED_COLUMNS - set(trades.columns)
    if missing:
        raise ValueError(
            f"{spec.label} trade sidecar lacks required columns: {sorted(missing)}"
        )


def _exact_trade_rows(
    trades: pd.DataFrame,
    spec: _AttributionSpec,
) -> pd.DataFrame:
    exact = trades.loc[
        (trades["strategy_id"] == spec.strategy_id) & (trades["symbol"] == spec.symbol)
    ].copy()
    _require_subset(exact, "phase", _PHASES, spec)
    _require_subset(exact, "friction", _FRICTIONS, spec)
    _require_subset(exact, "timing_mode", _MODES, spec)
    _require_subset(exact, "direction", _SIDES, spec)
    values = pd.to_numeric(exact["net_pnl_usd"], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{spec.label} trade outcomes must be finite numeric values")
    exact["net_pnl_usd"] = values.astype(float)
    return exact


def _require_subset(
    frame: pd.DataFrame,
    column: str,
    allowed: tuple[str, ...],
    spec: _AttributionSpec,
) -> None:
    observed = set(frame[column].dropna().astype(str))
    if not observed.issubset(set(allowed)):
        raise ValueError(
            f"{spec.label} {column} contains unsupported values: {sorted(observed)}"
        )


def _cells(trades: pd.DataFrame) -> dict[str, object]:
    return {
        _cell_key(mode, side, phase, friction): _cell(
            trades.loc[
                (trades["timing_mode"] == mode)
                & (trades["direction"] == side)
                & (trades["phase"] == phase)
                & (trades["friction"] == friction),
                "net_pnl_usd",
            ]
        )
        for mode in _MODES
        for side in _SIDES
        for phase in _PHASES
        for friction in _FRICTIONS
    }


def _cell(values: pd.Series) -> dict[str, object]:
    outcomes = [float(value) for value in values.tolist()]
    profits = [value for value in outcomes if value > 0.0]
    losses = [-value for value in outcomes if value < 0.0]
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    largest = max(profits, default=0.0)
    return {
        "trades": len(outcomes),
        "wins": len(profits),
        "losses": len(losses),
        "breakeven": sum(value == 0.0 for value in outcomes),
        "net_pnl_usd": sum(outcomes),
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "median_trade_pnl_usd": median(outcomes) if outcomes else None,
        "largest_winner_usd": largest,
        "net_excluding_largest_winner_usd": sum(outcomes) - largest,
    }


def _arms(cells: Record) -> dict[str, object]:
    arms: dict[str, object] = {}
    for mode in _MODES:
        for side in _SIDES:
            keys = [
                _cell_key(mode, side, phase, friction)
                for phase in _PHASES
                for friction in _FRICTIONS
            ]
            failed = [
                key
                for key in keys
                if not _cell_is_repeatable(_mapping(cells[key], key))
            ]
            arms[f"{mode}|{side}"] = {
                "stable": not failed,
                "failed_cells": failed,
                "criteria": (
                    "nonempty_net_positive_pf_above_one_and_positive_without_largest_winner"
                ),
            }
    return arms


def _cell_is_repeatable(cell: Record) -> bool:
    profit_factor = cell.get("profit_factor")
    return (
        _integer(cell.get("trades"), "cell trades") > 0
        and _number(cell.get("net_pnl_usd"), "cell net") > 0.0
        and profit_factor is not None
        and _number(profit_factor, "cell profit factor") > 1.0
        and _number(cell.get("net_excluding_largest_winner_usd"), "cell repeatability")
        > 0.0
    )


def _cell_key(mode: str, side: str, phase: str, friction: str) -> str:
    return f"{mode}|{side}|{phase}|{friction}"


def _limitations(spec: _AttributionSpec) -> list[str]:
    return [
        "Development and validation were already opened and cannot be reused as a sealed promotion test.",
        "The sealed holdout remains unread and is not consumed by this attribution.",
        "Results are independent-asset 15-minute approximations, not a shared-router replay.",
        "Visible-book and latency friction are modeled rather than realized venue fills.",
        f"Rejecting the tested timing set does not prove that no {spec.label} mechanism can work.",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not result == result or result in {float("inf"), float("-inf")}:
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value
