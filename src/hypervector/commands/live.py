"""Live command handlers and cohort preflights; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from hypervector.commands.common import CommandRefused, _ensure_root, print_error
from hypervector.paper.order_intent import NETWORK_MAINNET

if TYPE_CHECKING:
    from hypervector.live.policy import LivePolicy
    from hypervector.live.runner import LiveDaemonResult

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"


def preflight_start(args: argparse.Namespace) -> None:
    """Load the profile in observe mode and check provider dependencies before exec."""
    from hypervector.live.cohort_process_commands import (
        require_live_provider_dependencies,
    )
    from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

    try:
        config = load_multi_asset_live_config(args.config, mode="observe")
        require_live_provider_dependencies(config)
    except (OSError, ValueError) as exc:
        raise CommandRefused(f"live start refused: {exc}") from exc


def preflight_audit(args: argparse.Namespace) -> None:
    """A current-run audit needs the run it is about."""
    if args.history_scope == "current-run" and not args.run_id:
        raise CommandRefused(
            "current-run audit requires --run-id; pass --history-scope all-time "
            "to snapshot all compatible history"
        )


def cmd_live_check(args: argparse.Namespace) -> int:
    """Cohort start readiness as booleans; exit 0 when ready, 1 when not.

    Credentials are reported as presence only (process environment first, then
    ``.env``); no value is read into this process's environment and nothing is
    printed but booleans. With ``--config`` the profile loads in observe mode
    only, so the check never arms anything. The authority flags only change the
    report (``would_arm``).
    """
    blockers: list[str] = []
    credentials = _credential_readiness(blockers)
    enabled = bool(getattr(args, "enabled", False))
    accepts = bool(getattr(args, "i_accept_live_risk", False))
    if not enabled:
        blockers.append("--enabled not given (live start requires it)")
    if not accepts:
        blockers.append("--i-accept-live-risk not given (live start requires it)")
    config = getattr(args, "config", None)
    if config is None:
        profile = None
        blockers.append("no --config given; the cohort profile was not checked")
    else:
        profile = _profile_readiness(Path(config), blockers)
    ready = not blockers
    report = {
        "ok": ready,
        "command": "live check",
        "ready": ready,
        "blockers": blockers,
        "credentials": credentials,
        "authority": {
            "enabled": enabled,
            "i_accept_live_risk": accepts,
            "would_arm": enabled and accepts,
        },
        "profile": profile,
        "start_command": (
            f"hypervector live start --config {config} --enabled --i-accept-live-risk"
            if config is not None
            else "hypervector live start --config PROFILE --enabled --i-accept-live-risk"
        ),
        "venue_submit": False,
        "network": NETWORK_MAINNET,
    }
    print(json.dumps(report, indent=2, default=str))
    return 0 if ready else 1


def _credential_readiness(blockers: list[str]) -> dict[str, object]:
    """Presence and source of each live credential name; never a value."""
    from hypervector.runtime_env import dotenv_key_presence

    keys = (SECRET_ENV_WALLET, SECRET_ENV_API_KEY)
    presence = dotenv_key_presence(keys)
    sources: dict[str, dict[str, object]] = {}
    for key in keys:
        configured = bool(presence[key])
        in_process = bool((os.environ.get(key) or "").strip())
        source = (
            "process_env" if in_process else ("dotenv" if configured else "missing")
        )
        sources[key] = {"configured": configured, "source": source}
        if not configured:
            blockers.append(f"{key} is not configured (process environment or .env)")
    return {
        "wallet_configured": bool(presence[SECRET_ENV_WALLET]),
        "signing_key_configured": bool(presence[SECRET_ENV_API_KEY]),
        "keys": sources,
    }


def _profile_readiness(path: Path, blockers: list[str]) -> dict[str, object]:
    """Observe-mode profile load, dependency check, STOP and drain markers."""
    report: dict[str, object] = {
        "config": str(path),
        "mode": "observe",
        "loaded": False,
        "profile_id": None,
        "profile_fingerprint": None,
        "provider_dependencies_ok": None,
        "stop_file": None,
        "transition_drain": None,
    }
    try:
        from hypervector.live.multi_asset_live_config import (
            load_multi_asset_live_config,
        )

        config = load_multi_asset_live_config(path, mode="observe")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        blockers.append(f"profile does not load in observe mode: {exc}")
        return report
    report.update(
        loaded=True,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
    )
    try:
        from hypervector.live.cohort_process_commands import (
            require_live_provider_dependencies,
        )

        require_live_provider_dependencies(config)
        report["provider_dependencies_ok"] = True
    except Exception as exc:  # noqa: BLE001 - every dependency failure is a blocker
        report["provider_dependencies_ok"] = False
        report["provider_dependencies_error"] = f"{type(exc).__name__}: {exc}"
        blockers.append(f"provider dependencies not ready: {exc}")
    stop_file = Path(config.stop_file)
    report["stop_file"] = {"path": str(stop_file), "present": stop_file.exists()}
    if stop_file.exists():
        blockers.append(
            f"STOP file present: {stop_file} (the backend would stop at once)"
        )
    drain = Path(config.cohort_ledger).parent / "transition_drain.json"
    report["transition_drain"] = {"path": str(drain), "present": drain.exists()}
    if drain.exists():
        blockers.append(
            f"transition drain evidence remains: {drain}; archive it with "
            "'live drain-archive' or start with --resume-transition-drain"
        )
    return report


def cmd_live_run(args: argparse.Namespace) -> int:
    """Live daemon: mainnet place when enabled+armed+secrets (fail-closed).

    Missing authority flags, missing credentials, an unresolvable ``--export``
    (a bundle directory, a candidate id under ``exports/`` or ``latest``) and a
    shared account another live backend owns are refusals before any venue call
    (exit 2, ``CommandRefused``); failures after start exit 1.
    """
    from hypervector.commands.exports import resolve_export
    from hypervector.live.policy import LivePolicyError
    from hypervector.live.runner import start_live_daemon
    from hypervector.runtime_lock import RuntimeLockError

    if not (
        getattr(args, "enabled", False) and getattr(args, "i_accept_live_risk", False)
    ):
        raise CommandRefused(
            "live run refused: requires both --enabled and --i-accept-live-risk"
        )
    path = resolve_export(args.export, args.data_root)

    try:
        policy = _armed_policy(args)
        wallet, key = _live_credentials()
    except LivePolicyError as exc:
        raise CommandRefused(f"live run refused: {exc}") from exc
    _ensure_root(args)
    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    try:
        result = start_live_daemon(
            **_live_options(args, path, policy, wallet, key, stop_file)
        )
    except RuntimeLockError as exc:
        # Another live owner holds the shared account; nothing was sent.
        raise CommandRefused(f"live run refused: {exc}") from exc
    except LivePolicyError as exc:
        return print_error(args, exc, error=f"live run refused: {exc}")
    except FileNotFoundError as exc:
        return print_error(args, exc)
    except (OSError, RuntimeError, ValueError) as exc:
        return print_error(args, exc, error=f"live run failed: {exc}")

    print(json.dumps(_live_result(result, policy), indent=2, default=str))
    return 0


def cmd_live_report(args: argparse.Namespace) -> int:
    """Summarize live decisions JSONL (read-only; no place)."""
    from hypervector.live.report import (
        default_live_decisions_path,
        report_from_data_root as live_report_from_data_root,
    )

    root = Path(args.data_root)
    decisions = (
        Path(args.decisions)
        if getattr(args, "decisions", None)
        else default_live_decisions_path(root)
    )
    if not decisions.is_file():
        # A mistyped path must not read as an empty session (exit 1).
        missing = FileNotFoundError(f"decisions file not found: {decisions}")
        return print_error(args, missing)
    last_n = int(getattr(args, "last", 5))
    try:
        report = live_report_from_data_root(
            root,
            decisions_path=decisions,
            last_n=last_n,
        )
    except ValueError as exc:
        return print_error(args, exc)
    print(json.dumps(report, indent=2, default=str))
    return 0


def _armed_policy(args: argparse.Namespace) -> LivePolicy:
    """Require explicit authority and existing policy checks before execution."""
    from hypervector.live.policy import (
        DEFAULT_MAX_NOTIONAL_USD,
        LivePolicyError,
        live_policy_from_env,
    )

    armed = bool(getattr(args, "i_accept_live_risk", False))
    if not armed:
        raise LivePolicyError("pass --i-accept-live-risk to arm mainnet risk")

    enabled = bool(getattr(args, "enabled", False))
    if not enabled:
        raise LivePolicyError("pass --enabled to allow live execution")

    max_notional = float(getattr(args, "max_notional_usd", DEFAULT_MAX_NOTIONAL_USD))
    policy = live_policy_from_env(
        enabled=enabled,
        armed=armed,
        max_notional_usd=max_notional,
    )
    policy.require_start()
    return policy


def _live_options(
    args: argparse.Namespace,
    path: Path,
    policy: LivePolicy,
    wallet: str,
    key: str,
    stop_file: Path | None,
) -> dict[str, object]:
    """Build execution arguments without printing credential values."""
    return {
        "export_dir": path,
        "data_root": Path(args.data_root),
        "policy": policy,
        "wallet_address": wallet,
        "private_key": key,
        "conviction": float(getattr(args, "conviction", 0.5)),
        "fee_tier": int(getattr(args, "fee_tier", 0)),
        "stop_file": stop_file,
        "poll_interval_secs": float(getattr(args, "interval_seconds", 5.0)),
        "max_live_bars": int(args.max_live_bars)
        if getattr(args, "max_live_bars", None) is not None
        else None,
        "lookback_days": int(args.lookback)
        if getattr(args, "lookback", None)
        else None,
    }


def _live_result(result: LiveDaemonResult, policy: LivePolicy) -> dict[str, object]:
    """Report observed daemon activity and the effective explicit policy."""
    return {
        "ok": True,
        "execution_mode": result.execution_mode,
        "run_id": result.run_id,
        "export_dir": str(result.export_dir),
        "decisions_path": str(result.decisions_path),
        "warm_bars": result.warm_bars,
        "live_bars": result.live_bars,
        "bars_processed": result.bars_processed,
        "fills_count": result.fills_count,
        "places_count": result.places_count,
        "catchup_bars": getattr(result, "catchup_bars", 0),
        # Open exposure at stop: the daemon never flattens when it stops.
        "position_qty": getattr(result, "position_qty", 0.0),
        "stop_reason": result.stop_reason,
        "cancel_attempted": result.cancel_attempted,
        "cancel_ok": result.cancel_ok,
        # cancel_ok means no owned resting order remained (not every order on the coin).
        "cancel_scope": "owned_resting_orders",
        "cancel_error": result.cancel_error,
        "network": NETWORK_MAINNET,
        "max_notional_usd": policy.max_notional_usd,
        "venue_submit": True,  # armed live-run path (actual places depend on signals)
    }


def _live_credentials() -> tuple[str, str]:
    """Require non-empty configured values without exposing them in diagnostics."""
    from hypervector.live.policy import LivePolicyError

    wallet = (os.environ.get(SECRET_ENV_WALLET) or "").strip()
    key = (os.environ.get(SECRET_ENV_API_KEY) or "").strip()
    if not wallet or not key:
        raise LivePolicyError(f"set {SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}")
    return wallet, key
