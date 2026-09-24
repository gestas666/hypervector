"""Pure fail-closed child restart decisions."""

from __future__ import annotations

from collections.abc import Sequence
from cohort_supervisor_models import RestartDecision, RestartPolicy, EXIT_OPERATOR_STOP, EXIT_START_REFUSED

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
