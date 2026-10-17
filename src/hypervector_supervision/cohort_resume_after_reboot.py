"""Operator-invoked resume of the cohort supervisor after a host restart.

Dry run by default: every check and the planned actions are printed as JSON and
nothing is changed. With ``--yes`` plus both live-authority flags
(``--enabled --i-accept-live-risk``: the kickstart restarts the supervise agent,
which starts the armed backend), and only when every check passes, the
restart journal is moved into
``data/backups/bidirectional_cohort/reboot_hold_<UTC>/`` together with copies of
the tails of the supervisor event and alert journals, and the supervise agent is
restarted with ``launchctl kickstart -k``.

The checks:

* no STOP file (a STOP file is the durable operator stop and always wins);
* no live backend: neither the process-lock owner nor any other process runs
  the backend entry point;
* the hold is a signal stop (operator_signal_stop, operator_stop_grace_expired)
  or an unresolved supervisor session, the classes a host restart latches;
* the hold predates this boot: its boot-session stamp, when the journal has one,
  names another boot, and the newest backend event in the supervisor journal
  predates kern.boottime. An unresolved session must also be first seen in this
  boot, as the supervisor's own opt-in resume requires;
* a signal stop latched within HOST_RESTART_HOLD_WINDOW_SECONDS of the previous
  boot's shutdown record (for a journal without a latch time, its newest backend
  event stands in). A stop outside the window was an operator's: archive that
  journal by hand only if the stop is no longer wanted;
* the supervise agent is loaded and not disabled (``launchctl disable`` is a
  durable operator stop), so the kickstart can follow the archive.

This never signals the backend, never places or cancels an order, and never
reads secrets. The only process it touches is the supervise agent, through
launchd; its other launchctl calls only read.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from hypervector_supervision.cohort_supervisor_alerts import append_jsonl
from hypervector_supervision.cohort_supervisor_health import (
    _backend_command,
    process_is_backend,
    read_lock_pid,
)
from hypervector_supervision.cohort_supervisor_host import (
    BootIdentity,
    previous_shutdown_epoch,
    read_boot_identity,
)
from hypervector_supervision.cohort_supervisor_models import (
    BACKEND_MARKER,
    LAUNCHD_LABEL_PREFIX,
    REPOSITORY_ROOT,
    SupervisorPaths,
)
from hypervector_supervision.cohort_supervisor_restart_policy import (
    HOST_RESTART_HOLD_WINDOW_SECONDS,
)
from hypervector_supervision.cohort_supervisor_state import (
    SIGNAL_STOP_HOLDS,
    UNRESOLVED_SESSION_HOLD,
    restart_journal_path,
)

SUPERVISE_LABEL = f"{LAUNCHD_LABEL_PREFIX}supervise"
SUPERVISE_PLIST = Path.home() / "Library/LaunchAgents" / f"{SUPERVISE_LABEL}.plist"
LAUNCHCTL = "/bin/launchctl"
BACKUP_ROOT = REPOSITORY_ROOT / "data/backups/bidirectional_cohort"
TAIL_LINES = 200
_TAIL_BYTES = 1024 * 1024
# Supervisor events that mean a backend ran, or was about to. A supervisor that
# only read the hold at start writes none of these.
BACKEND_EVENTS = frozenset(
    {
        "backend_launched",
        "backend_exited",
        "backend_waiting_for_venue",
        "operator_stop_grace_expired",
        "adopted_running_backend",
        "adopted_backend_ended",
        "refused_backend_already_running",
        "hold_cleared_after_host_restart",
    }
)
EXIT_READY = 0
EXIT_REFUSED = 1
EXIT_ACTION_FAILED = 2
EXIT_AUTHORITY_REFUSED = 2  # the argparse usage code: nothing was checked or changed
AUTHORITY_REFUSAL = (
    "--yes kickstarts the supervise agent, which starts the armed backend; "
    "it requires both --enabled and --i-accept-live-risk"
)
# `launchctl print-disabled` prints `"<label>" => disabled|enabled` (older
# releases: `=> true|false`); a label it does not list is enabled.
_DISABLED_LINE = re.compile(r'^\s*"([^"]+)"\s*=>\s*(\S+)\s*$')
_DISABLED_VALUES = {"disabled": True, "true": True, "enabled": False, "false": False}


@dataclass(frozen=True)
class AgentState:
    """The supervise agent as launchd sees it; None where it could not be read."""

    loaded: bool | None
    disabled: bool | None


def read_agent_state(
    uid: int, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> AgentState:
    """Read, never change, whether the supervise agent is loaded and disabled."""

    def launchctl(*argv: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return run(
                [LAUNCHCTL, *argv],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    printed = launchctl("print", f"gui/{uid}/{SUPERVISE_LABEL}")
    disabled = launchctl("print-disabled", f"gui/{uid}")
    return AgentState(
        loaded=None if printed is None else printed.returncode == 0,
        disabled=(
            None
            if disabled is None or disabled.returncode != 0
            else parse_disabled(disabled.stdout, SUPERVISE_LABEL)
        ),
    )


def parse_disabled(output: str, label: str) -> bool | None:
    """Return whether ``print-disabled`` output disables ``label``; None if unclear."""
    for line in output.splitlines():
        match = _DISABLED_LINE.match(line)
        if match is not None and match.group(1) == label:
            return _DISABLED_VALUES.get(match.group(2).lower())
    return False


@dataclass
class Host:
    """Everything this helper reads from or does to the host, injectable."""

    boot_identity: Callable[[], BootIdentity] = read_boot_identity
    previous_shutdown: Callable[[float], float | None] = previous_shutdown_epoch
    is_backend: Callable[[int], bool] = process_is_backend
    backend_pids: Callable[[], list[int] | None] = lambda: _backend_pids()
    agent_state: Callable[[int], AgentState] = read_agent_state
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    now: Callable[[], float] = time.time
    uid: int = field(default_factory=os.getuid)


@dataclass(frozen=True)
class Check:
    """One named precondition; every one must pass before anything is changed."""

    name: str
    ok: bool
    detail: str


def evaluate(
    paths: SupervisorPaths, host: Host
) -> tuple[list[Check], dict[str, object]]:
    """Run every check without changing anything; return checks and evidence."""
    boot = host.boot_identity()
    journal_path = restart_journal_path(paths.events)
    evidence: dict[str, object] = {
        "restart_journal": str(journal_path),
        "boot_session": boot.session_uuid,
        "boot_time_utc": _utc(boot.boot_time_epoch),
    }
    checks = [
        Check("stop_file_absent", not paths.stop_file.exists(), str(paths.stop_file)),
        _lock_owner_check(paths, host),
        _backend_process_check(host),
    ]
    journal = _read_journal(journal_path)
    evidence["journal"] = journal
    checks.append(
        Check(
            "restart_journal_readable",
            journal is not None,
            "schema_version 1 object" if journal is not None else "missing or invalid",
        )
    )
    checks.append(
        Check(
            "boot_identity_known",
            boot.session_uuid is not None and boot.boot_time_epoch is not None,
            f"session={boot.session_uuid} boot_time={_utc(boot.boot_time_epoch)}",
        )
    )
    if journal is not None:
        checks.append(_hold_class_check(journal))
        checks.append(_stamp_check(journal, boot))
    last = _last_backend_event(paths.events)
    evidence["last_backend_event"] = last
    checks.append(_backend_event_check(last, boot.boot_time_epoch))
    shutdown = None
    if boot.boot_time_epoch is not None:
        shutdown = host.previous_shutdown(boot.boot_time_epoch)
        evidence["previous_shutdown_utc"] = _utc(shutdown)
    if journal is not None:
        checks.append(_shutdown_window_check(journal, last, shutdown, evidence))
    checks.extend(_agent_checks(host))
    return checks, evidence


def resume(
    paths: SupervisorPaths,
    host: Host,
    *,
    yes: bool,
    backup_root: Path = BACKUP_ROOT,
    out: Callable[[str], None] = print,
) -> int:
    """Check, then (only with ``yes`` and every check passing) archive and kickstart."""
    checks, evidence = evaluate(paths, host)
    ready = all(check.ok for check in checks)
    stamp = datetime.fromtimestamp(host.now(), UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = backup_root / f"reboot_hold_{stamp}"
    target = f"gui/{host.uid}/{SUPERVISE_LABEL}"
    report: dict[str, object] = {
        "verdict": "ready" if ready else "refused",
        "dry_run": not yes,
        "checks": [asdict(check) for check in checks],
        "evidence": evidence,
        "planned_actions": [
            f"move {restart_journal_path(paths.events)} into {archive}/",
            f"copy the last {TAIL_LINES} lines of {paths.events.name} and "
            f"{paths.alerts.name} into {archive}/",
            f"{LAUNCHCTL} kickstart -k {target}",
        ],
    }
    if not ready or not yes:
        out(json.dumps(report, indent=2, default=str))
        return EXIT_READY if ready else EXIT_REFUSED
    try:
        _archive(paths, archive, report)
    except (OSError, ValueError) as exc:
        report["verdict"] = "failed"
        report["failure"] = f"archive: {type(exc).__name__}: {exc}"
        out(json.dumps(report, indent=2, default=str))
        return EXIT_ACTION_FAILED
    report["archive"] = str(archive)
    try:
        kicked = host.run(
            [LAUNCHCTL, "kickstart", "-k", target],
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        code, detail = kicked.returncode, (kicked.stderr or "").strip()[:500]
    except (OSError, subprocess.SubprocessError) as exc:
        code, detail = -1, type(exc).__name__
    report["kickstart"] = {"target": target, "returncode": code, "detail": detail}
    if code != 0:
        report["verdict"] = "failed"
        report["failure"] = (
            "the restart journal is archived but the kickstart failed; "
            f"run: {LAUNCHCTL} kickstart -k {target}, or, if the agent is not "
            f"loaded: {LAUNCHCTL} bootstrap gui/{host.uid} {SUPERVISE_PLIST}"
        )
        out(json.dumps(report, indent=2, default=str))
        return EXIT_ACTION_FAILED
    report["verdict"] = "resumed"
    out(json.dumps(report, indent=2, default=str))
    return EXIT_READY


def _archive(paths: SupervisorPaths, archive: Path, report: dict[str, object]) -> None:
    """Move the journal aside after re-reading it; copy the journal tails."""
    journal_path = restart_journal_path(paths.events)
    checked = report["evidence"]["journal"]  # type: ignore[index]
    if _read_journal(journal_path) != checked:
        raise ValueError("restart journal changed after the checks; re-run")
    archive.mkdir(parents=True, exist_ok=False)
    for source in (paths.events, paths.alerts):
        if source.exists():
            (archive / f"{source.stem}_tail.jsonl").write_text(
                "".join(line + "\n" for line in _tail_lines(source, TAIL_LINES)),
                encoding="utf-8",
            )
    (archive / "resume_evidence.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
    )
    shutil.move(str(journal_path), str(archive / journal_path.name))
    try:
        append_jsonl(
            paths.events,
            {
                "event": "restart_journal_archived_after_host_restart",
                "at_utc": datetime.now(UTC).isoformat(),
                "archive": str(archive),
                "previous_reason": (checked or {}).get("hold_reason"),
            },
        )
    except OSError as exc:
        # The journal is already archived: a missing audit line must not strand
        # the book without its kickstart. The archive holds the same evidence.
        report["event_journal_failure"] = type(exc).__name__


def _lock_owner_check(paths: SupervisorPaths, host: Host) -> Check:
    pid = read_lock_pid(paths.process_lock)
    if pid is None:
        return Check("no_backend_lock_owner", True, "no process-lock PID")
    alive = host.is_backend(pid)
    return Check(
        "no_backend_lock_owner",
        not alive,
        f"pid {pid} {'is a live backend' if alive else 'is not a live backend'}",
    )


def _backend_process_check(host: Host) -> Check:
    pids = host.backend_pids()
    if pids is None:
        return Check("no_backend_process", False, "process table unreadable")
    return Check(
        "no_backend_process",
        not pids,
        f"backend pids {pids}" if pids else f"no {BACKEND_MARKER} process",
    )


def _hold_class_check(journal: dict[str, object]) -> Check:
    reason = journal.get("hold_reason")
    inferred = reason is None and journal.get("session_active") is True
    shown = UNRESOLVED_SESSION_HOLD + " (inferred)" if inferred else str(reason)
    ok = inferred or reason in SIGNAL_STOP_HOLDS or reason == UNRESOLVED_SESSION_HOLD
    return Check("hold_is_host_restart_class", ok, shown)


def _stamp_check(journal: dict[str, object], boot: BootIdentity) -> Check:
    """Compare the journal's boot-session stamp, when it has one, to this boot.

    An unresolved session is anchored to its launch: a supervisor that re-latched
    it after this boot stamped the hold, not the launch. As in the supervisor's
    own resume, a hold that is on disk must have been first persisted in this
    boot; one persisted in an earlier boot is a supervisor death that boot's
    operator was alerted to, not the end of the previous boot.
    """
    reason = journal.get("hold_reason")
    unresolved = reason in (None, UNRESOLVED_SESSION_HOLD)
    key = "launch_boot_session" if unresolved else "held_boot_session"
    stamped = journal.get(key)
    if stamped is None:
        return Check(
            "hold_latched_before_this_boot",
            True,
            f"no {key} (journal predates boot stamps); relying on the event journal",
        )
    ok = boot.session_uuid is not None and stamped != boot.session_uuid
    detail = f"{key}={stamped} this_boot={boot.session_uuid}"
    if unresolved and reason is not None:
        held = journal.get("held_boot_session")
        ok = ok and held == boot.session_uuid
        detail += f" held_boot_session={held}"
    held_at = journal.get("held_at_epoch")
    if (
        not unresolved
        and isinstance(held_at, (int, float))
        and boot.boot_time_epoch is not None
        and held_at >= boot.boot_time_epoch
    ):
        ok = False
    return Check("hold_latched_before_this_boot", ok, detail)


def _shutdown_window_check(
    journal: dict[str, object],
    last: dict[str, object] | None,
    shutdown: float | None,
    evidence: dict[str, object],
) -> Check:
    """Require a signal stop to have latched at the previous boot's shutdown.

    A signal stop is also what a plain ``launchctl bootout`` latches; one latched
    long before an unrelated reboot was an operator's stop and is refused.
    """
    name = "hold_latched_at_previous_shutdown"
    if journal.get("hold_reason") not in SIGNAL_STOP_HOLDS:
        return Check(name, True, "not a signal stop; no latch time to compare")
    held_at = journal.get("held_at_epoch")
    if isinstance(held_at, (int, float)) and not isinstance(held_at, bool):
        anchor, source = float(held_at), "held_at_epoch"
    else:
        anchor = None if last is None else _parse_utc(last.get("at_utc"))
        source = "last_backend_event"
    evidence["hold_anchor"] = source
    if shutdown is None:
        return Check(name, False, "previous boot's shutdown record unknown")
    if anchor is None:
        return Check(name, False, f"no {source} time")
    offset = anchor - shutdown
    evidence["hold_after_shutdown_seconds"] = round(offset, 3)
    ok = abs(offset) <= HOST_RESTART_HOLD_WINDOW_SECONDS
    detail = (
        f"{source} {offset:+.3f} s from the previous shutdown "
        f"(window {HOST_RESTART_HOLD_WINDOW_SECONDS:.0f} s)"
    )
    if not ok:
        detail += (
            "; an operator stop: archive the journal by hand only if it is "
            "no longer wanted"
        )
    return Check(name, ok, detail)


def _agent_checks(host: Host) -> list[Check]:
    """Refuse before the archive when the kickstart could not follow it."""
    state = host.agent_state(host.uid)
    target = f"gui/{host.uid}/{SUPERVISE_LABEL}"
    if state.disabled is None:
        disabled = Check("supervise_agent_not_disabled", False, "unreadable")
    elif state.disabled:
        disabled = Check(
            "supervise_agent_not_disabled",
            False,
            f"{target} is disabled: a durable operator stop",
        )
    else:
        disabled = Check("supervise_agent_not_disabled", True, f"{target} enabled")
    if state.loaded is None:
        loaded = Check("supervise_agent_loaded", False, "unreadable")
    elif state.loaded:
        loaded = Check("supervise_agent_loaded", True, f"{target} loaded")
    else:
        loaded = Check(
            "supervise_agent_loaded",
            False,
            f"{target} not loaded; load it (it starts held), then re-run: "
            f"{LAUNCHCTL} bootstrap gui/{host.uid} {SUPERVISE_PLIST}",
        )
    return [disabled, loaded]


def _backend_event_check(
    last: dict[str, object] | None, boot_time: float | None
) -> Check:
    if last is None:
        return Check(
            "last_backend_event_predates_boot", False, "no backend event found"
        )
    stamp = _parse_utc(last.get("at_utc"))
    ok = stamp is not None and boot_time is not None and stamp < boot_time
    return Check(
        "last_backend_event_predates_boot",
        ok,
        f"{last.get('event')} at {last.get('at_utc')}; boot {_utc(boot_time)}",
    )


def _read_journal(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return None
    return payload


def _last_backend_event(events: Path) -> dict[str, object] | None:
    for line in reversed(_tail_lines(events, None)):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("event") in BACKEND_EVENTS:
            return row
    return None


def _tail_lines(path: Path, limit: int | None) -> list[str]:
    """Return the last complete lines within the final megabyte of a journal."""
    try:
        with path.open("rb") as handle:
            end = handle.seek(0, os.SEEK_END)
            start = max(0, end - _TAIL_BYTES)
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # the first line may be cut
    lines = [line for line in lines if line.strip()]
    return lines if limit is None else lines[-limit:]


def _backend_pids() -> list[int] | None:
    """Return every process running the backend entry point, or None if unknown."""
    try:
        result = subprocess.run(
            ["/bin/ps", "-Ao", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return backend_pids_from_ps(result.stdout, own_pid=os.getpid())


def backend_pids_from_ps(output: str, *, own_pid: int) -> list[int]:
    """Parse ``ps -Ao pid=,command=`` output for the backend entry point.

    A process is the backend when its Python entry point is the backend script or
    the packaged ``-m`` module, exactly as the supervisor's own health probe
    decides; incidental argv text (an editor, a grep) does not count.
    """
    pids: list[int] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit() or int(parts[0]) == own_pid:
            continue
        if _backend_command(parts[1:]):
            pids.append(int(parts[0]))
    return pids


def _parse_utc(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp.timestamp() if stamp.tzinfo is not None else None


def _utc(epoch: float | None) -> str | None:
    return None if epoch is None else datetime.fromtimestamp(epoch, UTC).isoformat()


def build_parser() -> argparse.ArgumentParser:
    """Build the command line."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--yes",
        action="store_true",
        help="archive the restart journal and kickstart the supervise agent "
        "(default: dry run; requires --enabled and --i-accept-live-risk)",
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="first of the two live-authority flags --yes requires",
    )
    parser.add_argument(
        "--i-accept-live-risk",
        action="store_true",
        help="second of the two live-authority flags --yes requires",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Check the host after a reboot and, with --yes, resume supervision."""
    args = build_parser().parse_args(argv)
    if args.yes and not (args.enabled and args.i_accept_live_risk):
        print(f"resume refused: {AUTHORITY_REFUSAL}", file=sys.stderr)
        return EXIT_AUTHORITY_REFUSED
    return resume(SupervisorPaths(), Host(), yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
