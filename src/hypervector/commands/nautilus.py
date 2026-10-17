"""Nautilus command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.export.schema import ExportSchemaError
from hypervector.nautilus.config_stub import phase2_check_report
from hypervector.nautilus.runner import run_phase2_backtest
from hypervector.commands.common import _ensure_root


def cmd_phase2_check(args: argparse.Namespace) -> int:
    """Load a strategy bundle as a Nautilus loadout and probe the engine offline."""
    _ensure_root(args)
    path = Path(args.export)
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
        "note: 'nautilus run' is historical only; "
        "paper/shadow dry-run → 'paper run' (default shadow, no venue orders); "
        "live execution → 'live start' (--enabled + --i-accept-live-risk)",
        file=sys.stderr,
    )
    return 0


def cmd_phase2_run(args: argparse.Namespace) -> int:
    """Run a strict strategy bundle through the historical Nautilus engine."""
    _ensure_root(args)
    path = Path(args.export)

    try:
        result = run_phase2_backtest(
            export_dir=path,
            data_root=Path(args.data_root),
            conviction=float(args.conviction),
            lookback_days=int(args.lookback) if args.lookback is not None else None,
            allow_network=not args.no_network,
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

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
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
