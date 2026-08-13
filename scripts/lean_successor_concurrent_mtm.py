#!/usr/bin/env python3
"""Measure concurrent mark-to-market drawdown for the fixed lean successor."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import UTC, datetime
import json
import math
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_storage import (
    file_evidence,
    write_immutable_json,
    write_immutable_parquet,
)
from hypervector.research.concurrent_mtm_portfolio import (
    MarkedLifecycle,
    replay_concurrent_mark_to_market,
)
from hypervector.research.current_cohort_shared_portfolio import (
    CohortOutcome,
    CohortTradeSpec,
    default_sol_range_artifact_paths,
)
from hypervector.research.evidence_selected_portfolio import (
    AcceptedPortfolioOutcome,
    PrioritizedPortfolioConfig,
    replay_prioritized_outcomes,
)
from hypervector.research.hip3_midpoint_bars import build_hip3_midpoint_bars
from hypervector.research.lean_successor_mtm import (
    RawLifecycleTerms,
    active_completed_bar_marks,
    build_marked_lifecycles,
    scale_cohort_outcomes,
)

import lean_successor_portfolio as lean

_INITIAL_EQUITY_USD = 500.0
_MULTIPLIERS = (0.50, 0.75, 1.00, 1.25, 1.50, 2.00)
_SOL_BARS = Path("data/cache/SOL_1m_368d.parquet")
_HIP3_DATABASE = Path("data/research/hip3_market.duckdb")


def build_parser() -> argparse.ArgumentParser:
    """Build the report-only concurrent drawdown command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range-context", type=Path, default=lean._RANGE_CONTEXT)
    parser.add_argument("--eth-bars", type=Path, default=lean._ETH_BARS)
    parser.add_argument("--eth-funding", type=Path, default=lean._ETH_FUNDING)
    parser.add_argument(
        "--sol-artifact",
        type=Path,
        action="append",
        default=list(default_sol_range_artifact_paths()),
    )
    parser.add_argument("--sol-bars", type=Path, default=_SOL_BARS)
    parser.add_argument("--hip3-sidecar", type=Path, default=lean._HIP3_SIDECAR)
    parser.add_argument("--hip3-database", type=Path, default=_HIP3_DATABASE)
    parser.add_argument("--active-profile", type=Path, default=lean._ACTIVE_PROFILE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--path-out", type=Path, required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    """Build fixed sensitivity reports from immutable local evidence."""
    _require_new_outputs(args.out, args.path_out)
    sources = _source_paths(args)
    _require_files(sources)
    scenarios = lean._build_scenarios(args)
    nominal_routes = scenarios["nominal"]
    raw = _raw_terms(args)
    specs = lean._route_specs()
    config = PrioritizedPortfolioConfig(
        _INITIAL_EQUITY_USD,
        3,
        (lean.RANGE, lean.PULLBACK, lean.SPCX),
    )
    baseline = _accepted_rows(nominal_routes, 1.0, None, None, config)
    baseline_marked = build_marked_lifecycles(baseline, raw, specs)
    bars = _active_marks(args, baseline_marked)
    sensitivity, baseline_path = _sensitivity(nominal_routes, raw, specs, bars, config)
    write_immutable_parquet(args.path_out, baseline_path)
    artifact = _artifact(args, sources, sensitivity, baseline_path, bars)
    write_immutable_json(args.out, artifact)
    return artifact


def _sensitivity(
    routes: Mapping[lean.RouteKey, tuple[CohortOutcome, ...]],
    raw: tuple[RawLifecycleTerms, ...],
    specs: Mapping[lean.RouteKey, CohortTradeSpec],
    bars: Mapping[str, pd.DataFrame],
    config: PrioritizedPortfolioConfig,
) -> tuple[dict[str, object], pd.DataFrame]:
    output: dict[str, object] = {}
    baseline_path = pd.DataFrame()
    for multiplier in _MULTIPLIERS:
        windows: dict[str, object] = {}
        for window in lean.fixed_windows():
            accepted = _accepted_rows(
                routes,
                multiplier,
                window.start_ms,
                window.end_ms,
                config,
            )
            marked = build_marked_lifecycles(accepted, raw, specs)
            report, path = replay_concurrent_mark_to_market(
                marked,
                bars,
                _INITIAL_EQUITY_USD,
            )
            realized = _realized_summary(accepted, config)
            _reconcile_terminal(report.final_equity_usd, realized)
            windows[window.window_id] = report.to_dict() | {"realized": realized}
            if multiplier == 1.0 and window.window_id == "full_opened_descriptive":
                baseline_path = path
        output[f"{multiplier:.2f}x"] = windows
    if baseline_path.empty:
        raise RuntimeError("baseline full-opened mark path was not produced")
    return output, baseline_path


def _accepted_rows(
    routes: Mapping[lean.RouteKey, tuple[CohortOutcome, ...]],
    multiplier: float,
    start_ms: int | None,
    end_ms: int | None,
    config: PrioritizedPortfolioConfig,
) -> tuple[AcceptedPortfolioOutcome, ...]:
    selected = (lean.SOL_ROUTE, lean.SPCX_ROUTE, lean.ETH_RANGE_ROUTE)
    rows = tuple(
        row
        for route in selected
        for row in scale_cohort_outcomes(routes[route], multiplier)
        if _inside(row, start_ms, end_ms)
    )
    return replay_prioritized_outcomes(rows, config).accepted


def _inside(row: CohortOutcome, start_ms: int | None, end_ms: int | None) -> bool:
    if start_ms is None or end_ms is None:
        return True
    return start_ms <= row.outcome.entry_time_ms < end_ms


def _realized_summary(
    accepted: tuple[AcceptedPortfolioOutcome, ...],
    config: PrioritizedPortfolioConfig,
) -> dict[str, float | int | None]:
    values = [row.net_pnl_usd for row in accepted]
    wins = [value for value in values if value > 0.0]
    losses = [-value for value in values if value < 0.0]
    net = sum(values)
    return {
        "completed_trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl_usd": net,
        "final_equity_usd": config.initial_equity_usd + net,
        "profit_factor": sum(wins) / sum(losses) if losses else None,
    }


def _active_marks(
    args: argparse.Namespace,
    marked: tuple[MarkedLifecycle, ...],
) -> dict[str, pd.DataFrame]:
    by_symbol = {
        symbol: tuple(row for row in marked if row.symbol == symbol)
        for symbol in ("ETH", "SOL", "xyz:SPCX")
    }
    spcx = build_hip3_midpoint_bars(args.hip3_database, symbol="xyz:SPCX")
    return {
        "ETH": active_completed_bar_marks(
            pd.read_parquet(args.eth_bars), by_symbol["ETH"], bar_minutes=1
        ),
        "SOL": active_completed_bar_marks(
            pd.read_parquet(args.sol_bars), by_symbol["SOL"], bar_minutes=1
        ),
        "xyz:SPCX": active_completed_bar_marks(
            spcx.bars, by_symbol["xyz:SPCX"], bar_minutes=15
        ),
    }


def _raw_terms(args: argparse.Namespace) -> tuple[RawLifecycleTerms, ...]:
    rows: list[RawLifecycleTerms] = []
    rows.extend(_eth_raw(_load_json(args.range_context)))
    for path in args.sol_artifact:
        rows.extend(_sol_raw(_load_json(path)))
    rows.extend(_spcx_raw(pd.read_parquet(args.hip3_sidecar)))
    return tuple(rows)


def _eth_raw(payload: Mapping[str, object]) -> list[RawLifecycleTerms]:
    continuous = _mapping(payload.get("continuous"), "ETH continuous")
    candidates = _rows(continuous.get("candidates"), "ETH candidates")
    matches = [
        row for row in candidates if row.get("candidate_id") == "dual_mtf_not_opposed"
    ]
    if len(matches) != 1:
        raise ValueError("ETH source requires one dual_mtf_not_opposed candidate")
    return [
        _mapping_raw(lean.RANGE, "ETH", row, utc_timestamps=True)
        for row in _rows(matches[0].get("trades"), "ETH trades")
    ]


def _sol_raw(payload: Mapping[str, object]) -> list[RawLifecycleTerms]:
    continuous = _mapping(payload.get("continuous"), "SOL continuous")
    trials = _rows(continuous.get("trials"), "SOL trials")
    matches = [
        row
        for row in trials
        if math.isclose(_number(row.get("effective_exposure"), "SOL exposure"), 0.15)
    ]
    if len(matches) != 1:
        raise ValueError("SOL source requires one 0.15 exposure trial")
    replay = _mapping(matches[0].get("event_replay"), "SOL event replay")
    return [
        _mapping_raw(lean.RANGE, "SOL", row, utc_timestamps=False)
        for row in _rows(replay.get("trades"), "SOL trades")
    ]


def _spcx_raw(frame: pd.DataFrame) -> list[RawLifecycleTerms]:
    selected = frame.loc[
        frame["strategy_id"].eq(lean.SPCX)
        & frame["symbol"].eq("xyz:SPCX")
        & frame["friction"].eq("nominal")
    ]
    if selected.empty:
        raise ValueError("SPCX source contains no nominal selected rows")
    return [
        _mapping_raw(lean.SPCX, "xyz:SPCX", row.to_dict(), utc_timestamps=True)
        for _, row in selected.iterrows()
    ]


def _mapping_raw(
    strategy: str,
    symbol: str,
    row: Mapping[str, object],
    *,
    utc_timestamps: bool,
) -> RawLifecycleTerms:
    entry = _number(row.get("entry_price"), "entry_price")
    quantity = abs(_number(row.get("quantity"), "quantity"))
    notional_value = row.get("notional_usd")
    notional = (
        entry * quantity
        if notional_value is None
        else _number(notional_value, "notional_usd")
    )
    if utc_timestamps:
        entry_ms = _timestamp_ms(_text(row.get("entry_time_utc"), "entry_time_utc"))
        exit_ms = _timestamp_ms(_text(row.get("exit_time_utc"), "exit_time_utc"))
    else:
        entry_ms = _integer(row.get("entry_snapshot_time_ms"), "entry_snapshot_time_ms")
        exit_ms = _integer(row.get("exit_snapshot_time_ms"), "exit_snapshot_time_ms")
    if exit_ms == entry_ms:
        exit_ms += 1
    return RawLifecycleTerms(
        strategy,
        symbol,
        _text(row.get("direction"), "direction").lower(),
        entry_ms,
        exit_ms,
        entry,
        _number(row.get("exit_price"), "exit_price"),
        quantity,
        notional,
        _number(row.get("fees_usd"), "fees_usd"),
        _number(row.get("funding_cashflow_usd"), "funding_cashflow_usd"),
        _number(row.get("net_pnl_usd"), "net_pnl_usd"),
    )


def _artifact(
    args: argparse.Namespace,
    sources: tuple[Path, ...],
    sensitivity: Mapping[str, object],
    baseline_path: pd.DataFrame,
    bars: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    return {
        "schema_version": "lean_successor_concurrent_mtm_v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "candidate": "sol_range_spcx_eth_dual_mtf",
        "sizing_multipliers": list(_MULTIPLIERS),
        "sensitivity": dict(sensitivity),
        "mark_coverage_rows": {symbol: len(frame) for symbol, frame in bars.items()},
        "baseline_path": {
            "path": str(args.path_out.resolve()),
            "rows": len(baseline_path),
            **file_evidence(args.path_out),
        },
        "source_evidence": _evidence(sources),
        "limitations": [
            "all source windows are opened and selection-contaminated",
            "funding is linearly accrued between entry and exit rather than replayed at exact venue boundaries",
            "SPCX uses verified L2 midpoint bars rather than executable trade OHLC",
            "adverse intrabar marks assume the bar extreme occurred while the position remained open",
            "the fixed multiplier surface is sensitivity analysis rather than parameter optimization",
        ],
        "decision": "diagnostic_only_no_live_or_profile_mutation",
    }


def _source_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    return (
        args.range_context,
        args.eth_bars,
        args.eth_funding,
        *tuple(args.sol_artifact),
        args.sol_bars,
        args.hip3_sidecar,
        args.hip3_database,
        args.active_profile,
    )


def _reconcile_terminal(marked: float, realized: Mapping[str, object]) -> None:
    expected = _number(realized.get("final_equity_usd"), "realized final equity")
    if not math.isclose(marked, expected, abs_tol=0.01):
        raise RuntimeError(
            "marked terminal equity does not reconcile to realized ledger"
        )


def _require_new_outputs(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"immutable concurrent MTM outputs exist: {existing}")


def _require_files(paths: tuple[Path, ...]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"concurrent MTM sources are missing: {missing}")


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"concurrent MTM JSON source must be an object: {path}")
    return value


def _evidence(paths: tuple[Path, ...]) -> dict[str, object]:
    return {
        str(path): {"path": str(path.resolve()), **file_evidence(path)}
        for path in paths
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object with text keys")
    return value


def _rows(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return [_mapping(row, f"{label} row") for row in value]


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("concurrent MTM source timestamp must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def main() -> int:
    """Run the immutable diagnostic and print a bounded result."""
    args = build_parser().parse_args()
    artifact = run(args)
    baseline = artifact["sensitivity"]["1.00x"]["full_opened_descriptive"]
    print(
        json.dumps(
            {"ok": True, "output": str(args.out.resolve()), "baseline": baseline},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
