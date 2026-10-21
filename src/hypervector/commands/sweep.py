"""Sweep and trial-board command handlers; imported only on dispatch.

Engines load lazily inside :func:`run_sweep`, so the read-only board does not
pay for VectorBT.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from functools import lru_cache
import json
import math
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hypervector.commands.common import CommandRefused, exit_config_from_args
from hypervector.commands.exports import (
    TRIAL_METRICS,
    select_export_trial,
    trial_matches,
)
from hypervector.infra import ensure_data_layout, paths_for
from hypervector.runs.db import RunsDB, TrialRow

if TYPE_CHECKING:
    import pandas as pd

    from hypervector.strategies.registry import StrategySpec
    from hypervector.sweep.costs import CostModel
    from hypervector.sweep.exits import ExitConfig
    from hypervector.sweep.search import TrialResult
    from hypervector.sweep.sizing import RiskConfig

TABLE_COLUMNS: tuple[str, ...] = (
    "source",
    "run_id",
    "track",
    "strategy",
    "symbol",
    "timeframe",
    "net_pnl",
    "total_return_pct",
    "sharpe",
    "trade_count",
    "win_pct",
    "max_drawdown",
    "status",
)


# --- sweep -----------------------------------------------------------------------


def cmd_sweep(args: argparse.Namespace) -> int:
    """Grid-search one strategy track, store every measured trial, export the best."""
    print(json.dumps(run_sweep(args, str(args.track)), indent=2, default=str))
    return 0


def run_sweep(args: argparse.Namespace, role: str) -> dict[str, Any]:
    """Run one track sweep and return its run id, best trial and bundle.

    The strategy and settings are validated before any data load (refusal, exit
    2). Weak or negative results are returned as measured; only every trial
    failing technically raises (exit 1). The best trial is chosen from the
    stored rows by :func:`select_export_trial`, the same rule ``export create``
    uses.
    """
    from hypervector.strategies import register_all_strategies
    from hypervector.sweep.search import run_grid_search

    from hypervector.commands.common import cache_age_options

    register_all_strategies()
    strategy = _select_sweep_strategy(args, role)
    init_cash, cost, exit_cfg, risk_cfg = _sweep_settings(args)
    cache_age_options(args)
    df, prov = _sweep_bars(args)
    root = Path(args.data_root)
    _emit_sweep_diagnostics(
        strategy, len(df), init_cash, cost, exit_cfg, risk_cfg, prov, args.symbol
    )
    apply_costs = not getattr(args, "no_costs", False)
    results = run_grid_search(
        df,
        strategy,
        init_cash=init_cash,
        cost=cost,
        exit_cfg=exit_cfg,
        risk_cfg=risk_cfg,
        conviction=risk_cfg.default_conviction,
        apply_costs=apply_costs,
        symbol=args.symbol,
    )
    run_id = str(uuid.uuid4())[:8]
    research_meta = _sweep_metadata(
        args, init_cash, exit_cfg, risk_cfg, cost, apply_costs, prov
    )
    board = _persist_sweep_trials(root, run_id, role, results, research_meta)
    _emit_board(board)
    ok_count = sum(result.status == "ok" for result in results)
    if ok_count == 0:
        raise RuntimeError(
            f"every sweep trial failed ({len(results)} trials, run {run_id}); "
            "inspect the technical errors above"
        )
    best = _best_stored_trial(root, run_id, role)
    warnings: list[str] = []
    if not apply_costs:
        warnings.append(
            "--no-costs: every trial was measured without fees or slippage; "
            "the result is diagnostic only"
        )
    export_dir = None
    if not getattr(args, "no_export", False) and best is not None:
        if not apply_costs:
            warnings.append(
                "the exported bundle is zero-cost (meta.apply_costs false); "
                "'export validate --require-costed' rejects it"
            )
        export_dir = _export_sweep_best(root, run_id, role, best)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    runs_db = paths_for(root).runs_db
    return {
        "ok": True,
        "run_id": run_id,
        "track": role,
        "strategy": strategy.name,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "lookback_days": args.lookback,
        "fee_model": args.fee_model,
        "costs_applied": apply_costs,
        "trials": len(results),
        "ok_trials": ok_count,
        "failed_trials": len(results) - ok_count,
        "best": _trial_summary(best),
        "sizing": _sizing_summary(risk_cfg, results, best),
        "warnings": warnings,
        "export_dir": str(export_dir) if export_dir else None,
        "candidate_id": export_dir.name if export_dir else None,
        "data_provenance": prov,
        "artifacts": {
            "board": str(runs_db.resolve()),
            "export": str(export_dir) if export_dir else None,
        },
    }


def _select_sweep_strategy(args: argparse.Namespace, role: str) -> StrategySpec:
    """Resolve ``--strategy``; a role that does not match the track is refused."""
    from hypervector.commands.common import registered_strategy

    name = getattr(args, "strategy", None)
    strategy = registered_strategy(name)
    if strategy.role != role:
        raise CommandRefused(
            f"strategy {name!r} has role={strategy.role!r}, expected {role!r}"
        )
    return strategy


def _sweep_settings(
    args: argparse.Namespace,
) -> tuple[float, CostModel, ExitConfig, RiskConfig]:
    """Explicit sweep settings; no performance gates are introduced here.

    ``--leverage`` is checked against the symbol's venue cap before any data
    load (a refusal exits 2).
    """
    from hypervector.sweep.costs import resolve_cost_model
    from hypervector.sweep.sizing import RiskConfig, validate_leverage

    try:
        leverage = validate_leverage(
            float(getattr(args, "leverage", 1.0)), symbol=args.symbol
        )
    except ValueError as exc:
        raise CommandRefused(f"--leverage refused: {exc}") from exc
    init_cash = float(args.initial_cash)
    cost = resolve_cost_model(args.fee_model)
    exit_cfg = exit_config_from_args(args)
    try:
        risk_cfg = RiskConfig(
            risk_pct_min=float(getattr(args, "risk_min", 0.01)),
            risk_pct_max=float(getattr(args, "risk_max", 0.05)),
            default_conviction=float(getattr(args, "conviction", 0.5)),
            max_size_frac=leverage,
        )
    except ValueError as exc:
        raise CommandRefused(str(exc)) from exc
    return init_cash, cost, exit_cfg, risk_cfg


def _sweep_bars(args: argparse.Namespace) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load the sweep's bars (cache-first; ``no_network`` keeps it offline)."""
    from hypervector.commands.common import cache_age_options
    from hypervector.data.pipeline import load_research_history

    options = cache_age_options(args)
    ensure_data_layout(Path(args.data_root))
    return load_research_history(
        args.data_root,
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.lookback,
        strict_hl_only=getattr(args, "strict_hl_only", False),
        force_refresh=getattr(args, "force", False),
        allow_network=not getattr(args, "no_network", False),
        **options,
    )


def _emit_sweep_diagnostics(
    strategy: StrategySpec,
    bars: int,
    init_cash: float,
    cost: CostModel,
    exit_cfg: ExitConfig,
    risk_cfg: RiskConfig,
    prov: dict[str, object],
    symbol: str | None = None,
) -> None:
    """Report the actual search settings and source provenance on stderr."""
    from hypervector.sweep.sizing import maintenance_margin_rate, venue_leverage_cap

    cap = venue_leverage_cap(symbol)
    print(
        json.dumps(
            {
                "strategy": strategy.name,
                "role": strategy.role,
                "bars": bars,
                "init_cash": init_cash,
                "tp_sl_mode": exit_cfg.mode,
                "risk_pct_range": [risk_cfg.risk_pct_min, risk_cfg.risk_pct_max],
                "conviction": risk_cfg.default_conviction,
                "leverage": risk_cfg.max_size_frac,
                "venue_leverage_cap": cap,
                "maintenance_margin_rate": maintenance_margin_rate(cap),
                "costs": cost.to_dict(),
                "data_provenance": prov,
            },
            indent=2,
            default=str,
        ),
        file=sys.stderr,
    )


def _sweep_metadata(
    args: argparse.Namespace,
    init_cash: float,
    exit_cfg: ExitConfig,
    risk_cfg: RiskConfig,
    cost: CostModel,
    apply_costs: bool,
    prov: dict[str, object],
) -> dict[str, object]:
    """Bind measured trial rows to their exact research inputs and settings."""
    return {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "lookback_days": args.lookback,
        "init_cash": init_cash,
        "tp_sl_mode": exit_cfg.mode,
        "exits": exit_cfg.to_dict(),
        "risk": risk_cfg.to_dict(),
        "costs": cost.to_dict(),
        "apply_costs": apply_costs,
        "data_provenance": prov,
        "fee_model": args.fee_model,
        "conviction": risk_cfg.default_conviction,
    }


def _persist_sweep_trials(
    root: Path,
    run_id: str,
    role: str,
    results: list[TrialResult],
    research_meta: dict[str, object],
) -> list[dict[str, object]]:
    """Store measured trials in one transaction; failures stay on the printed board."""
    rows: list[dict[str, object]] = []
    stored: list[TrialRow] = []
    for result in results:
        rows.append(
            {
                "strategy": result.strategy,
                "params": result.params,
                "status": result.status,
                **({"error": result.error} if result.error else {}),
                **result.metrics,
            }
        )
        if result.status == "ok":
            stored.append(
                TrialRow(
                    run_id=run_id,
                    track=role,
                    strategy=result.strategy,
                    params=result.params,
                    net_pnl=result.metrics["net_pnl"],
                    total_return_pct=result.metrics["total_return_pct"],
                    sharpe=result.metrics["sharpe"],
                    trade_count=result.metrics["trade_count"],
                    wins=result.metrics["wins"],
                    losses=result.metrics["losses"],
                    win_pct=result.metrics["win_pct"],
                    max_drawdown=result.metrics["max_drawdown"],
                    status="ok",
                    research_meta=research_meta,
                )
            )
    with closing(RunsDB(paths_for(root).runs_db)) as db:
        db.insert_trials(stored)
    return rows


def _emit_board(rows: list[dict[str, object]]) -> None:
    """Human-readable ranked board on stderr (stdout carries the JSON result)."""
    from hypervector.report import rank_trials

    board = rank_trials(rows)
    print(
        board.to_string(index=False) if len(board) else "(no trials)", file=sys.stderr
    )


def _best_stored_trial(root: Path, run_id: str, role: str) -> dict[str, Any] | None:
    with closing(RunsDB(paths_for(root).runs_db)) as db:
        rows = db.list_trials(run_id=run_id)
    return select_export_trial(rows, run_id=run_id, track=role)


def _export_sweep_best(
    root: Path, run_id: str, role: str, best: dict[str, Any] | None = None
) -> Path | None:
    """Publish this run's selected stored trial as a strict bundle; return its path.

    Selection is :func:`select_export_trial` over the run's stored rows (pass an
    already selected trial to skip the second query).
    """
    from hypervector.commands.export import publish_trial_export

    chosen = best if best is not None else _best_stored_trial(root, run_id, role)
    if chosen is None:
        return None
    return publish_trial_export(
        root, chosen, candidate_id=f"{role}_{chosen['strategy']}_{run_id}"
    )


def _sizing_summary(
    risk_cfg: RiskConfig,
    results: list[TrialResult],
    best: dict[str, Any] | None,
) -> dict[str, Any]:
    """Requested leverage and the best trial's measured sizing (never a gate)."""
    summary: dict[str, Any] = {"leverage": risk_cfg.max_size_frac}
    if best is None:
        return summary
    measured = next(
        (
            result.metrics
            for result in results
            if result.status == "ok"
            and result.strategy == best.get("strategy")
            and result.params == best.get("params")
        ),
        {},
    )
    for key in (
        "effective_risk_pct",
        "size_cap_bound_fraction",
        "venue_leverage_cap",
        "maintenance_margin_rate",
        "liquidations",
        "equity_depleted",
    ):
        summary[key] = measured.get(key)
    return summary


def _trial_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "trial_id": row.get("id"),
        "strategy": row.get("strategy"),
        "params": row.get("params"),
        **{key: row.get(key) for key in TRIAL_METRICS},
    }


# --- board -----------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    """Rank stored sweep trials and tune boards (read-only; never creates directories)."""
    limit = int(args.limit)
    if limit < 1:
        raise CommandRefused("--limit must be at least 1")
    root = Path(args.data_root)
    paths = paths_for(root)
    sources = ("sweep", "tune") if args.source == "all" else (args.source,)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    if "sweep" in sources:
        rows += _sweep_board_rows(paths.runs_db)
    if "tune" in sources:
        tune_rows, skipped = _tune_board_rows(paths.logs_research)
        rows += tune_rows
    filters = {
        "run_id": args.run_id,
        "track": args.track,
        "strategy": args.strategy,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
    }
    rows = [row for row in rows if trial_matches(row, **filters)]
    rows.sort(key=_board_rank)
    shown = rows[:limit]
    if args.format == "table":
        print(_render_table(shown) if shown else "(no trials)")
        return 0
    report = {
        "ok": True,
        "sources": list(sources),
        "filters": {key: value for key, value in filters.items() if value is not None},
        "total": len(rows),
        "count": len(shown),
        "limit": limit,
        "boards": {
            "sweep": str(paths.runs_db.resolve()),
            "tune": str(paths.logs_research.resolve()),
        },
        "rows": shown,
        "skipped": skipped,
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


def _sweep_board_rows(database: Path) -> list[dict[str, Any]]:
    if not database.is_file():
        return []
    with closing(RunsDB(database)) as db:
        stored = db.list_trials()
    rows = []
    for row in stored:
        meta = row.get("research_meta") or {}
        rows.append(
            {
                "source": "sweep",
                "run_id": row.get("run_id"),
                "trial_id": row.get("id"),
                "track": row.get("track"),
                "strategy": row.get("strategy"),
                "symbol": meta.get("symbol"),
                "timeframe": meta.get("timeframe"),
                "lookback_days": meta.get("lookback_days"),
                "initial_cash": meta.get("init_cash"),
                "fee_model": meta.get("fee_model"),
                **{key: row.get(key) for key in TRIAL_METRICS},
                "status": row.get("status"),
                "params": row.get("params"),
                "created_at": row.get("created_at"),
            }
        )
    return rows


def _tune_board_rows(
    directory: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """One row per autotune trial from ``logs/research/autotune_*.json``."""
    if not directory.is_dir():
        return [], []
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(directory.glob("autotune_*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            trials = document["all_trials"]
            if not isinstance(trials, list):
                raise TypeError("all_trials is not a list")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped.append(
                {"path": str(path), "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        strategy = document.get("strategy")
        created = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(
            timespec="seconds"
        )
        for index, trial in enumerate(trials):
            if not isinstance(trial, dict):
                continue
            metrics = trial.get("metrics") or {}
            rows.append(
                {
                    "source": "tune",
                    "run_id": path.stem,
                    "trial_id": index,
                    "track": _strategy_role(str(strategy)) if strategy else None,
                    "strategy": strategy,
                    "symbol": document.get("symbol"),
                    "timeframe": document.get("timeframe"),
                    "lookback_days": document.get("lookback_days"),
                    "fee_model": document.get("fee_model"),
                    "sampler": document.get("sampler_used"),
                    **{key: metrics.get(key) for key in TRIAL_METRICS},
                    "status": trial.get("status"),
                    "params": trial.get("params"),
                    "exit_cfg": trial.get("exit_cfg"),
                    "created_at": created,
                }
            )
    return rows, skipped


@lru_cache(maxsize=None)
def _strategy_role(name: str) -> str | None:
    """Track of a registered strategy; unknown names have none."""
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy

    register_all_strategies()
    try:
        return str(get_strategy(name).role)
    except KeyError:
        return None


def _board_rank(row: dict[str, Any]) -> tuple[int, float, float]:
    return (
        0 if row.get("status", "ok") == "ok" else 1,
        -_finite(row.get("net_pnl")),
        -_finite(row.get("total_return_pct")),
    )


def _finite(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -math.inf
    return -math.inf if math.isnan(number) else number


def _render_table(rows: list[dict[str, Any]]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, float):
            return f"{value:.4g}" if abs(value) < 1e-3 and value else f"{value:.2f}"
        return str(value)

    cells = [[cell(row.get(column)) for column in TABLE_COLUMNS] for row in rows]
    widths = [
        max(len(column), *(len(line[index]) for line in cells))
        for index, column in enumerate(TABLE_COLUMNS)
    ]
    lines = ["  ".join(c.ljust(w) for c, w in zip(TABLE_COLUMNS, widths))]
    lines += ["  ".join(v.ljust(w) for v, w in zip(line, widths)) for line in cells]
    return "\n".join(line.rstrip() for line in lines)
