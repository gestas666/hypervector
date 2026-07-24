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
from hypervector.live.policy import (
    DEFAULT_MAX_NOTIONAL_USD,
    LivePolicyError,
    live_policy_from_env,
)
from hypervector.live.report import report_from_data_root as live_report_from_data_root
from hypervector.live.runner import start_live_daemon
from hypervector.paper.order_intent import NETWORK_MAINNET, ORDER_INTENT_SCHEMA
from hypervector.paper.report import report_from_data_root
from hypervector.paper.runner import start_paper_daemon

# Phase 4c: discoverable command inventory (status command + tests).
CLI_COMMANDS: tuple[str, ...] = (
    "infra-init",
    "status",
    "paper-check",
    "paper-report",
    "paper-run",
    "live-check",
    "live-report",
    "live-run",
    "history",
    "regime",
    "sweep-up",
    "sweep-down",
    "report",
    "export",
    "export-validate",
    "phase2-check",
    "phase2-run",
    "metalabel-train",
    "book-record",
    "autotune",
    "book-align",
)
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
# Phase 4b: daemon default is mainnet shadow (no venue submit).
DEFAULT_EXECUTION_MODE = "shadow"
ALLOWED_CLI_EXECUTION_MODES = frozenset({"shadow", "paper"})


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


def cmd_status(args: argparse.Namespace) -> int:
    """Pipeline + CLI inventory (no secret values; no place)."""
    paths = _ensure_root(args)
    ready = live_policy_from_env(enabled=False, armed=False).readiness()
    out = {
        "ok": True,
        "root": str(paths.root.resolve()),
        "pipeline": {
            "phase1_research": True,
            "phase2_historical": True,
            "paper_shadow_dry_run": True,
            "live_submit": True,
            "tui_gui": False,
        },
        "commands": list(CLI_COMMANDS),
        "paper": {
            "default_mode": DEFAULT_EXECUTION_MODE,
            "no_submit": True,
            "commands": ["paper-check", "paper-report", "paper-run"],
        },
        "live": {
            "submit_wired": bool(ready.get("submit_wired")),
            "can_start": bool(ready.get("can_start")),
            "enabled_default": False,
            "max_notional_usd": float(ready.get("max_notional_usd", DEFAULT_MAX_NOTIONAL_USD)),
            "network": ready.get("network", NETWORK_MAINNET),
            "commands": ["live-check", "live-report", "live-run"],
            "requires_for_run": ["--enabled", "--i-accept-live-risk", "secrets"],
        },
        "honesty": {
            "paper_never_constructs_exec_client": True,
            "live_run_fail_closed": True,
            "secret_values_never_printed": True,
        },
        "metalabel": _metalabel_status(paths.root),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _metalabel_status(data_root: Path | str) -> dict:
    """Compact metalabel readiness for status (default still off)."""
    try:
        from hypervector.ml.metalabel import probe_metalabel

        p = probe_metalabel(data_root=data_root)
    except Exception as exc:  # noqa: BLE001 — status must not fail
        return {
            "enabled_default": False,
            "ready": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "enabled_default": False,
        "ready": bool(p.get("loadable")),
        "bundle_root": p.get("bundle_root"),
        "n_features": p.get("n_features"),
        "calibrator": bool(p.get("calibrator_present")),
        "env_root_set": bool(p.get("env_root_set")),
        "error": p.get("error"),
        "enable_flag": "paper-run --metalabel",
    }


def _paper_surface_flags(data_root: Path | str | None = None) -> dict:
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
    metalabel_probe: dict = {
        "loadable": False,
        "bundle_root": None,
        "n_features": None,
        "calibrator_present": False,
        "error": None,
    }
    try:
        from hypervector.ml.metalabel import probe_metalabel

        metalabel_probe = probe_metalabel(data_root=data_root)
    except Exception as exc:  # noqa: BLE001 — surface probe only
        metalabel_probe = {
            "loadable": False,
            "bundle_root": None,
            "n_features": None,
            "calibrator_present": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        # Phase 4b shadow surface (strings/bools only; never secret values).
        "mode": DEFAULT_EXECUTION_MODE,
        "network": NETWORK_MAINNET,
        "no_submit": True,
        "submitted_default": False,
        "order_intent_schema": ORDER_INTENT_SCHEMA,
        "preferred_fill_model": DEFAULT_PREFERRED_FILL_MODEL,
        "max_book_age_ms": int(DEFAULT_MAX_BOOK_AGE_MS),
        "book_feed": book_feed_ok,
        "l2_walk_available": l2_walk_ok,
        "metalabel_enabled": DEFAULT_METALABEL_ENABLED,
        "metalabel_default_off": True,
        # Ready-to-enable (bundle installed); still off until paper-run --metalabel.
        "metalabel_ready": bool(metalabel_probe.get("loadable")),
        "metalabel_bundle_root": metalabel_probe.get("bundle_root"),
        "metalabel_n_features": metalabel_probe.get("n_features"),
        "metalabel_calibrator": bool(metalabel_probe.get("calibrator_present")),
        "metalabel_error": metalabel_probe.get("error"),
    }


def cmd_paper_check(args: argparse.Namespace) -> int:
    """Print paper/live layout identity and readiness flags (no secret values)."""
    paths = _ensure_root(args)
    report = layout_report(paths.root)
    paper = {
        # Alias of mode; Phase 4b default is shadow (mainnet, no venue orders).
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "decisions": str(paths.paper_decisions),
        "ledger": str(paths.paper_ledger),
        "live_feed_loop": True,
        # Default off; paper-run --sandbox sets shadow fields only (no real sandbox client).
        "sandbox_enabled": False,
        "secrets_present": _secrets_present(),
        "secret_env_names": [SECRET_ENV_WALLET, SECRET_ENV_API_KEY],
    }
    paper.update(_paper_surface_flags(paths.root))
    report["paper"] = paper
    live_pol = live_policy_from_env(enabled=False, armed=False)
    ready = live_pol.readiness()
    report["live"] = {
        "enabled": False,
        "decisions": str(paths.live_decisions),
        "ledger": str(paths.live_ledger),
        "submit_wired": bool(ready.get("submit_wired")),
        "note": ready.get(
            "note",
            "Live readiness — use live-check for start gates.",
        ),
        "readiness": ready,
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_live_check(args: argparse.Namespace) -> int:
    """Live readiness (policy only; never prints secret values; no submit)."""
    paths = _ensure_root(args)
    enabled = bool(getattr(args, "enabled", False))
    armed = bool(getattr(args, "armed", False))
    max_notional = float(
        getattr(args, "max_notional_usd", DEFAULT_MAX_NOTIONAL_USD)
    )
    policy = live_policy_from_env(
        enabled=enabled,
        armed=armed,
        max_notional_usd=max_notional,
    )
    ready = policy.readiness()
    report = {
        "ok": True,
        "root": str(paths.root.resolve()),
        "live_decisions": str(paths.live_decisions),
        "live_ledger": str(paths.live_ledger),
        "live": ready,
        "paper_path_unchanged": True,
        # live-check never places; True only would mean an active submit session.
        "venue_submit": False,
        "submit_wired": bool(ready.get("submit_wired")),
    }
    # Attempt start gate only for diagnostics (do not start daemon).
    try:
        policy.require_start()
        report["start_gate"] = "ok"
    except Exception as exc:  # LivePolicyError
        report["start_gate"] = "refused"
        report["start_gate_reason"] = str(exc)
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_live_run(args: argparse.Namespace) -> int:
    """Live daemon: mainnet place when enabled+armed+secrets (fail-closed)."""
    _ensure_root(args)
    path = Path(args.path)
    if not path.is_dir():
        print(f"export path not found: {path}", file=sys.stderr)
        return 1

    armed = bool(getattr(args, "i_accept_live_risk", False))
    if not armed:
        print(
            "live-run refused: pass --i-accept-live-risk to arm mainnet risk",
            file=sys.stderr,
        )
        return 1

    enabled = bool(getattr(args, "enabled", False))
    if not enabled:
        print(
            "live-run refused: pass --enabled (or set [live] enabled=true) "
            "to allow live execution",
            file=sys.stderr,
        )
        return 1

    max_notional = float(
        getattr(args, "max_notional_usd", DEFAULT_MAX_NOTIONAL_USD)
    )
    policy = live_policy_from_env(
        enabled=enabled,
        armed=armed,
        max_notional_usd=max_notional,
    )
    try:
        policy.require_start()
    except LivePolicyError as exc:
        print(f"live-run refused: {exc}", file=sys.stderr)
        return 1

    wallet = (os.environ.get(SECRET_ENV_WALLET) or "").strip()
    key = (os.environ.get(SECRET_ENV_API_KEY) or "").strip()
    if not wallet or not key:
        print(
            f"live-run refused: set {SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}",
            file=sys.stderr,
        )
        return 1

    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    try:
        result = start_live_daemon(
            export_dir=path,
            data_root=Path(args.data_root),
            policy=policy,
            wallet_address=wallet,
            private_key=key,
            conviction=float(getattr(args, "conviction", 0.5)),
            fee_tier=int(getattr(args, "fee_tier", 0)),
            stop_file=stop_file,
            poll_interval_secs=float(getattr(args, "poll_interval", 5.0)),
            max_live_bars=int(args.max_live_bars)
            if getattr(args, "max_live_bars", None) is not None
            else None,
            lookback_days=int(args.lookback) if getattr(args, "lookback", None) else None,
        )
    except LivePolicyError as exc:
        print(f"live-run refused: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"live-run failed: {exc}", file=sys.stderr)
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
        "places_count": result.places_count,
        "stop_reason": result.stop_reason,
        "cancel_attempted": result.cancel_attempted,
        "cancel_ok": result.cancel_ok,
        "cancel_error": result.cancel_error,
        "network": NETWORK_MAINNET,
        "max_notional_usd": max_notional,
        "venue_submit": True,  # armed live-run path (actual places depend on signals)
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_paper_report(args: argparse.Namespace) -> int:
    """Summarize paper/shadow decisions JSONL (read-only; no venue orders)."""
    _ensure_root(args)
    root = Path(args.data_root)
    decisions = Path(args.path) if getattr(args, "path", None) else None
    last_n = int(getattr(args, "last", 5))
    try:
        report = report_from_data_root(
            root,
            decisions_path=decisions,
            last_n=last_n,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_live_report(args: argparse.Namespace) -> int:
    """Summarize live decisions JSONL (read-only; no place)."""
    _ensure_root(args)
    root = Path(args.data_root)
    decisions = Path(args.path) if getattr(args, "path", None) else None
    last_n = int(getattr(args, "last", 5))
    try:
        report = live_report_from_data_root(
            root,
            decisions_path=decisions,
            last_n=last_n,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, default=str))
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
    metalabel_min_p = float(getattr(args, "metalabel_min_p", 0.5))
    metalabel_filter = bool(getattr(args, "metalabel_filter", True))
    execution_mode = str(getattr(args, "mode", DEFAULT_EXECUTION_MODE)).lower().strip()
    if execution_mode not in ALLOWED_CLI_EXECUTION_MODES:
        print(
            f"invalid --mode {execution_mode!r}; choose shadow|paper",
            file=sys.stderr,
        )
        return 1
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
            metalabel_min_p=metalabel_min_p,
            metalabel_filter=metalabel_filter,
            execution_mode=execution_mode,
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
        "mode": result.execution_mode,
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
        "metalabel_filter": metalabel_filter if metalabel_enabled else False,
        "metalabel_min_p": metalabel_min_p if metalabel_enabled else None,
        "secrets_present": _secrets_present(),
        "no_submit": True,
        "network": NETWORK_MAINNET,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_book_record(args: argparse.Namespace) -> int:
    """Poll HL public L2 and append snapshots under data/cache/book/."""
    from hypervector.data.book_record import append_snapshot, run_book_recorder

    paths = _ensure_root(args)
    symbol = str(getattr(args, "symbol", "BTC"))
    once = bool(getattr(args, "once", False))
    if once:
        try:
            row = append_snapshot(paths.root, symbol)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "mode": "once", **row}, indent=2, default=str))
        return 0

    interval = float(getattr(args, "interval", 2.0))
    max_n = getattr(args, "max_snapshots", None)
    stop = getattr(args, "stop_file", None)
    try:
        result = run_book_recorder(
            paths.root,
            symbol=symbol,
            interval_secs=interval,
            max_snapshots=int(max_n) if max_n is not None else None,
            stop_file=stop,
        )
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
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
    apply_costs = not getattr(args, "no_costs", False)
    research_meta = {
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
    # Prefer Phase 2-ready trials (research_meta from modern sweeps).
    # list_trials already ranks by net_pnl DESC. Prefer cost-aware rows
    # (non-zero taker_fee) so --no-costs diagnostics never become the export.
    ready = [
        r
        for r in rows
        if r.get("status") == "ok"
        and isinstance(r.get("research_meta"), dict)
        and r["research_meta"]
    ]

    def _costs_applied(r: dict) -> bool:
        meta = r.get("research_meta") or {}
        if "apply_costs" in meta:
            return bool(meta["apply_costs"])
        # Legacy rows: treat fee_model zero / explicit zero fees as diagnostic-only
        if meta.get("fee_model") == "zero":
            return False
        costs = meta.get("costs") or {}
        try:
            return float(costs.get("taker_fee", 0) or 0) > 0
        except (TypeError, ValueError):
            return False

    costed = [r for r in ready if _costs_applied(r)]
    best = costed[0] if costed else (ready[0] if ready else None)
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
    """Load export as Phase 2 loadout stub; note paper dry-run is paper-run."""
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
    print(
        "note: phase2-run is historical only; "
        "paper/shadow dry-run → paper-run (default shadow, no venue orders); "
        "live venue submit → live-run (--enabled + --i-accept-live-risk + secrets)",
        file=sys.stderr,
    )
    return 0


def cmd_phase2_run(args: argparse.Namespace) -> int:
    """Run Phase 2 historical backtest from a strict export bundle.

    ``--paper`` / ``--live`` on phase2-run do not switch engines: historical
    path still runs. Paper dry-run is ``paper-run``; live venue is ``live-run``.
    """
    _ensure_root(args)
    path = Path(args.path)
    if getattr(args, "paper", False):
        print(
            "note: phase2-run --paper does not start paper daemon; "
            "use: hypervector paper-run --path <export>",
            file=sys.stderr,
        )
    if getattr(args, "live", False):
        print(
            "note: phase2-run --live does not place venue orders; "
            "use: hypervector live-run --path <export> --enabled --i-accept-live-risk",
            file=sys.stderr,
        )

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


def cmd_metalabel_train(args: argparse.Namespace) -> int:
    """Walk-forward LightGBM retrain; labels match export strategy exits."""
    from hypervector.ml.walk_forward import run_walk_forward_metalabel

    paths = _ensure_root(args)
    export_path = Path(args.path)
    if not export_path.is_dir():
        print(json.dumps({"ok": False, "error": f"export not found: {export_path}"}))
        return 1
    try:
        result = run_walk_forward_metalabel(
            export_dir=export_path,
            data_root=paths.root,
            out_dir=Path(args.out) if args.out else None,
            lookback_days=int(args.lookback) if args.lookback is not None else None,
            train_days=int(args.train_days),
            test_days=int(args.test_days),
            step_days=int(args.step_days) if args.step_days is not None else None,
            embargo_minutes=int(args.embargo_minutes),
            max_hold_bars=int(args.max_hold_bars),
        )
    except Exception as exc:  # noqa: BLE001 — surface as JSON error
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1

    install_path = None
    if getattr(args, "install", False):
        import shutil

        dest = paths.root / "models" / "metalabel"
        dest.mkdir(parents=True, exist_ok=True)
        for name in (
            "metalabel_lgbm.txt",
            "metalabel_calibrator.joblib",
            "metalabel_metadata.json",
        ):
            src = result.bundle_dir / name
            if src.is_file():
                shutil.copy2(src, dest / name)
        report_src = result.bundle_dir / "walk_forward_report.json"
        if report_src.is_file():
            shutil.copy2(report_src, dest / "walk_forward_report.json")
        install_path = str(dest.resolve())

    out = {
        **result.report,
        "installed_to": install_path,
        "env_hint": (
            f"export HYPERVECTOR_METALABEL_ROOT={install_path or result.bundle_dir}"
        ),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_autotune(args: argparse.Namespace) -> int:
    """Run Optuna / Karpathy autotuning for strategy optimization."""
    from hypervector.sweep.autotune import run_optuna_autotune

    res = run_optuna_autotune(
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.lookback,
        n_trials=args.n_trials,
        data_root=args.data_root,
        cost_preset=args.fee_model,
        export_best=not args.no_export,
        book_data_path=getattr(args, "book_path", None),
        sampler=getattr(args, "sampler", "hybrid"),
    )
    out = {
        "ok": True,
        "strategy": res.strategy_name,
        "symbol": res.symbol,
        "timeframe": res.timeframe,
        "lookback_days": res.lookback_days,
        "n_trials": res.n_trials,
        "sampler_used": res.sampler_used,
        "best_params": res.best_params,
        "best_exit_cfg": res.best_exit_cfg,
        "best_metrics": res.best_metrics,
        "export_dir": str(res.export_dir) if res.export_dir else None,
        "board_path": str(res.board_path),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_regime_eval(args: argparse.Namespace) -> int:
    """Evaluate forward return accuracy and predictive edge of Ultimate Regime Classifier."""
    from hypervector.data.pipeline import load_research_history
    from hypervector.regime.evaluator import evaluate_regime_accuracy

    root = Path(args.data_root)
    df_1m, _ = load_research_history(root, symbol=args.symbol, timeframe=args.timeframe, lookback_days=args.lookback)

    book_path = getattr(args, "book_path", None)
    if book_path and Path(book_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl
        df_book = load_l2_jsonl(book_path)
        df_1m = align_orderbook_to_ohlcv(df_1m, df_book)

    rpt = evaluate_regime_accuracy(df_1m, forward_horizon=args.forward_horizon)
    out = {
        "ok": True,
        "symbol": rpt.symbol,
        "timeframe": rpt.timeframe,
        "total_bars": rpt.total_bars,
        "forward_horizon": args.forward_horizon,
        "overall_directional_accuracy_pct": rpt.overall_directional_accuracy,
        "regime_stats": rpt.regime_stats,
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    """Run Phase-1.5 backtest across any registered strategy with leverage & fee models."""
    from hypervector.data.pipeline import load_research_history
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy
    from hypervector.sweep.costs import resolve_cost_model
    from hypervector.sweep.exits import ExitConfig
    from hypervector.sweep.sizing import RiskConfig
    from hypervector.sweep.metrics import compute_trial_metrics

    register_all_strategies()
    root = Path(args.data_root)
    df_bars, _ = load_research_history(
        root, symbol=args.symbol, timeframe=args.timeframe, lookback_days=args.lookback
    )

    book_path = getattr(args, "book_path", None)
    if book_path and Path(book_path).is_file():
        from hypervector.data.book_align import align_orderbook_to_ohlcv, load_l2_jsonl
        df_book = load_l2_jsonl(book_path)
        df_bars = align_orderbook_to_ohlcv(df_bars, df_book)

    spec = get_strategy(args.strategy)
    params = {}
    if getattr(args, "book_gate", False):
        params["book_gate"] = True
        params["max_spread_bps"] = getattr(args, "max_spread_bps", 3.0)
        params["min_obi"] = getattr(args, "min_obi", 0.1)

    entries, exits, direction = spec.build_signals(df_bars, **params)
    close = df_bars["close"].astype(float)

    exit_cfg = ExitConfig(
        mode=args.exit_mode,
        sl_atr_mult=args.sl_atr_mult,
        rr=args.rr,
    )
    risk_cfg = RiskConfig(max_size_frac=args.leverage)
    cost = resolve_cost_model(args.fee_model)

    m = compute_trial_metrics(
        close,
        entries,
        exits,
        direction=direction,
        init_cash=args.init_cash,
        df=df_bars,
        cost=cost,
        exit_cfg=exit_cfg,
        risk_cfg=risk_cfg,
    )

    out = {
        "ok": True,
        "strategy": args.strategy,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "lookback_days": args.lookback,
        "leverage": args.leverage,
        "initial_cash": args.init_cash,
        "fee_model": args.fee_model,
        "orderbook_gated": getattr(args, "book_gate", False),
        "metrics": {
            "net_pnl": round(m["net_pnl"], 2),
            "total_return_pct": round(m["total_return_pct"], 2),
            "sharpe_annualized": round(m["sharpe"], 2),
            "max_drawdown_pct": round(m["max_drawdown"], 2),
            "total_trades": m["trade_count"],
            "wins": m["wins"],
            "losses": m["losses"],
            "win_pct": round(m["win_pct"], 1),
            "profit_factor": round(m["profit_factor"], 2) if m.get("profit_factor") is not None else None,
            "avg_trade_pnl": round(m["net_pnl"] / m["trade_count"], 2) if m["trade_count"] > 0 else 0.0,
        },
    }
    print(json.dumps(out, indent=2, default=str))
    return 0




def cmd_book_align(args: argparse.Namespace) -> int:
    """Align L2 orderbook snapshot data with OHLCV bars and export parquet."""
    from hypervector.data.book_align import (
        align_orderbook_to_ohlcv,
        load_l2_jsonl,
        load_l2_sqlite_feature_samples,
    )

    root = Path(args.data_root)
    df_bars, prov = load_research_history(
        root,
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.lookback,
    )

    book_path = Path(args.book_path)
    if str(book_path).endswith(".jsonl"):
        df_book = load_l2_jsonl(book_path)
    else:
        df_book = load_l2_sqlite_feature_samples(book_path, coin=args.symbol)

    aligned = align_orderbook_to_ohlcv(df_bars, df_book)
    out_dir = root / "cache" / "aligned"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{args.symbol}_{args.timeframe}_aligned_book.parquet"
    aligned.to_parquet(out_file)

    out = {
        "ok": True,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars_count": len(aligned),
        "book_records": len(df_book),
        "aligned_path": str(out_file),
        "sample": aligned[["close", "spread_bps", "obi_5", "book_depth_ratio"]].tail(3).to_dict(orient="records"),
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "================================================================================\n"
            "⚡ HYPERVECTOR PERPETUALS BACKTEST ENGINE & ULTIMATE REGIME DETECTOR\n"
            "================================================================================\n"
            "Autonomous quant strategy research (VectorBT vectorized engine), phase2 historical\n"
            "backtest (Nautilus event-driven engine), paper/shadow dry-run, live-run execution,\n"
            "multi-timeframe regime classification, Karpathy/Optuna autotuning, LightGBM metalabeling,\n"
            "and Rust TUI cockpit."
        ),
        epilog=(
            "EXAMPLES & COMMON WORKFLOWS:\n"
            "  ----------------------------------------------------------------------------\n"
            "  1. Run Fast VectorBT Strategy Backtest (Phase 1.5 Vectorized Simulation):\n"
            "     uv run python -m hypervector backtest --strategy crown_stack_long --symbol BTC --timeframe 5m --leverage 2.0 --fee-model hl_maker\n"
            "     uv run python -m hypervector backtest --strategy oi_divergence_long --symbol BTC --timeframe 1m --book-gate --max-spread-bps 3.0\n\n"
            "  2. Run Event-Driven Nautilus Engine Backtest:\n"
            "     uv run python -m hypervector phase2-run --path data/exports/<export_dir> --lookback 180\n\n"
            "  3. Run Ultimate Regime Accuracy Evaluator:\n"
            "     uv run python -m hypervector regime-eval --symbol BTC --timeframe 5m --lookback 180\n"
            "     uv run python -m hypervector regime-eval --symbol BTC --timeframe 1m --book-path data/cache/book/BTC_l2_20260723.jsonl\n\n"
            "  4. Launch Visual Quant TA Terminal Cockpit (Rust Ratatui):\n"
            "     cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --timeframe 5m\n"
            "     cargo run -p hypervector-tui --bin tui-regime-detector -- --symbol BTC --live --refresh-ms 250\n\n"
            "  5. Karpathy & Optuna Dual Autotuning:\n"
            "     uv run python -m hypervector autotune --strategy crown_stack_long --sampler hybrid --n-trials 100\n"
            "     uv run python -m hypervector autotune --strategy oi_divergence_long --sampler karpathy\n\n"
            "  6. LightGBM Metalabeling Walk-Forward Training:\n"
            "     uv run python -m hypervector metalabel-train --path data/exports/<export_dir> --install\n\n"
            "  7. Pipeline & System Status:\n"
            "     uv run python -m hypervector status\n"
            "================================================================================"
        ),
    )
    p.add_argument("--data-root", default=str(_default_data_root()))
    sub = p.add_subparsers(dest="command", required=True)

    infra = sub.add_parser(
        "infra-init",
        help="Create I2 data layout (cache/runs/exports/logs/paper/live/nautilus)",
    )
    infra.set_defaults(func=cmd_infra_init)

    st = sub.add_parser(
        "status",
        help=(
            "Pipeline + command inventory + paper/live honesty flags "
            "(no secret values; no place)"
        ),
    )
    st.set_defaults(func=cmd_status)

    pc = sub.add_parser(
        "paper-check",
        help=(
            "Paper/shadow identity: mode, mainnet network, no_submit "
            "(booleans/strings only; never secret values)"
        ),
    )
    pc.set_defaults(func=cmd_paper_check)

    prep = sub.add_parser(
        "paper-report",
        help=(
            "Summarize paper/shadow decisions.jsonl (fill models, modes, "
            "intents, honesty counters; read-only)"
        ),
    )
    prep.add_argument(
        "--path",
        default=None,
        help="optional decisions JSONL path (default: <data-root>/paper/decisions/decisions.jsonl)",
    )
    prep.add_argument(
        "--last",
        type=int,
        default=5,
        help="include last N market fills in sample (default 5)",
    )
    prep.set_defaults(func=cmd_paper_report)

    lrep = sub.add_parser(
        "live-report",
        help=(
            "Summarize live decisions.jsonl (submitted/place_attempted, "
            "modes; read-only; no place)"
        ),
    )
    lrep.add_argument(
        "--path",
        default=None,
        help="optional decisions JSONL path (default: <data-root>/live/decisions/decisions.jsonl)",
    )
    lrep.add_argument(
        "--last",
        type=int,
        default=5,
        help="include last N market fills in sample (default 5)",
    )
    lrep.set_defaults(func=cmd_live_report)

    lc = sub.add_parser(
        "live-check",
        help=(
            "Live readiness: secrets present (bool), arm/enabled gates, "
            "max notional, submit_wired (no secret values; no place)"
        ),
    )
    lc.add_argument(
        "--enabled",
        action="store_true",
        help="simulate [live] enabled=true for readiness (default false)",
    )
    lc.add_argument(
        "--armed",
        action="store_true",
        help="simulate --i-accept-live-risk arm for readiness (default false)",
    )
    lc.add_argument(
        "--max-notional-usd",
        type=float,
        default=DEFAULT_MAX_NOTIONAL_USD,
        help=f"max notional cap for policy (default {DEFAULT_MAX_NOTIONAL_USD})",
    )
    lc.set_defaults(func=cmd_live_check)

    lr = sub.add_parser(
        "live-run",
        help=(
            "Live mainnet daemon: requires --enabled + --i-accept-live-risk + secrets; "
            "writes data/live/ decisions (fail-closed)"
        ),
    )
    lr.add_argument(
        "--path",
        required=True,
        help="path to strict Phase 1.5 export directory",
    )
    lr.add_argument(
        "--enabled",
        action="store_true",
        help="set [live] enabled=true for this run (required)",
    )
    lr.add_argument(
        "--i-accept-live-risk",
        action="store_true",
        dest="i_accept_live_risk",
        help="explicit arm for mainnet risk (required)",
    )
    lr.add_argument(
        "--max-notional-usd",
        type=float,
        default=DEFAULT_MAX_NOTIONAL_USD,
        help=f"hard notional cap (default {DEFAULT_MAX_NOTIONAL_USD})",
    )
    lr.add_argument(
        "--conviction",
        type=float,
        default=0.5,
        help="fixed conviction [0,1] (default 0.5)",
    )
    lr.add_argument(
        "--fee-tier",
        type=int,
        default=0,
        help="HL fee tier index (default 0)",
    )
    lr.add_argument(
        "--stop-file",
        default=None,
        help="path: when this file exists, stop gracefully",
    )
    lr.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="seconds between bar polls (default 5)",
    )
    lr.add_argument(
        "--max-live-bars",
        type=int,
        default=None,
        help="stop after N live bars (smoke / offline cap)",
    )
    lr.add_argument(
        "--lookback",
        type=int,
        default=None,
        help="warm-up lookback days (default from export meta)",
    )
    lr.set_defaults(func=cmd_live_run)

    pr = sub.add_parser(
        "paper-run",
        help=(
            "Paper/shadow daemon: mainnet HL bars + synthetic fills; "
            "no venue orders (default mode=shadow)"
        ),
    )
    pr.add_argument(
        "--path",
        required=True,
        help="path to strict Phase 1.5 export directory",
    )
    pr.add_argument(
        "--mode",
        choices=sorted(ALLOWED_CLI_EXECUTION_MODES),
        default=DEFAULT_EXECUTION_MODE,
        help=(
            "execution mode: shadow (default; mainnet-honest intents, no venue orders) "
            "or paper (offline-compat synthetic path)"
        ),
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
        help=(
            "enable LightGBM metalabel: scale conviction by p and "
            "filter entries below --metalabel-min-p (default: off)"
        ),
    )
    pr.add_argument(
        "--metalabel-min-p",
        type=float,
        default=0.5,
        help="min metalabel p to allow entry when filtering (default: 0.5)",
    )
    pr.add_argument(
        "--metalabel-filter",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "when metalabel is on, skip entries with p < min-p "
            "(default: on; use --no-metalabel-filter for scale-only)"
        ),
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
        s = sub.add_parser(name, help=f"Search {name} track on live/cached history (VectorBT engine)")
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
        help=(
            "Load export as Phase 2 StrategyLoadout stub "
            "(historical; paper dry-run is paper-run)"
        ),
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
        help="legacy flag: does not switch engines — use paper-run for dry-run",
    )
    p2r.add_argument(
        "--live",
        action="store_true",
        help="legacy flag: does not place; use live-run for venue submit",
    )
    p2r.set_defaults(func=cmd_phase2_run)

    mt = sub.add_parser(
        "metalabel-train",
        help=(
            "Walk-forward LightGBM metalabel retrain on strategy entries "
            "from a Phase-1.5 export (labels match export TP/SL)"
        ),
    )
    mt.add_argument(
        "--path",
        required=True,
        help="export directory (params/meta with strategy + exits)",
    )
    mt.add_argument(
        "--lookback",
        type=int,
        default=None,
        help=f"history lookback days (default: export meta or {DEFAULT_LOOKBACK})",
    )
    mt.add_argument(
        "--train-days",
        type=int,
        default=45,
        help="walk-forward train window in days (default 45)",
    )
    mt.add_argument(
        "--test-days",
        type=int,
        default=15,
        help="walk-forward OOS test window in days (default 15)",
    )
    mt.add_argument(
        "--step-days",
        type=int,
        default=None,
        help="step between OOS windows (default: test-days)",
    )
    mt.add_argument(
        "--embargo-minutes",
        type=int,
        default=60,
        help="purged-CV embargo minutes (default 60)",
    )
    mt.add_argument(
        "--max-hold-bars",
        type=int,
        default=120,
        help="label barrier timeout in bars (default 120 = 2h on 1m)",
    )
    mt.add_argument(
        "--out",
        default=None,
        help="bundle output dir (default data/models/metalabel/wf_<strategy>_<ts>)",
    )
    mt.add_argument(
        "--install",
        action="store_true",
        help=(
            "also copy final model files into data/models/metalabel/ "
            "and print HYPERVECTOR_METALABEL_ROOT"
        ),
    )
    mt.set_defaults(func=cmd_metalabel_train)

    br = sub.add_parser(
        "book-record",
        help="Record HL public L2 snapshots under data/cache/book/ (jsonl)",
    )
    br.add_argument("--symbol", default="BTC")
    br.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="seconds between snapshots (default 2)",
    )
    br.add_argument(
        "--once",
        action="store_true",
        help="fetch and write a single snapshot then exit",
    )
    br.add_argument(
        "--max-snapshots",
        type=int,
        default=None,
        help="stop after N snapshots (omit = run until stop-file)",
    )
    br.add_argument(
        "--stop-file",
        default=None,
        help="stop when this path exists",
    )
    br.set_defaults(func=cmd_book_record)

    at = sub.add_parser(
        "autotune",
        help="Run Karpathy / Optuna TPE parameter autotuning for strategy optimization (VectorBT engine)",
    )
    _add_market_args(at)
    at.add_argument(
        "--strategy",
        default="crown_stack_long",
        help="strategy name (e.g. crown_stack_long, pine_composite_long, crown_stack_short)",
    )
    at.add_argument(
        "--n-trials",
        type=int,
        default=100,
        help="number of Optuna/Karpathy trial iterations (default 100)",
    )
    at.add_argument(
        "--fee-model",
        default="hl_taker_default",
        help="cost model: hl_taker_default | hl_taker_tight | zero",
    )
    at.add_argument(
        "--book-path",
        default=None,
        help="optional orderbook L2 data path (JSONL or SQLite)",
    )
    at.add_argument(
        "--sampler",
        choices=["hybrid", "karpathy", "optuna"],
        default="hybrid",
        help="search sampler: hybrid | karpathy (random-adaptive + elite zoom) | optuna (TPE)",
    )
    at.add_argument(
        "--no-export",
        action="store_true",
        help="do not automatically export best strategy configuration",
    )
    at.set_defaults(func=cmd_autotune)

    ba = sub.add_parser(
        "book-align",
        help="Align historical L2 orderbook data (JSONL or SQLite) with OHLCV bars",
    )
    _add_market_args(ba)
    ba.add_argument(
        "--book-path",
        required=True,
        help="path to L2 orderbook data (data/cache/book/BTC_l2_...jsonl or impulse_calibration_snapshot.sqlite.zst)",
    )
    ba.set_defaults(func=cmd_book_align)

    re_parser = sub.add_parser(
        "regime-eval",
        help="Evaluate forward return accuracy and predictive edge of Ultimate Regime Classifier",
    )
    _add_market_args(re_parser)
    re_parser.add_argument(
        "--forward-horizon",
        type=int,
        default=15,
        help="number of forward bars to evaluate return accuracy (default 15)",
    )
    re_parser.add_argument(
        "--book-path",
        default=None,
        help="optional orderbook L2 data path (JSONL or SQLite)",
    )
    re_parser.set_defaults(func=cmd_regime_eval)

    bt = sub.add_parser(
        "backtest",
        help="Run Phase-1.5 backtest across any registered strategy with leverage & fee models (VectorBT engine)",
    )
    _add_market_args(bt)
    bt.add_argument(
        "--strategy",
        default="crown_stack_long",
        help="strategy name (e.g. crown_stack_long, oi_divergence_long, funding_momentum, pine_composite_long)",
    )
    bt.add_argument(
        "--leverage",
        type=float,
        default=2.0,
        help="position leverage scaling factor 1.0-10.0 (default 2.0)",
    )
    bt.add_argument(
        "--init-cash",
        type=float,
        default=10000.0,
        help="starting portfolio balance USD (default 10000.0)",
    )
    bt.add_argument(
        "--fee-model",
        default="hl_maker",
        help="fee preset: hl_maker | hl_base_taker | hl_referred_taker | hl_vip1_taker",
    )
    bt.add_argument(
        "--exit-mode",
        default="atr",
        help="exit mode: atr | fixed_rr | trail",
    )
    bt.add_argument(
        "--sl-atr-mult",
        type=float,
        default=2.5,
        help="ATR stop loss multiplier (default 2.5)",
    )
    bt.add_argument(
        "--rr",
        type=float,
        default=3.0,
        help="risk/reward ratio (default 3.0)",
    )
    bt.add_argument(
        "--book-gate",
        action="store_true",
        help="enable orderbook entry gating filter",
    )
    bt.add_argument(
        "--max-spread-bps",
        type=float,
        default=3.0,
        help="max bid-ask spread in bps for book gating (default 3.0)",
    )
    bt.add_argument(
        "--min-obi",
        type=float,
        default=0.10,
        help="min orderbook imbalance ratio for book gating (default 0.10)",
    )
    bt.add_argument(
        "--book-path",
        default=None,
        help="optional orderbook L2 snapshot data path (JSONL or SQLite)",
    )
    bt.set_defaults(func=cmd_backtest)

    return p


def _load_dotenv_if_present() -> None:
    """Load repo-root ``.env`` KEY=VALUE into os.environ without overwriting.

    Minimal parser (no python-dotenv dependency). Skips blank/comment lines.
    Secrets stay local (``.env`` is gitignored).
    """
    candidates = (
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    )
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not path.is_file():
            continue
        seen.add(resolved)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key or key in os.environ:
                continue
            val = val.strip().strip("'").strip('"')
            os.environ[key] = val


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_if_present()
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
