"""Fail-closed process supervision and read-only cohort monitoring CLI."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

from cohort_supervisor_models import (
    SupervisorPaths as SupervisorPaths,
    HealthThresholds as HealthThresholds,
    RestartPolicy as RestartPolicy,
    HealthReport as HealthReport,
    RestartDecision as RestartDecision,
    REPOSITORY_ROOT as REPOSITORY_ROOT,
    RUNTIME_ROOT as RUNTIME_ROOT,
    WEBHOOK_ENV as WEBHOOK_ENV,
    DEADMAN_ENV as DEADMAN_ENV,
    EXIT_START_REFUSED as EXIT_START_REFUSED,
    require_positive,
)
from cohort_supervisor_health import (
    file_age_seconds as file_age_seconds,
    free_disk_gib as free_disk_gib,
    read_lock_pid as read_lock_pid,
    process_is_backend as process_is_backend,
    hip3_fee_regime as hip3_fee_regime,
    maximum_hip3_fill_fee_bps as maximum_hip3_fill_fee_bps,
    evaluate_health as evaluate_health,
)
from cohort_supervisor_alerts import (
    AlertSink as AlertSink,
    JsonlSink as JsonlSink,
    MacNotificationSink as MacNotificationSink,
    WebhookSink as WebhookSink,
    Alerter as Alerter,
    build_sinks as build_sinks,
    ping_deadman as ping_deadman,
    append_jsonl as append_jsonl,
)
from cohort_supervisor_state import (
    RestartJournal as RestartJournal,
    supervisor_lock as supervisor_lock,
)
from cohort_supervisor_venue_wait import backend_venue_wait
from cohort_supervisor_runtime import (
    decide_restart as decide_restart,
    _StopFlag as _StopFlag,
    SupervisorRuntime as SupervisorRuntime,
    wait_for_adopted_exit as wait_for_adopted_exit,
    supervise as supervise,
    _watch_child as _watch_child,
    _hold as _hold,
    _terminate_group as _terminate_group,
    _interruptible_sleep as _interruptible_sleep,
    _event as _event,
)


def launchd_plist(kind: str, arguments: Sequence[str], *, python: Path) -> bytes:
    """Return a LaunchAgent that keeps this supervisor alive across logins.

    ``KeepAlive.SuccessfulExit = false`` relaunches a crashed supervisor but not
    one that returned 0 after an operator stop, so an operator stop stays stopped.
    """
    label = f"local.hypervector.cohort.{kind}"
    log = str(REPOSITORY_ROOT / RUNTIME_ROOT / f"supervisor_{kind}.launchd.log")
    return plistlib.dumps(
        {
            "Label": label,
            "ProgramArguments": [
                str(python),
                str(Path(__file__).resolve()),
                *arguments,
            ],
            "WorkingDirectory": str(REPOSITORY_ROOT),
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 30,
            # This host caps requested values at 60 seconds. The child gets 30
            # seconds, and its stop is persisted before waiting for termination.
            "ExitTimeOut": 60,
            "ProcessType": "Interactive",
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        }
    )


def _add_health_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = HealthThresholds()
    parser.add_argument(
        "--heartbeat-seconds", type=float, default=defaults.heartbeat_seconds
    )
    parser.add_argument(
        "--checkpoint-seconds", type=float, default=defaults.checkpoint_seconds
    )
    parser.add_argument("--roster-seconds", type=float, default=defaults.roster_seconds)
    parser.add_argument("--hip3-fee-bps", type=float, default=defaults.hip3_fee_bps)
    parser.add_argument(
        "--free-disk-gib", type=float, default=defaults.minimum_free_disk_gib
    )
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--reminder-seconds", type=float, default=1_800.0)
    parser.add_argument("--alert-minimum-interval-seconds", type=float, default=60.0)
    parser.add_argument(
        "--startup-grace-seconds",
        type=float,
        default=RestartPolicy().startup_grace_seconds,
        help="suppress heartbeat staleness while the backend is this young",
    )
    parser.add_argument("--no-notifications", action="store_true")


def _thresholds(args: argparse.Namespace) -> HealthThresholds:
    return HealthThresholds(
        heartbeat_seconds=args.heartbeat_seconds,
        checkpoint_seconds=args.checkpoint_seconds,
        roster_seconds=args.roster_seconds,
        hip3_fee_bps=args.hip3_fee_bps,
        minimum_free_disk_gib=args.free_disk_gib,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the supervisor command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="one-shot health report")
    _add_health_arguments(status)

    watch = commands.add_parser("watch", help="read-only watchdog")
    _add_health_arguments(watch)

    owned = commands.add_parser("supervise", help="own and restart the backend")
    _add_health_arguments(owned)
    _add_supervise_arguments(owned)

    plist = commands.add_parser("print-launchd", help="emit a LaunchAgent plist")
    plist.add_argument("--kind", choices=("watch", "supervise"), required=True)
    plist.add_argument(
        "--python", type=Path, default=REPOSITORY_ROOT / ".venv/bin/python"
    )
    plist.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="-- followed by the arguments for that subcommand",
    )
    return parser


def _add_supervise_arguments(parser: argparse.ArgumentParser) -> None:
    defaults = RestartPolicy()
    parser.add_argument(
        "--maximum-restarts", type=int, default=defaults.maximum_restarts
    )
    parser.add_argument("--window-seconds", type=float, default=defaults.window_seconds)
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=defaults.initial_backoff_seconds,
    )
    parser.add_argument(
        "--maximum-backoff-seconds",
        type=float,
        default=defaults.maximum_backoff_seconds,
    )
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="watch an already-running backend and take over after it ends",
    )
    parser.add_argument(
        "--adopted-exit-policy",
        choices=("hold", "restart"),
        default="hold",
        help="an adopted process has no observable exit code; default is to hold",
    )
    parser.add_argument(
        "--allow-idle-sleep",
        action="store_true",
        help="do not hold a caffeinate idle-sleep assertion",
    )
    parser.add_argument(
        "child",
        nargs=argparse.REMAINDER,
        help="-- followed by the exact backend command to run",
    )


def _strip_separator(values: Sequence[str]) -> list[str]:
    return list(values[1:]) if values and values[0] == "--" else list(values)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand from the repository root."""
    args = build_parser().parse_args(argv)
    os.chdir(REPOSITORY_ROOT)
    paths = SupervisorPaths()

    if args.command == "print-launchd":
        forwarded = [args.kind, *_strip_separator(args.arguments)]
        sys.stdout.buffer.write(launchd_plist(args.kind, forwarded, python=args.python))
        return 0

    thresholds = _thresholds(args)
    if args.command == "status":
        report = evaluate_health(paths, thresholds, now=time.time())
        print(json.dumps({**asdict(report), "healthy": report.healthy}, indent=2))
        return 0 if report.healthy else 1

    stop = _StopFlag()
    stop.install()
    if args.command == "watch":
        # The watch agent keeps its own journals: both agents dedup per process, so
        # a shared journal delivered every alert twice.
        paths = replace(
            paths,
            alerts=paths.alerts.with_name("supervisor_watch_alerts.jsonl"),
            events=paths.events.with_name("supervisor_watch_events.jsonl"),
        )
    alerter = Alerter(
        build_sinks(paths, notifications=not args.no_notifications),
        reminder_seconds=args.reminder_seconds,
        minimum_interval_seconds=args.alert_minimum_interval_seconds,
    )
    deadman_url = os.environ.get(DEADMAN_ENV, "").strip() or None

    require_positive(args.interval, "interval")
    require_positive(args.reminder_seconds, "reminder_seconds")
    if args.command == "watch":
        return _run_watch(args, paths, thresholds, alerter, stop, deadman_url)
    return _run_owned(args, paths, thresholds, alerter, stop, deadman_url)


def _run_watch(
    args: argparse.Namespace,
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    alerter: Alerter,
    stop: _StopFlag,
    deadman_url: str | None,
) -> int:
    _event(paths, "watchdog_started")
    while not stop.requested:
        now = time.time()
        report = evaluate_health(
            paths,
            thresholds,
            now=now,
            heartbeat_required=not _backend_is_warming(
                paths, now, args.startup_grace_seconds
            ),
        )
        alerter.observe(report, now)
        # Host liveness is not data freshness: gating this on full health let one
        # stale research file disable the only external outage detector.
        ping_deadman(deadman_url)
        _interruptible_sleep(args.interval, stop, SupervisorRuntime())
    return 0


def _backend_is_warming(
    paths: SupervisorPaths, now: float, startup_grace_seconds: float
) -> bool:
    """Report whether the owned backend is still inside its startup grace.

    The lock file is written at backend startup, so its age anchors the same grace
    the supervise agent applies. Without it the watch agent alerted
    ``backend_heartbeat_stale`` on every legitimate restart. A backend waiting for
    the venue before its start is warming whatever its lock's age, as the
    supervise agent treats it; it refreshes the lock once the wait returns, so
    the grace then runs from the moment the start proceeds.
    """
    pid = read_lock_pid(paths.process_lock)
    waiting = pid is not None and (
        backend_venue_wait(paths.process_lock, pid, now) is not None
    )
    if waiting:
        return True
    age = file_age_seconds(paths.process_lock, now)
    return age is not None and age < startup_grace_seconds


def _run_owned(
    args: argparse.Namespace,
    paths: SupervisorPaths,
    thresholds: HealthThresholds,
    alerter: Alerter,
    stop: _StopFlag,
    deadman_url: str | None,
) -> int:
    command = _strip_separator(args.child)
    if not command:
        print("supervise requires the backend command after --", file=sys.stderr)
        return EXIT_START_REFUSED
    caffeinate = shutil.which("caffeinate")
    if caffeinate and not args.allow_idle_sleep:
        subprocess.Popen(  # noqa: S603
            [caffeinate, "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    policy = RestartPolicy(
        maximum_restarts=args.maximum_restarts,
        window_seconds=args.window_seconds,
        initial_backoff_seconds=args.initial_backoff_seconds,
        maximum_backoff_seconds=args.maximum_backoff_seconds,
        startup_grace_seconds=args.startup_grace_seconds,
    )
    return supervise(
        command,
        paths,
        thresholds,
        policy,
        alerter,
        interval=args.interval,
        adopt=args.adopt,
        adopted_exit_policy=args.adopted_exit_policy,
        deadman_url=deadman_url,
        stop=stop,
    )


if __name__ == "__main__":
    raise SystemExit(main())
