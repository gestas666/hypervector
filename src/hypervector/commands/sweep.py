"""Sweep command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import sys
import uuid
from pathlib import Path
from hypervector.export.phase2 import export_candidate
from hypervector.report import rank_trials
from hypervector.runs.db import RunsDB, TrialRow
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import StrategySpec, get_strategy, list_strategies
from hypervector.sweep.costs import CostModel, resolve_cost_model
from hypervector.sweep.exits import EXIT_MODES, ExitConfig
from hypervector.sweep.search import TrialResult, run_grid_search
from hypervector.sweep.sizing import RiskConfig
from hypervector.commands.common import _ensure_root, _load_bars


def _run_sweep(args: argparse.Namespace, role: str) -> int:
    register_all_strategies()
    root = _ensure_root(args).root
    df, prov = _load_bars(args)
    strategy = _select_sweep_strategy(args, role)
    if strategy is None:
        return 1
    try:
        init_cash, cost, exit_cfg, risk_cfg = _sweep_settings(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _emit_sweep_diagnostics(
        strategy, len(df), init_cash, cost, exit_cfg, risk_cfg, prov
    )
    results = run_grid_search(
        df,
        strategy,
        init_cash=init_cash,
        cost=cost,
        exit_cfg=exit_cfg,
        risk_cfg=risk_cfg,
        conviction=risk_cfg.default_conviction,
        apply_costs=not getattr(args, "no_costs", False),
    )
    run_id = str(uuid.uuid4())[:8]
    apply_costs = not getattr(args, "no_costs", False)
    research_meta = _sweep_metadata(
        args, init_cash, exit_cfg, risk_cfg, cost, apply_costs, prov
    )
    rows = _persist_sweep_trials(root, run_id, role, results, research_meta)
    print(rank_trials(rows).to_string(index=False))
    _export_sweep_best(args.export, root, run_id, role, results, research_meta)
    return 0


def cmd_sweep_up(args: argparse.Namespace) -> int:
    """Search the declared uptrend strategy track."""
    return _run_sweep(args, "uptrend")


def cmd_sweep_down(args: argparse.Namespace) -> int:
    """Search the declared downtrend strategy track."""
    return _run_sweep(args, "downtrend")


def cmd_report(args: argparse.Namespace) -> int:
    """Read the persisted trial board for an optional track."""
    root = _ensure_root(args).root
    with closing(RunsDB(root / "runs" / "hypervector.db")) as db:
        rows = db.list_trials(track=args.track)
    board = rank_trials(rows)
    print(board.to_string(index=False) if len(board) else "(no trials)")
    return 0


def _select_sweep_strategy(args: argparse.Namespace, role: str) -> StrategySpec | None:
    """Resolve the requested family and preserve its declared research track."""
    name = getattr(args, "strategy", None)
    if name:
        strategy = get_strategy(name)
        if strategy.role != role:
            print(
                f"strategy {name!r} has role={strategy.role!r}, expected {role!r}",
                file=sys.stderr,
            )
            return None
    else:
        # Prefer frankenstein trend_ride, then crown_stack
        preferred = (
            f"trend_ride_{'long' if role == 'uptrend' else 'short'}",
            f"crown_stack_{'long' if role == 'uptrend' else 'short'}",
        )
        specs = list_strategies(role=role)
        by_name = {s.name: s for s in specs}
        strategy = None
        for name in preferred:
            if name in by_name:
                strategy = by_name[name]
                break
        if strategy is None and specs:
            strategy = specs[0]
    if strategy is None:
        print(f"no strategies for role={role}", file=sys.stderr)
        return None
    return strategy


def _sweep_settings(
    args: argparse.Namespace,
) -> tuple[float, CostModel, ExitConfig, RiskConfig]:
    """Validate explicit sweep settings without introducing performance gates."""
    init_cash = float(getattr(args, "cash", 10_000.0))
    cost = resolve_cost_model(getattr(args, "fee_model", "hl_taker_default"))
    mode = getattr(args, "tp_sl_mode", "atr")
    if mode not in EXIT_MODES:
        raise ValueError(f"tp_sl_mode must be one of {EXIT_MODES}")
    exit_cfg = ExitConfig(
        mode=mode,
        sl_pct=float(getattr(args, "sl_pct", 0.01)),
        rr=float(getattr(args, "rr", 2.0)),
        atr_length=int(getattr(args, "atr_length", 14)),
        sl_atr_mult=float(getattr(args, "sl_atr_mult", 1.5)),
        trail_atr_mult=float(getattr(args, "trail_atr_mult", 2.0)),
    )
    risk_cfg = RiskConfig(
        risk_pct_min=float(getattr(args, "risk_min", 0.01)),
        risk_pct_max=float(getattr(args, "risk_max", 0.05)),
        default_conviction=float(getattr(args, "conviction", 0.5)),
    )
    return init_cash, cost, exit_cfg, risk_cfg


def _emit_sweep_diagnostics(
    strategy: StrategySpec,
    bars: int,
    init_cash: float,
    cost: CostModel,
    exit_cfg: ExitConfig,
    risk_cfg: RiskConfig,
    prov: dict[str, object],
) -> None:
    """Report the actual search settings and source provenance."""
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
        "fee_model": getattr(args, "fee_model", "hl_taker_default"),
        "conviction": risk_cfg.default_conviction,
    }


def _persist_sweep_trials(
    root: Path,
    run_id: str,
    role: str,
    results: list[TrialResult],
    research_meta: dict[str, object],
) -> list[dict[str, object]]:
    """Store valid measured trials and retain technical failures on the board."""
    rows: list[dict[str, object]] = []
    with closing(RunsDB(root / "runs" / "hypervector.db")) as db:
        for r in results:
            row = {
                "strategy": r.strategy,
                "params": r.params,
                "status": r.status,
                **r.metrics,
            }
            rows.append(row)
            if r.status == "ok":
                db.insert_trial(
                    TrialRow(
                        run_id=run_id,
                        track=role,
                        strategy=r.strategy,
                        params=r.params,
                        net_pnl=r.metrics["net_pnl"],
                        total_return_pct=r.metrics["total_return_pct"],
                        sharpe=r.metrics["sharpe"],
                        trade_count=r.metrics["trade_count"],
                        wins=r.metrics["wins"],
                        losses=r.metrics["losses"],
                        win_pct=r.metrics["win_pct"],
                        max_drawdown=r.metrics["max_drawdown"],
                        status="ok",
                        research_meta=research_meta,
                    )
                )
    return rows


def _export_sweep_best(
    requested: bool,
    root: Path,
    run_id: str,
    role: str,
    results: list[TrialResult],
    research_meta: dict[str, object],
) -> None:
    """Publish the selected valid result with its source and cost metadata."""
    if requested and results and results[0].status == "ok":
        best = results[0]
        export_candidate(
            root / "exports",
            run_id=run_id,
            meta={
                "track": role,
                **research_meta,
            },
            params={"strategy": best.strategy, "role": role, **best.params},
            metrics=best.metrics,
            candidate_id=f"{role}_{best.strategy}_{run_id}",
            strict=True,
        )
