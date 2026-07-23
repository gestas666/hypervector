"""CLI: history (live HL+backfill), regime, sweep-up, sweep-down, report, export."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from hypervector.config import DEFAULT_LOOKBACK, FLOOR_LOOKBACK, PROMO_LOOKBACK
from hypervector.data.pipeline import load_research_history
from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import ExportSchemaError, validate_export_dir
from hypervector.infra import ensure_data_layout, layout_report
from hypervector.nautilus.config_stub import phase2_check_report
from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.paper.fill_models import (
    DEFAULT_MAX_BOOK_AGE_MS,
    FILL_MODEL_L2_WALK_V1,
)
from hypervector.paper.runner import start_paper_daemon
from hypervector.regime.detectors import detect_regime_ema
from hypervector.regime.metrics import regime_detection_metrics
from hypervector.report import rank_trials
from hypervector.runs.db import RunsDB, TrialRow
from hypervector.strategies import register_all_strategies
from hypervector.strategies.registry import get_strategy, list_strategies
from hypervector.sweep.costs import resolve_cost_model
from hypervector.sweep.exits import EXIT_MODES, ExitConfig
from hypervector.sweep.search import run_grid_search
from hypervector.sweep.sizing import RiskConfig

# Phase 4 live secrets (paper public path works without keys; never print values).
SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"

# Phase 4a paper defaults (match configs/default.toml [paper]).
DEFAULT_PREFERRED_FILL_MODEL = FILL_MODEL_L2_WALK_V1
DEFAULT_METALABEL_ENABLED = False


def _secrets_present() -> bool:
    """True when both live secret env vars are set (values never logged)."""
    return bool(os.environ.get(SECRET_ENV_WALLET)) and bool(
        os.environ.get(SECRET_ENV_API_KEY)
    )


def _default_data_root() -> Path:
    return Path("data")


def _ensure_root(args: argparse.Namespace):
    """Create I2 layout under --data-root before any IO."""
    return ensure_data_layout(Path(args.data_root))


def _load_bars(args: argparse.Namespace):
    """Load OHLCV from cache or live HL→Binance→Bybit pipeline."""
    _ensure_root(args)
    return load_research_history(
        args.data_root,
        symbol=getattr(args, "symbol", "BTC"),
        timeframe=getattr(args, "timeframe", "1m"),
        lookback_days=getattr(args, "lookback", DEFAULT_LOOKBACK),
        strict_hl_only=getattr(args, "strict_hl_only", False),
        force_refresh=getattr(args, "force", False),
    )


def cmd_infra_init(args: argparse.Namespace) -> int:
    paths = _ensure_root(args)
    report = layout_report(paths.root)
    print(json.dumps(report, indent=2))
    return 0


def _paper_surface_flags() -> dict:
    """Capability/config surface for paper-check (booleans/strings only; no secrets)."""
    book_feed_ok = False
    l2_walk_ok = False
    try:
        from hypervector.paper.book import BookFeed  # noqa: F401

        book_feed_ok = True
    except Exception:  # noqa: BLE001 — surface probe only
        book_feed_ok = False
    try:
        from hypervector.paper.fill_models import L2WalkFillModel  # noqa: F401

        l2_walk_ok = True
    except Exception:  # noqa: BLE001 — surface probe only
        l2_walk_ok = False
    return {
        "preferred_fill_model": DEFAULT_PREFERRED_FILL_MODEL,
        "max_book_age_ms": int(DEFAULT_MAX_BOOK_AGE_MS),
        "book_feed": book_feed_ok,
        "l2_walk_available": l2_walk_ok,
        "metalabel_enabled": DEFAULT_METALABEL_ENABLED,
        "metalabel_default_off": True,
    }


def cmd_paper_check(args: argparse.Namespace) -> int:
    """Print paper/live layout identity and readiness flags (no secret values)."""
    paths = _ensure_root(args)
    report = layout_report(paths.root)
    paper = {
        "execution_mode": "paper",
        "decisions": str(paths.paper_decisions),
        "ledger": str(paths.paper_ledger),
        "live_feed_loop": True,
        # Default off; paper-run --sandbox sets shadow fields only (no real sandbox client).
        "sandbox_enabled": False,
        "secrets_present": _secrets_present(),
        "secret_env_names": [SECRET_ENV_WALLET, SECRET_ENV_API_KEY],
    }
    paper.update(_paper_surface_flags())
    report["paper"] = paper
    report["live"] = {
        "enabled": False,
        "note": "Phase 4b: set live.enabled + secrets; paper never places venue orders",
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_paper_run(args: argparse.Namespace) -> int:
    """Start paper daemon: warm-up + live HL bars + synthetic fills (no venue orders)."""
    _ensure_root(args)
    path = Path(args.path)
    if not path.is_dir():
        print(f"export path not found: {path}", file=sys.stderr)
        return 1

    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    preferred = str(
        getattr(args, "preferred_fill_model", DEFAULT_PREFERRED_FILL_MODEL)
    )
    max_book_age_ms = float(
        getattr(args, "max_book_age_ms", DEFAULT_MAX_BOOK_AGE_MS)
    )
    metalabel_enabled = bool(getattr(args, "metalabel", DEFAULT_METALABEL_ENABLED))
    try:
        result = start_paper_daemon(
            export_dir=path,
            data_root=Path(args.data_root),
            conviction=float(args.conviction),
            sandbox_enabled=bool(getattr(args, "sandbox", False)),
            fee_tier=int(getattr(args, "fee_tier", 0)),
            stop_file=stop_file,
            poll_interval_secs=float(getattr(args, "poll_interval", 5.0)),
            max_live_bars=int(args.max_live_bars)
            if getattr(args, "max_live_bars", None) is not None
            else None,
            lookback_days=int(args.lookback) if getattr(args, "lookback", None) else None,
            preferred_fill_model=preferred,
            max_book_age_ms=max_book_age_ms,
            metalabel_enabled=metalabel_enabled,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"paper-run failed: {exc}", file=sys.stderr)
        return 1

    out = {
        "ok": True,
        "execution_mode": result.execution_mode,
        "run_id": result.run_id,
        "export_dir": str(result.export_dir),
        "decisions_path": str(result.decisions_path),
        "warm_bars": result.warm_bars,
        "live_bars": result.live_bars,
        "bars_processed": result.bars_processed,
        "fills_count": result.fills_count,
        "stop_reason": result.stop_reason,
        "sandbox_enabled": bool(getattr(args, "sandbox", False)),
        "preferred_fill_model": preferred,
        "max_book_age_ms": max_book_age_ms,
        "metalabel_enabled": metalabel_enabled,
        "secrets_present": _secrets_present(),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    df, prov = _load_bars(args)
    print(
        json.dumps(
            {
                "bars": len(df),
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "lookback_days": args.lookback,
                "provenance": prov,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def cmd_regime(args: argparse.Namespace) -> int:
    df, prov = _load_bars(args)
    labels = detect_regime_ema(df["close"], fast=args.fast, slow=args.slow)
    metrics = regime_detection_metrics(labels)
    print(
        json.dumps(
            {
                "labels_sample": labels.value_counts().to_dict(),
                "metrics": metrics,
                "data_provenance": prov,
            },
            indent=2,
            default=str,
        )
    )
    if args.export:
        export_candidate(
            Path(args.data_root) / "exports",
            run_id=str(uuid.uuid4())[:8],
            meta={
                "track": "regime",
                "symbol": args.symbol,
                "timeframe": args.timeframe,
                "data_provenance": prov,
            },
            params={
                "strategy": "regime_ema",
                "fast": args.fast,
                "slow": args.slow,
            },
            metrics=metrics,
            regime_labels=labels,
            candidate_id=f"regime_{args.symbol}",
        )
    return 0


def _run_sweep(args: argparse.Namespace, role: str) -> int:
    register_all_strategies()
    root = _ensure_root(args).root
    df, prov = _load_bars(args)
    name = getattr(args, "strategy", None)
    if name:
        strategy = get_strategy(name)
        if strategy.role != role:
            print(
                f"strategy {name!r} has role={strategy.role!r}, expected {role!r}",
                file=sys.stderr,
            )
            return 1
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
        return 1
    init_cash = float(getattr(args, "cash", 10_000.0))
    cost = resolve_cost_model(getattr(args, "fee_model", "hl_taker_default"))
    mode = getattr(args, "tp_sl_mode", "atr")
    if mode not in EXIT_MODES:
        print(f"tp_sl_mode must be one of {EXIT_MODES}", file=sys.stderr)
        return 2
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
    print(
        json.dumps(
            {
                "strategy": strategy.name,
                "role": strategy.role,
                "bars": len(df),
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
    rows = []
    db = RunsDB(root / "runs" / "hypervector.db")
    run_id = str(uuid.uuid4())[:8]
    research_meta = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "lookback_days": args.lookback,
        "init_cash": init_cash,
        "tp_sl_mode": exit_cfg.mode,
        "exits": exit_cfg.to_dict(),
        "risk": risk_cfg.to_dict(),
        "costs": cost.to_dict(),
        "data_provenance": prov,
        "fee_model": getattr(args, "fee_model", "hl_taker_default"),
        "conviction": risk_cfg.default_conviction,
    }
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
    board = rank_trials(rows)
    print(board.to_string(index=False))
    if args.export and results and results[0].status == "ok":
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
    return 0


def cmd_sweep_up(args: argparse.Namespace) -> int:
    return _run_sweep(args, "uptrend")


def cmd_sweep_down(args: argparse.Namespace) -> int:
    return _run_sweep(args, "downtrend")


def cmd_report(args: argparse.Namespace) -> int:
    root = _ensure_root(args).root
    db = RunsDB(root / "runs" / "hypervector.db")
    rows = db.list_trials(track=args.track)
    board = rank_trials(rows)
    print(board.to_string(index=False) if len(board) else "(no trials)")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Re-export best trial for a track as a Phase 2-ready bundle.

    Requires trials written by a modern sweep that stored ``research_meta``
    (costs/risk/exits/cash). Older DB rows without research_meta are refused.
    """
    root = _ensure_root(args).root
    db = RunsDB(root / "runs" / "hypervector.db")
    rows = db.list_trials(track=args.track) if args.track else []
    # Prefer Phase 2-ready trials (research_meta from modern sweeps)
    ready = [
        r
        for r in rows
        if r.get("status") == "ok"
        and isinstance(r.get("research_meta"), dict)
        and r["research_meta"]
    ]
    best = ready[0] if ready else None
    if best is None:
        # Distinguish empty track vs legacy-only rows
        any_ok = any(r.get("status") == "ok" for r in rows)
        if any_ok:
            print(
                "ok trials exist but none have research_meta "
                "(costs/risk/exits/cash); re-run sweep-* with current CLI "
                "so Phase 2-ready config is stored",
                file=sys.stderr,
            )
        else:
            print("no ok trials to export", file=sys.stderr)
        return 1
    research = best["research_meta"]
    meta = {
        "track": best["track"],
        "exported_from": "cli",
        **research,
    }
    # CLI symbol/timeframe only fill gaps; research_meta wins when present
    meta.setdefault("symbol", getattr(args, "symbol", "BTC"))
    meta.setdefault("timeframe", getattr(args, "timeframe", "1m"))
    path = export_candidate(
        root / "exports",
        run_id=best["run_id"],
        meta=meta,
        params={"strategy": best["strategy"], **best["params"]},
        metrics={
            k: best[k]
            for k in (
                "net_pnl",
                "total_return_pct",
                "sharpe",
                "trade_count",
                "wins",
                "losses",
                "win_pct",
                "max_drawdown",
            )
        },
        candidate_id=f"export_{best['track']}_{best['id']}",
        strict=True,
    )
    print(str(path))
    return 0


def cmd_export_validate(args: argparse.Namespace) -> int:
    """Validate an export bundle against the Phase 1→2 schema contract."""
    path = Path(args.path)
    try:
        report = validate_export_dir(path, strict=bool(args.strict))
    except ExportSchemaError as exc:
        print(
            json.dumps(
                {"ok": False, "path": str(path), "errors": exc.errors},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    # Drop heavy nested blobs from CLI stdout unless --verbose
    out = {k: v for k, v in report.items() if k not in ("meta", "params", "metrics")}
    if args.verbose:
        out["meta"] = report["meta"]
        out["params"] = report["params"]
        out["metrics"] = report["metrics"]
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_phase2_check(args: argparse.Namespace) -> int:
    """Load export as Phase 2 loadout stub; confirm paper/live not implemented."""
    _ensure_root(args)
    path = Path(args.path)
    try:
        report = phase2_check_report(
            path,
            data_root=args.data_root,
            strict=not args.loose,
            probe_nautilus=not args.no_nautilus_probe,
        )
    except ExportSchemaError as exc:
        print(
            json.dumps(
                {"ok": False, "path": str(path), "errors": exc.errors},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, indent=2, default=str))
    if not report.get("paper_live", {}).get("implemented", False):
        print("paper/live not implemented", file=sys.stderr)
    return 0


def cmd_phase2_run(args: argparse.Namespace) -> int:
    """Run Phase 2 historical backtest from a strict export bundle.

    Paper/live modes are not implemented; if those flags are requested we only
    note that on stderr and still run the historical engine path.
    """
    _ensure_root(args)
    path = Path(args.path)
    if getattr(args, "paper", False) or getattr(args, "live", False):
        print("paper/live not implemented", file=sys.stderr)

    try:
        result = run_phase2_backtest(
            export_dir=path,
            data_root=Path(args.data_root),
            conviction=float(args.conviction),
            lookback_days=int(args.lookback) if args.lookback is not None else None,
        )
    except ExportSchemaError as exc:
        print(
            json.dumps(
                {"ok": False, "path": str(path), "errors": exc.errors},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    # Prefer on-disk summary payload; ensure CLI contract fields are present.
    try:
        payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    out = {
        "ok": True,
        "execution_mode": payload.get("execution_mode", "phase2_historical"),
        "orders_count": result.orders_count,
        "pnl": result.pnl,
        "report_path": str(result.report_path),
        "export_dir": str(result.export_dir),
        "run_id": payload.get("run_id"),
        "bars": payload.get("bars"),
        "conviction": payload.get("conviction", float(args.conviction)),
        "loadout": result.loadout_summary,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _add_market_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--symbol", default="BTC")
    p.add_argument("--timeframe", default="1m")
    p.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK,
        help=f"calendar days (floor={FLOOR_LOOKBACK}, default={DEFAULT_LOOKBACK}, promo={PROMO_LOOKBACK})",
    )
    p.add_argument(
        "--strict-hl-only",
        action="store_true",
        help="do not backfill from Binance/Bybit",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="ignore Parquet cache and re-fetch",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hypervector",
        description="Phase 1 research funnel (live HL history + Binance/Bybit backfill)",
    )
    p.add_argument("--data-root", default=str(_default_data_root()))
    sub = p.add_subparsers(dest="command", required=True)

    infra = sub.add_parser(
        "infra-init",
        help="Create I2 data layout (cache/runs/exports/logs/paper/live/nautilus)",
    )
    infra.set_defaults(func=cmd_infra_init)

    pc = sub.add_parser(
        "paper-check",
        help="Paper identity: layout, live_feed_loop, secrets_present (no key values)",
    )
    pc.set_defaults(func=cmd_paper_check)

    pr = sub.add_parser(
        "paper-run",
        help="Paper daemon: warm-up + live HL bars + synthetic fills (no venue orders)",
    )
    pr.add_argument(
        "--path",
        required=True,
        help="path to strict Phase 1.5 export directory",
    )
    pr.add_argument(
        "--conviction",
        type=float,
        default=0.5,
        help="0-1 conviction for position sizing (default 0.5)",
    )
    pr.add_argument(
        "--fee-tier",
        type=int,
        default=0,
        help="HL fee tier for CostProvider (default 0)",
    )
    pr.add_argument(
        "--sandbox",
        action="store_true",
        help="enable optional sandbox shadow fields (non-authoritative; default off)",
    )
    pr.add_argument(
        "--stop-file",
        default=None,
        help="if this path exists, daemon stops gracefully",
    )
    pr.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="seconds between REST candle polls (default 5)",
    )
    pr.add_argument(
        "--max-live-bars",
        type=int,
        default=None,
        help="stop after N live bars (offline / smoke tests)",
    )
    pr.add_argument(
        "--lookback",
        type=int,
        default=None,
        help=f"warm-up lookback days (default: export meta or {DEFAULT_LOOKBACK})",
    )
    pr.add_argument(
        "--preferred-fill-model",
        default=DEFAULT_PREFERRED_FILL_MODEL,
        help=(
            "preferred FillModel id when book is fresh "
            f"(default: {DEFAULT_PREFERRED_FILL_MODEL}; falls back to bar_close without book)"
        ),
    )
    pr.add_argument(
        "--max-book-age-ms",
        type=float,
        default=float(DEFAULT_MAX_BOOK_AGE_MS),
        help=f"stale book threshold in ms (default: {int(DEFAULT_MAX_BOOK_AGE_MS)})",
    )
    pr.add_argument(
        "--metalabel",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_METALABEL_ENABLED,
        help="enable metalabel scale-only conviction (default: off)",
    )
    pr.set_defaults(func=cmd_paper_run)

    h = sub.add_parser("history", help="Fetch/cache HL-max + Binance/Bybit backfill")
    _add_market_args(h)
    h.set_defaults(func=cmd_history)

    r = sub.add_parser("regime", help="Run regime detector on live/cached history")
    _add_market_args(r)
    r.add_argument("--fast", type=int, default=12)
    r.add_argument("--slow", type=int, default=48)
    r.add_argument("--export", action="store_true")
    r.set_defaults(func=cmd_regime)

    for name, fn in (("sweep-up", cmd_sweep_up), ("sweep-down", cmd_sweep_down)):
        s = sub.add_parser(name, help=f"Search {name} track on live/cached history")
        _add_market_args(s)
        s.add_argument(
            "--strategy",
            default=None,
            help="strategy name (default: trend_ride then crown_stack)",
        )
        s.add_argument(
            "--cash",
            type=float,
            default=10_000.0,
            help="starting cash for VectorBT portfolio (default: 10000)",
        )
        s.add_argument(
            "--tp-sl-mode",
            choices=list(EXIT_MODES),
            default="atr",
            help="TP/SL mode: fixed_rr | atr | trail (default: atr)",
        )
        s.add_argument("--sl-pct", type=float, default=0.01, help="fixed_rr stop as fraction")
        s.add_argument("--rr", type=float, default=2.0, help="reward:risk for fixed_rr/atr")
        s.add_argument("--atr-length", type=int, default=14)
        s.add_argument("--sl-atr-mult", type=float, default=1.5)
        s.add_argument("--trail-atr-mult", type=float, default=2.0)
        s.add_argument(
            "--risk-min",
            type=float,
            default=0.01,
            help="min equity risk fraction (default 1%%)",
        )
        s.add_argument(
            "--risk-max",
            type=float,
            default=0.05,
            help="max equity risk fraction (default 5%%)",
        )
        s.add_argument(
            "--conviction",
            type=float,
            default=0.5,
            help="0-1 conviction → risk between min and max (default 0.5 → ~3%%)",
        )
        s.add_argument(
            "--fee-model",
            default="hl_taker_default",
            help="hl_taker_default | hl_taker_tight | zero",
        )
        s.add_argument(
            "--no-costs",
            action="store_true",
            help="disable fees/slippage/funding (debug only)",
        )
        s.add_argument("--export", action="store_true")
        s.set_defaults(func=fn)

    rep = sub.add_parser("report", help="Print ranked board from SQLite")
    rep.add_argument("--track", default=None)
    rep.set_defaults(func=cmd_report)

    ex = sub.add_parser("export", help="Export best trial for a track")
    ex.add_argument("--track", required=True)
    ex.add_argument("--symbol", default="BTC")
    ex.add_argument("--timeframe", default="1m")
    ex.set_defaults(func=cmd_export)

    ev = sub.add_parser(
        "export-validate",
        help="Validate a Phase 1 export bundle (meta/params/metrics schema)",
    )
    ev.add_argument("--path", required=True, help="path to export directory")
    ev.add_argument(
        "--strict",
        action="store_true",
        help="require Phase 1.5 fields (init_cash, costs, risk, tp_sl_mode)",
    )
    ev.add_argument(
        "--verbose",
        action="store_true",
        help="include full meta/params/metrics in JSON output",
    )
    ev.set_defaults(func=cmd_export_validate)

    p2 = sub.add_parser(
        "phase2-check",
        help="Load export as Phase 2 StrategyLoadout stub (offline; no paper/live)",
    )
    p2.add_argument("--path", required=True, help="path to export directory")
    p2.add_argument(
        "--loose",
        action="store_true",
        help="do not require Phase 1.5 fields",
    )
    p2.add_argument(
        "--no-nautilus-probe",
        action="store_true",
        help="skip offline Nautilus import/config probe",
    )
    p2.set_defaults(func=cmd_phase2_check)

    p2r = sub.add_parser(
        "phase2-run",
        help="Run Phase 2 historical backtest from a strict export (Nautilus engine)",
    )
    p2r.add_argument("--path", required=True, help="path to export directory")
    p2r.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK,
        help=f"calendar days for research history (floor={FLOOR_LOOKBACK}, default={DEFAULT_LOOKBACK})",
    )
    p2r.add_argument(
        "--conviction",
        type=float,
        default=0.5,
        help="0-1 conviction for position sizing (default 0.5)",
    )
    p2r.add_argument(
        "--no-network",
        action="store_true",
        help="offline intent: history load is cache-first (no force refresh)",
    )
    p2r.add_argument(
        "--paper",
        action="store_true",
        help="request paper mode (not implemented; historical still runs)",
    )
    p2r.add_argument(
        "--live",
        action="store_true",
        help="request live mode (not implemented; historical still runs)",
    )
    p2r.set_defaults(func=cmd_phase2_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "lookback") and args.lookback is not None:
        if args.lookback < FLOOR_LOOKBACK:
            print(
                f"lookback must be >= {FLOOR_LOOKBACK} (promo={PROMO_LOOKBACK})",
                file=sys.stderr,
            )
            return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
