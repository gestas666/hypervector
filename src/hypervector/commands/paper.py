"""Paper command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.conviction import resolve_metalabel_mode
from hypervector.paper.fill_models import DEFAULT_MAX_BOOK_AGE_MS
from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.paper.report import report_from_data_root
from hypervector.paper.runner import PaperDaemonResult, start_paper_daemon
from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy
from hypervector.commands.common import _ensure_root, _secrets_present
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1

DEFAULT_PREFERRED_FILL_MODEL = FILL_MODEL_L2_WALK_V1
DEFAULT_EXECUTION_MODE = "shadow"
ALLOWED_CLI_EXECUTION_MODES = frozenset({"shadow", "paper"})


def cmd_paper_run(args: argparse.Namespace) -> int:
    """Run one explicitly configured no-submit paper/shadow session."""
    path = Path(args.path)
    if not path.is_dir():
        print(f"export path not found: {path}", file=sys.stderr)
        return 1
    try:
        options = _paper_options(args, path)
        _ensure_root(args)
        result = start_paper_daemon(**options)
    except PaperArgumentsError as exc:
        print(f"paper-run refused: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"paper-run failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(_paper_result(args, result, options), indent=2, default=str))
    return 0


def cmd_paper_report(args: argparse.Namespace) -> int:
    """Summarize paper/shadow decisions JSONL (read-only; no venue orders)."""
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


class PaperArgumentsError(ValueError):
    """Conflicting or unsupported explicit paper command options."""


def _paper_options(args: argparse.Namespace, path: Path) -> dict[str, object]:
    """Prepare the daemon's typed runtime options from CLI arguments."""
    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    preferred = str(getattr(args, "preferred_fill_model", DEFAULT_PREFERRED_FILL_MODEL))
    max_book_age_ms = float(getattr(args, "max_book_age_ms", DEFAULT_MAX_BOOK_AGE_MS))
    metalabel_mode, metalabel_enabled, metalabel_filter, metalabel_min_p = (
        _paper_model_options(args, path)
    )
    execution_mode = str(getattr(args, "mode", DEFAULT_EXECUTION_MODE)).lower().strip()
    if execution_mode not in ALLOWED_CLI_EXECUTION_MODES:
        raise PaperArgumentsError(
            f"invalid --mode {execution_mode!r}; choose shadow|paper"
        )
    return {
        "export_dir": path,
        "data_root": Path(args.data_root),
        "conviction": float(args.conviction),
        "sandbox_enabled": bool(getattr(args, "sandbox", False)),
        "fee_tier": int(getattr(args, "fee_tier", 0)),
        "stop_file": stop_file,
        "poll_interval_secs": float(getattr(args, "poll_interval", 5.0)),
        "max_live_bars": int(args.max_live_bars)
        if getattr(args, "max_live_bars", None) is not None
        else None,
        "lookback_days": int(args.lookback)
        if getattr(args, "lookback", None)
        else None,
        "preferred_fill_model": preferred,
        "max_book_age_ms": max_book_age_ms,
        "metalabel_enabled": metalabel_enabled,
        "metalabel_min_p": metalabel_min_p,
        "metalabel_filter": metalabel_filter,
        "metalabel_mode": metalabel_mode,
        "execution_mode": execution_mode,
    }


def _paper_model_options(
    args: argparse.Namespace, path: Path
) -> tuple[str, bool, bool, float]:
    """Preserve explicit model policy and Hypervelocity annotation-only authority."""
    legacy_metalabel = getattr(args, "metalabel", None)
    metalabel_min_p = float(getattr(args, "metalabel_min_p", 0.5))
    metalabel_filter = bool(getattr(args, "metalabel_filter", True))
    requested_metalabel_mode = getattr(args, "metalabel_mode", None)
    if requested_metalabel_mode not in (None, "off") and legacy_metalabel is False:
        raise PaperArgumentsError(
            "--no-metalabel conflicts with an active --metalabel-mode"
        )
    if requested_metalabel_mode == "off" and legacy_metalabel is True:
        raise PaperArgumentsError("--metalabel conflicts with --metalabel-mode off")
    metalabel_mode = resolve_metalabel_mode(
        enabled=bool(legacy_metalabel),
        filter_entries=metalabel_filter,
        requested=requested_metalabel_mode,
    )
    strategy_name = load_strategy_loadout(path, strict=True).strategy_name
    if is_hypervelocity_strategy(strategy_name) and metalabel_mode in (
        "scale",
        "filter",
    ):
        metalabel_mode = "observe"
        metalabel_filter = False
    metalabel_enabled = metalabel_mode != "off"
    return metalabel_mode, metalabel_enabled, metalabel_filter, metalabel_min_p


def _paper_result(
    args: argparse.Namespace, result: PaperDaemonResult, options: dict[str, object]
) -> dict[str, object]:
    """Format the daemon's measured result and effective no-submit policy."""
    return {
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
        "preferred_fill_model": options["preferred_fill_model"],
        "max_book_age_ms": options["max_book_age_ms"],
        "metalabel_enabled": options["metalabel_enabled"],
        "metalabel_mode": options["metalabel_mode"],
        "metalabel_filter": options["metalabel_filter"]
        if options["metalabel_enabled"]
        else False,
        "metalabel_min_p": options["metalabel_min_p"]
        if options["metalabel_enabled"]
        else None,
        "secrets_present": _secrets_present(),
        "no_submit": True,
        "network": NETWORK_MAINNET,
    }
