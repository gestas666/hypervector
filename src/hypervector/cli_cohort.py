"""First-class CLI boundary for the shared bidirectional live cohort."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPOSITORY_ROOT / "scripts"
_DEFAULT_LEDGER_ROOT = Path("data/live/bidirectional_cohort")


def register_cohort_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register fail-closed cohort launcher, backend, and audit commands."""
    _register_tui(subparsers)
    _register_live(subparsers)
    _register_audit(subparsers)
    _register_audit_delta(subparsers)
    _register_research_import(subparsers)


def cohort_command(args: argparse.Namespace) -> tuple[str, ...]:
    """Resolve one cohort command without executing or weakening its authority."""
    command = str(args.command)
    if command == "cohort-tui":
        return _tui_command(args)
    if command == "cohort-live":
        return _live_command(args)
    if command == "cohort-live-audit":
        return _audit_command(args)
    if command == "cohort-live-audit-delta":
        return _audit_delta_command(args)
    if command == "cohort-research-import":
        return _research_import_command(args)
    raise ValueError(f"unsupported cohort command: {command}")


def run_cohort_command(args: argparse.Namespace) -> int:
    """Execute the resolved project script and propagate its return code."""
    try:
        command = cohort_command(args)
    except ValueError as exc:
        print(f"{args.command} refused: {exc}", file=sys.stderr)
        return 2
    return subprocess.run(command, check=False).returncode


def _register_tui(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "cohort-tui",
        help="Attach to or explicitly launch the bidirectional cohort TUI",
    )
    parser.add_argument(
        "--mode", choices=("observe", "monitor", "live"), default="observe"
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--backtest-lab-root", type=Path)
    parser.add_argument("--tui-bin", type=Path)
    parser.add_argument("--tui-bin-sha256")
    parser.add_argument(
        "--independent-monitor", action="store_true",
        help="open an updated read-only monitor alongside an existing cohort session",
    )
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--accounting-epoch-bundle", type=Path)
    parser.add_argument("--resume-transition-drain", action="store_true")
    parser.add_argument("--refresh-ms", type=int)
    parser.add_argument("--startup-timeout-seconds", type=float)
    parser.set_defaults(func=run_cohort_command)


def _register_live(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "cohort-live",
        help="Run the explicitly double-armed multi-asset live backend",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--backtest-lab-root", type=Path)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--i-accept-live-risk", action="store_true")
    parser.add_argument("--resume-transition-drain", action="store_true")
    parser.add_argument("--max-polls", type=int)
    parser.set_defaults(func=run_cohort_command)


def _register_audit(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "cohort-live-audit",
        help="Publish immutable report-only evidence for one cohort run",
    )
    parser.add_argument("--ledger-root", type=Path, default=_DEFAULT_LEDGER_ROOT)
    parser.add_argument("--run-id")
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--out", type=Path)
    destination.add_argument("--out-dir", type=Path)
    parser.set_defaults(func=run_cohort_command)


def _register_research_import(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "cohort-research-import",
        help="Incrementally import append-only cohort journals into DuckDB",
    )
    parser.add_argument("--ledger-root", type=Path, default=_DEFAULT_LEDGER_ROOT)
    parser.add_argument("--database", type=Path)
    parser.set_defaults(func=run_cohort_command)


def _register_audit_delta(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "cohort-live-audit-delta",
        help="Compare two immutable cohort live-audit prefixes",
    )
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(func=run_cohort_command)


def _tui_command(args: argparse.Namespace) -> tuple[str, ...]:
    mode = str(args.mode)
    _require_live_authority(args, live=mode == "live")
    if args.independent_monitor and mode != "monitor":
        raise ValueError("independent monitor requires monitor mode")
    command = _base_command(
        "cohort_independent_monitor.py" if args.independent_monitor
        else "multi_asset_bidirectional_canary_tui.py"
    )
    command += _optional_path("--config", args.config)
    command += _optional_path("--backtest-lab-root", args.backtest_lab_root)
    command += _optional_path("--tui-bin", args.tui_bin)
    command += _optional_value("--tui-bin-sha256", args.tui_bin_sha256)
    command += _optional_path(
        "--accounting-epoch-bundle",
        args.accounting_epoch_bundle,
    )
    command += _optional_value("--refresh-ms", args.refresh_ms)
    command += _optional_value(
        "--startup-timeout-seconds", args.startup_timeout_seconds
    )
    command += ("--mode", mode)
    if mode == "live":
        command += ("--enabled", "--i-accept-live-risk")
        if args.resume_transition_drain:
            command += ("--resume-transition-drain",)
    return command


def _live_command(args: argparse.Namespace) -> tuple[str, ...]:
    _require_live_authority(args, live=True)
    command = _base_command("multi_asset_bidirectional_live.py")
    command += _optional_path("--config", args.config)
    command += _optional_path("--backtest-lab-root", args.backtest_lab_root)
    command += ("--enabled", "--i-accept-live-risk")
    if args.resume_transition_drain:
        command += ("--resume-transition-drain",)
    command += _optional_value("--max-polls", args.max_polls)
    return command


def _audit_command(args: argparse.Namespace) -> tuple[str, ...]:
    command = _base_command("multi_asset_bidirectional_live_audit.py")
    command += ("--ledger-root", str(args.ledger_root))
    command += _optional_value("--run-id", args.run_id)
    if args.out is not None:
        return command + ("--out", str(args.out))
    return command + ("--out-dir", str(args.out_dir))


def _research_import_command(args: argparse.Namespace) -> tuple[str, ...]:
    command = _base_command("multi_asset_bidirectional_research_import.py")
    command += ("--ledger-root", str(args.ledger_root))
    return command + _optional_path("--database", args.database)


def _audit_delta_command(args: argparse.Namespace) -> tuple[str, ...]:
    command = _base_command("cohort_live_audit_delta.py")
    return command + (
        "--before",
        str(args.before),
        "--after",
        str(args.after),
        "--out",
        str(args.out),
    )


def _require_live_authority(args: argparse.Namespace, *, live: bool) -> None:
    enabled = bool(args.enabled)
    accepted = bool(args.i_accept_live_risk)
    if live and not (enabled and accepted):
        raise ValueError("live cohort requires both --enabled and --i-accept-live-risk")
    if not live and (enabled or accepted):
        raise ValueError("non-live cohort mode cannot accept live authority flags")
    if not live and bool(args.resume_transition_drain):
        raise ValueError("non-live cohort mode cannot resume a transition drain")


def _base_command(script: str) -> tuple[str, ...]:
    return (sys.executable, str(_SCRIPTS / script))


def _optional_path(flag: str, value: Path | None) -> tuple[str, ...]:
    return () if value is None else (flag, str(value))


def _optional_value(flag: str, value: object | None) -> tuple[str, ...]:
    return () if value is None else (flag, str(value))
