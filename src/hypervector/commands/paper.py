"""Paper command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hypervector.commands.common import CommandRefused, _secrets_present, print_error
from hypervector.commands.exports import resolve_export, resolve_metalabel_bundle
from hypervector.infra import ensure_data_layout
from hypervector.nautilus.load_export import load_strategy_loadout
from hypervector.paper.fill_models import DEFAULT_MAX_BOOK_AGE_MS, FILL_MODEL_L2_WALK_V1
from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.paper.report import default_decisions_path, report_from_data_root
from hypervector.strategies.hypervelocity_contract import is_hypervelocity_strategy

if TYPE_CHECKING:
    from hypervector.paper.runner import PaperDaemonResult

DEFAULT_PREFERRED_FILL_MODEL = FILL_MODEL_L2_WALK_V1
DEFAULT_EXECUTION_MODE = "shadow"
ALLOWED_CLI_EXECUTION_MODES = frozenset({"shadow", "paper"})
METALABEL_ROOT_ENV = "HYPERVECTOR_METALABEL_ROOT"


class PaperArgumentsError(ValueError):
    """Conflicting or unsupported explicit paper command options."""


def start_paper_daemon(**options: Any) -> PaperDaemonResult:
    """Start the no-submit paper daemon; the runner (and its engines) load here.

    A module-level seam, so ``paper report`` never imports the runner and
    tests can replace the daemon.
    """
    from hypervector.paper.runner import start_paper_daemon as start

    return start(**options)


def resolve_metalabel_mode(**options: Any) -> str:
    """Resolve the metalabel mode; the model stack (pandas) loads only here."""
    from hypervector.paper.conviction import resolve_metalabel_mode as resolve

    return resolve(**options)


def cmd_paper_run(args: argparse.Namespace) -> int:
    """Run one explicitly configured no-submit paper/shadow session.

    A Hypervelocity bundle in shadow mode takes the Hypervelocity runtime lock,
    so it can neither run beside nor resume into another Hypervelocity shadow.
    """
    from hypervector.runtime_lock import RuntimeLockError

    path = resolve_export(args.export, args.data_root)
    bundle = (
        resolve_metalabel_bundle(args.metalabel_bundle, args.data_root)
        if getattr(args, "metalabel_bundle", None)
        else None
    )
    try:
        strategy_name = load_strategy_loadout(path, strict=True).strategy_name
        options = _paper_options(args, path, strategy_name)
    except PaperArgumentsError as exc:
        raise CommandRefused(f"paper run refused: {exc}") from exc
    hypervelocity_shadow = (
        is_hypervelocity_strategy(strategy_name)
        and options["execution_mode"] == "shadow"
    )
    try:
        ensure_data_layout(Path(args.data_root))
        with _runtime_guard(args, hypervelocity_shadow), _metalabel_root(bundle):
            result = start_paper_daemon(**options)
    except RuntimeLockError as exc:
        raise CommandRefused(f"paper run refused: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - session failures are technical (exit 1)
        if os.environ.get("HYPERVECTOR_DEBUG") == "1":
            raise
        return print_error(
            args, exc, error=f"paper run failed: {exc}", export_dir=str(path)
        )
    report = _paper_result(args, result, options)
    report["hypervelocity_runtime_lock"] = hypervelocity_shadow
    report["metalabel_bundle"] = str(bundle) if bundle is not None else None
    report["artifacts"] = {
        "export": str(path),
        "model": str(bundle) if bundle is not None else None,
        "paper": str(result.decisions_path),
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_paper_report(args: argparse.Namespace) -> int:
    """Summarize paper/shadow decisions JSONL (read-only; no venue orders).

    A missing decisions file (explicit or default) exits 1 rather than
    reporting an empty session.
    """
    root = Path(args.data_root)
    decisions = (
        Path(args.decisions)
        if getattr(args, "decisions", None)
        else default_decisions_path(root)
    )
    if not decisions.is_file():
        missing = FileNotFoundError(f"decisions file not found: {decisions}")
        return print_error(args, missing)
    last_n = int(getattr(args, "last", 5))
    try:
        report = report_from_data_root(
            root,
            decisions_path=decisions,
            last_n=last_n,
            run_id=getattr(args, "run_id", None),
            strategy=getattr(args, "strategy", None),
        )
    except ValueError as exc:
        return print_error(args, exc)
    print(json.dumps(report, indent=2, default=str))
    return 0


@contextmanager
def _metalabel_root(bundle: Path | None) -> Iterator[None]:
    """Point the session's model loader (env root first) at ``bundle``, then restore.

    The override lasts for this session only and never outlives it, so an
    in-process caller keeps its own environment.
    """
    if bundle is None:
        yield
        return
    previous = os.environ.get(METALABEL_ROOT_ENV)
    os.environ[METALABEL_ROOT_ENV] = str(bundle)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(METALABEL_ROOT_ENV, None)
        else:
            os.environ[METALABEL_ROOT_ENV] = previous


def _runtime_guard(
    args: argparse.Namespace, hypervelocity_shadow: bool
) -> AbstractContextManager[Any]:
    if not hypervelocity_shadow:
        return nullcontext()
    from hypervector.runtime_lock import hypervelocity_runtime_lock

    return hypervelocity_runtime_lock(Path(args.data_root))


def _paper_options(
    args: argparse.Namespace, path: Path, strategy_name: str
) -> dict[str, object]:
    """Prepare the daemon's typed runtime options from CLI arguments."""
    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    preferred = str(getattr(args, "preferred_fill_model", DEFAULT_PREFERRED_FILL_MODEL))
    max_book_age_ms = float(getattr(args, "max_book_age_ms", DEFAULT_MAX_BOOK_AGE_MS))
    metalabel_mode, metalabel_enabled, metalabel_filter, metalabel_min_p = (
        _paper_model_options(args, strategy_name)
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
        "sandbox_enabled": False,
        "fee_tier": int(getattr(args, "fee_tier", 0)),
        "stop_file": stop_file,
        "poll_interval_secs": float(getattr(args, "interval_seconds", 5.0)),
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
    args: argparse.Namespace, strategy_name: str
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
        "warmup": getattr(result, "warmup_provenance", None),
        "sandbox_enabled": False,
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
