"""Live command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from hypervector.live.policy import (
    DEFAULT_MAX_NOTIONAL_USD,
    LivePolicy,
    LivePolicyError,
    live_policy_from_env,
)
from hypervector.live.report import report_from_data_root as live_report_from_data_root
from hypervector.live.runner import LiveDaemonResult, start_live_daemon
from hypervector.paper.order_intent import NETWORK_MAINNET
from hypervector.commands.common import _ensure_root

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"


def cmd_live_run(args: argparse.Namespace) -> int:
    """Live daemon: mainnet place when enabled+armed+secrets (fail-closed)."""
    path = Path(args.path)
    if not path.is_dir():
        print(f"export path not found: {path}", file=sys.stderr)
        return 1

    try:
        policy = _armed_policy(args)
        wallet, key = _live_credentials()
    except LivePolicyError as exc:
        print(f"live-run refused: {exc}", file=sys.stderr)
        return 1
    _ensure_root(args)
    stop_file = Path(args.stop_file) if getattr(args, "stop_file", None) else None
    try:
        result = start_live_daemon(
            **_live_options(args, path, policy, wallet, key, stop_file)
        )
    except LivePolicyError as exc:
        print(f"live-run refused: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"live-run failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(_live_result(result, policy), indent=2, default=str))
    return 0


def cmd_live_report(args: argparse.Namespace) -> int:
    """Summarize live decisions JSONL (read-only; no place)."""
    root = Path(args.data_root)
    decisions = Path(args.path) if getattr(args, "path", None) else None
    last_n = int(getattr(args, "last", 5))
    try:
        report = live_report_from_data_root(
            root,
            decisions_path=decisions,
            last_n=last_n,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, default=str))
    return 0


def _armed_policy(args: argparse.Namespace) -> LivePolicy:
    """Require explicit authority and existing policy checks before execution."""
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
        "poll_interval_secs": float(getattr(args, "poll_interval", 5.0)),
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
        "stop_reason": result.stop_reason,
        "cancel_attempted": result.cancel_attempted,
        "cancel_ok": result.cancel_ok,
        "cancel_error": result.cancel_error,
        "network": NETWORK_MAINNET,
        "max_notional_usd": policy.max_notional_usd,
        "venue_submit": True,  # armed live-run path (actual places depend on signals)
    }


def _live_credentials() -> tuple[str, str]:
    """Require non-empty configured values without exposing them in diagnostics."""
    wallet = (os.environ.get(SECRET_ENV_WALLET) or "").strip()
    key = (os.environ.get(SECRET_ENV_API_KEY) or "").strip()
    if not wallet or not key:
        raise LivePolicyError(f"set {SECRET_ENV_WALLET} and {SECRET_ENV_API_KEY}")
    return wallet, key
