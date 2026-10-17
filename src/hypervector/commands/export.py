"""Export command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from contextlib import closing
import json
import sys
from pathlib import Path
from hypervector.export.phase2 import export_candidate
from hypervector.export.schema import ExportSchemaError, validate_export_dir
from hypervector.runs.db import RunsDB
from hypervector.commands.common import _ensure_root


def cmd_export(args: argparse.Namespace) -> int:
    """Re-export best trial for a track as a Phase 2-ready bundle.

    Requires trials written by a modern sweep that stored ``research_meta``
    (costs/risk/exits/cash). Older DB rows without research_meta are refused.
    """
    root = _ensure_root(args).root
    with closing(RunsDB(root / "runs" / "hypervector.db")) as db:
        rows = db.list_trials(track=args.track) if args.track else []
    best = _select_export_trial(rows)
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
    path = _publish_selected_export(root, best, args)
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


def _select_export_trial(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Prefer costed, schema-ready trials while retaining weak measured results."""
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

    costed = [r for r in ready if _costs_applied(r)]
    return costed[0] if costed else (ready[0] if ready else None)


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


def _publish_selected_export(
    root: Path, best: dict[str, object], args: argparse.Namespace
) -> Path:
    """Publish one strict bundle from the selected stored trial metadata."""
    research = best["research_meta"]
    meta = {
        "track": best["track"],
        "exported_from": "cli",
        **research,
    }
    # CLI symbol/timeframe only fill gaps; research_meta wins when present
    meta.setdefault("symbol", getattr(args, "symbol", "BTC"))
    meta.setdefault("timeframe", getattr(args, "timeframe", "1m"))
    return export_candidate(
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
