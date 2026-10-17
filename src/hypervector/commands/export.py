"""Export command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import closing
import json
import sys
from pathlib import Path
from typing import Any

from hypervector.commands.common import CommandRefused
from hypervector.commands.exports import (
    TRIAL_METRICS,
    costs_applied,
    explain_no_export_trial,
    resolve_export,
    select_export_trial,
)
from hypervector.export.schema import ExportSchemaError, validate_export_dir
from hypervector.infra import ensure_data_layout, paths_for
from hypervector.runs.db import RunsDB


def cmd_create(args: argparse.Namespace) -> int:
    """Publish the best stored sweep trial matching the filters as a strict bundle.

    Requires trials written by a sweep that stored ``research_meta`` (costs,
    risk, exits, cash). Selecting reads only; directories are created right
    before the bundle is written.
    """
    filters = {
        "run_id": args.run_id,
        "track": args.track,
        "strategy": args.strategy,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
    }
    if args.track is None and args.run_id is None:
        raise CommandRefused("export create needs --track or --run-id (or both)")
    rows = stored_trials(args.data_root, track=args.track, run_id=args.run_id)
    best = select_export_trial(rows, **filters)
    if best is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": args.command,
                    "error_type": "NoExportableTrial",
                    "error": explain_no_export_trial(rows, filters),
                    "filters": {k: v for k, v in filters.items() if v is not None},
                }
            ),
            file=sys.stderr,
        )
        return 1
    path = publish_trial_export(
        Path(args.data_root),
        best,
        candidate_id=f"export_{best['track']}_{best['id']}",
    )
    research = best["research_meta"]
    out = {
        "ok": True,
        "candidate_id": path.name,
        "export_dir": str(path),
        "run_id": best["run_id"],
        "trial_id": best["id"],
        "track": best["track"],
        "strategy": best["strategy"],
        "symbol": research.get("symbol"),
        "timeframe": research.get("timeframe"),
        "metrics": {key: best.get(key) for key in TRIAL_METRICS},
        "costs_applied": costs_applied(best),
        "artifacts": {"export": str(path)},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a strategy bundle; strict unless --loose is given (exit 1 if invalid).

    ``--require-costed`` / ``--require-metrics`` (opt-in) turn a zero-cost
    measurement or a missing metric key into an invalid bundle; otherwise they
    stay non-fatal warnings, echoed on stderr.
    """
    path = resolve_export(args.export, args.data_root)
    strict = not args.loose
    require_costed = bool(getattr(args, "require_costed", False))
    require_metrics = bool(getattr(args, "require_metrics", False))
    try:
        report = validate_export_dir(
            path,
            strict=strict,
            require_costed=require_costed,
            require_metrics=require_metrics,
        )
    except ExportSchemaError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "command": args.command,
                    "error_type": "ExportSchemaError",
                    "error": str(exc),
                    "export_dir": str(path),
                    "path": str(path),
                    "strict": strict,
                    "errors": exc.errors,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    # Heavy nested blobs only with --verbose.
    out: dict[str, Any] = {
        k: v for k, v in report.items() if k not in ("meta", "params", "metrics")
    }
    out["candidate_id"] = path.name
    out["export_dir"] = str(path)
    if args.verbose:
        out["meta"] = report["meta"]
        out["params"] = report["params"]
        out["metrics"] = report["metrics"]
    out["require_costed"] = require_costed
    out["require_metrics"] = require_metrics
    out["artifacts"] = {
        "export": str(path),
        "validation": {"strict": strict, "valid": True},
    }
    for warning in report.get("warnings") or ():
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(out, indent=2, default=str))
    return 0


def stored_trials(
    data_root: Path | str, *, track: str | None = None, run_id: str | None = None
) -> list[dict[str, Any]]:
    """Read stored sweep trials; a missing runs database means no trials (no mkdir)."""
    database = paths_for(data_root).runs_db
    if not database.is_file():
        return []
    with closing(RunsDB(database)) as db:
        return db.list_trials(track=track, run_id=run_id)


def publish_trial_export(
    data_root: Path, best: Mapping[str, Any], *, candidate_id: str
) -> Path:
    """Write one strict bundle from a stored trial and its research metadata."""
    from hypervector.export.phase2 import export_candidate

    root = ensure_data_layout(data_root).root
    research = dict(best["research_meta"])
    meta = {"track": best["track"], "exported_from": "cli", **research}
    params = {"strategy": best["strategy"], "role": best["track"], **best["params"]}
    path = export_candidate(
        root / "exports",
        run_id=str(best["run_id"]),
        meta=meta,
        params=params,
        metrics={key: best[key] for key in TRIAL_METRICS},
        candidate_id=candidate_id,
        strict=True,
    )
    return path.resolve()
