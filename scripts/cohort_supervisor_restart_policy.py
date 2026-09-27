"""Pure fail-closed child restart decisions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from cohort_supervisor_host import BootIdentity
from cohort_supervisor_models import RestartDecision, RestartPolicy, EXIT_OPERATOR_STOP, EXIT_START_REFUSED
from cohort_supervisor_state import (
    SIGNAL_STOP_HOLDS,
    UNRESOLVED_SESSION_HOLD,
    RestartJournal,
)

# The backend's exit once its account stayed unreconciled past the wall-clock
# bound. That is venue unavailability, not a backend crash: the relaunch waits in
# process for the venue before any bundle or replay, and the backend can only
# exit this way again after another full bound of blindness, so the relaunch is
# not charged to the crash budget. Must equal EXIT_DEGRADED_BLINDNESS in
# scripts/multi_asset_bidirectional_live.py.
EXIT_DEGRADED_BLINDNESS = 4


def decide_restart(
    exit_code: int | None,
    *,
    stop_file_present: bool,
    restart_times: Sequence[float],
    policy: RestartPolicy,
    now: float,
) -> RestartDecision:
    """Apply the fail-closed table in the module docstring.

    ``exit_code`` is ``None`` when the process was adopted rather than owned, so
    its exit status is unobservable; that case is decided by the caller's
    explicit ``--adopted-exit-policy`` before this function is consulted.
    """
    if exit_code == EXIT_OPERATOR_STOP:
        return RestartDecision("stop", "clean_exit_operator_stop_or_bounded_run")
    if stop_file_present:
        return RestartDecision("hold", "operator_stop_file_present")
    if exit_code == EXIT_START_REFUSED:
        return RestartDecision("hold", "live_start_refused_fail_closed")
    if exit_code == EXIT_DEGRADED_BLINDNESS:
        return RestartDecision(
            "restart", "degraded_blindness_uncharged", policy.initial_backoff_seconds
        )
    recent = [stamp for stamp in restart_times if now - stamp <= policy.window_seconds]
    if len(recent) >= policy.maximum_restarts:
        return RestartDecision("give_up", "restart_budget_exhausted")
    delay = min(
        policy.maximum_backoff_seconds,
        policy.initial_backoff_seconds * (2.0 ** len(recent)),
    )
    return RestartDecision("restart", "unexpected_exit", delay)


def charges_restart_budget(exit_code: int | None) -> bool:
    """Report whether relaunching after this exit spends the crash budget."""
    return exit_code != EXIT_DEGRADED_BLINDNESS


# The previous boot's SHUTDOWN_TIME record is written as userspace shutdown
# starts; launchd then sends SIGTERM, and the latch is re-stamped when the child
# exits or its 30 s grace expires, all inside the 60 s ExitTimeOut
# (2026-09-26: record 22:49:07.10Z, final latch 22:49:40Z, 33 s after). The
# window is two-sided because the latch normally follows the record.
HOST_RESTART_HOLD_WINDOW_SECONDS = 180.0


@dataclass(frozen=True)
class HostRestartResume:
    """Whether a start-time hold may be released because a host restart latched it."""

    resume: bool
    reason: str
    evidence: dict[str, object] = field(default_factory=dict)


def decide_host_restart_resume(
    journal: RestartJournal,
    boot: BootIdentity,
    *,
    previous_shutdown: Callable[[float], float | None],
    stop_file_present: bool,
    backend_alive: bool,
    free_disk_gib: float | None,
    minimum_free_disk_gib: float,
    window_seconds: float = HOST_RESTART_HOLD_WINDOW_SECONDS,
) -> HostRestartResume:
    """Release only a hold that the previous boot's shutdown latched.

    Every check must pass; any value that cannot be read keeps the hold:

    * the hold is a signal stop (operator_signal_stop, operator_stop_grace_expired)
      or an unresolved supervisor session;
    * no STOP file, no live backend owning the process lock, and free disk at or
      above the launch floor;
    * it was latched in a different boot session than this one, so every process
      of that session, the backend included, is gone;
    * a signal stop latched within ``window_seconds`` of the previous boot's
      shutdown record. A plain ``launchctl bootout`` long before an unrelated
      reboot therefore stays an operator stop; a reboot that ended without a
      shutdown record (power loss, panic) keeps a signal hold;
    * an unresolved session (its supervisor never wrote the session's end: power
      loss, panic, SIGKILL) involves no operator stop and has no latch time of
      its own. Its launch's boot session must differ from this one, and its
      newest launch must predate this boot. The hold must also be first seen in
      this boot: either inferred now, or persisted by a supervisor of this boot
      (which stamped the hold, not the launch). One already persisted in an
      earlier boot was a supervisor death that boot's operator was alerted to
      (a SIGKILL relaunched in the same boot, or a hold left standing), not
      the end of the previous boot.

    ``previous_shutdown`` is called at most once, only after every cheaper check
    has passed.
    """
    reason = journal.hold_reason
    evidence: dict[str, object] = {
        "previous_reason": reason,
        "hold_inferred_from_active_session": journal.hold_inferred_from_active_session,
        "held_at_epoch": journal.held_at_epoch,
        "held_boot_session": journal.held_boot_session,
        "launch_boot_session": journal.launch_boot_session,
        "boot_session": boot.session_uuid,
        "boot_time_epoch": boot.boot_time_epoch,
        "free_disk_gib": free_disk_gib,
    }

    def keep(why: str) -> HostRestartResume:
        return HostRestartResume(False, why, evidence)

    if reason is None:
        return keep("no_hold")
    if reason not in SIGNAL_STOP_HOLDS and reason != UNRESOLVED_SESSION_HOLD:
        return keep("hold_not_host_restart_class")
    if stop_file_present:
        return keep("operator_stop_file_present")
    if backend_alive:
        return keep("backend_process_alive")
    if free_disk_gib is None or free_disk_gib < minimum_free_disk_gib:
        return keep("insufficient_free_disk")
    boot_time = boot.boot_time_epoch
    if boot.session_uuid is None or boot_time is None:
        return keep("boot_identity_unknown")
    unresolved = reason == UNRESOLVED_SESSION_HOLD
    latched_in = journal.launch_boot_session if unresolved else journal.held_boot_session
    if latched_in is None:
        return keep("hold_not_stamped_with_boot_session")
    if latched_in == boot.session_uuid:
        return keep("hold_latched_in_this_boot")
    if unresolved:
        if not journal.hold_inferred_from_active_session:
            if journal.held_boot_session is None:
                return keep("hold_not_stamped_with_boot_session")
            if journal.held_boot_session != boot.session_uuid:
                return keep("unresolved_session_held_in_an_earlier_boot")
        evidence["newest_launch_epoch"] = max(journal.launch_times, default=None)
        if not journal.launch_times:
            return keep("session_launch_time_unknown")
        if max(journal.launch_times) >= boot_time:
            return keep("session_launch_not_before_this_boot")
        return HostRestartResume(True, "unresolved_session_of_previous_boot", evidence)
    held_at = journal.held_at_epoch
    if held_at is None:
        return keep("hold_not_stamped_with_time")
    if held_at >= boot_time:
        return keep("hold_not_before_this_boot")
    shutdown = previous_shutdown(boot_time)
    evidence["previous_shutdown_epoch"] = shutdown
    if shutdown is None:
        return keep("previous_shutdown_unknown")
    evidence["hold_after_shutdown_seconds"] = round(held_at - shutdown, 3)
    if abs(held_at - shutdown) > window_seconds:
        return keep("hold_outside_shutdown_window")
    return HostRestartResume(True, "latched_by_previous_boot_shutdown", evidence)
