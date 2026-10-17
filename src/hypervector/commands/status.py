"""Status command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from hypervector.infra import layout_report, paths_for
from importlib.metadata import PackageNotFoundError, version
from hypervector.paper.fill_models import DEFAULT_MAX_BOOK_AGE_MS
from hypervector.live.policy import (
    DEFAULT_MAX_NOTIONAL_USD,
    LivePolicyError,
    live_policy_from_env,
)
from hypervector.paper.order_intent import NETWORK_MAINNET, ORDER_INTENT_SCHEMA
from hypervector.commands.common import _ensure_root, _secrets_present
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1
from hypervector.commands.registry import CLI_COMMANDS, GROUPS, command_specs

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"
DEFAULT_PREFERRED_FILL_MODEL = FILL_MODEL_L2_WALK_V1
DEFAULT_METALABEL_ENABLED = False
DEFAULT_EXECUTION_MODE = "shadow"


def cmd_infra_init(args: argparse.Namespace) -> int:
    """Create the explicit local data layout and report its paths."""
    paths = _ensure_root(args)
    report = layout_report(paths.root)
    print(json.dumps(report, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Pipeline + CLI inventory (no secret values; no place)."""
    paths = paths_for(args.data_root)
    ready = live_policy_from_env(enabled=False, armed=False).readiness()
    out = {
        "ok": True,
        "schema_version": 2,
        "workflows": _workflows(),
        "root": str(paths.root.resolve()),
        "pipeline": {
            "phase1_research": True,
            "phase2_historical": True,
            "paper_shadow_dry_run": True,
            "live_submit": True,
            "tui_gui": False,
        },
        "commands": list(CLI_COMMANDS),
        "capabilities": _capabilities(),
        "paper": {
            "default_mode": DEFAULT_EXECUTION_MODE,
            "no_submit": True,
            "commands": ["paper-check", "paper-report", "paper-run"],
        },
        "live": {
            "submit_wired": bool(ready.get("submit_wired")),
            "can_start": bool(ready.get("can_start")),
            "enabled_default": False,
            "max_notional_usd": float(
                ready.get("max_notional_usd", DEFAULT_MAX_NOTIONAL_USD)
            ),
            "network": ready.get("network", NETWORK_MAINNET),
            "commands": ["live-check", "live-report", "live-run"],
            "requires_for_run": ["--enabled", "--i-accept-live-risk", "secrets"],
        },
        "honesty": {
            "paper_never_constructs_exec_client": True,
            "live_run_fail_closed": True,
            "secret_values_never_printed": True,
        },
        "metalabel": _model_inventory(args, paths.root),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _workflows() -> dict[str, list[object]]:
    return {
        group: [spec["action"] for owner, spec in command_specs() if owner == group]
        for group in GROUPS
    }


def _model_inventory(args: argparse.Namespace, root: Path) -> dict[str, object]:
    if getattr(args, "probe_model", False):
        return _metalabel_status(root)
    return {
        "enabled_default": False,
        "ready": None,
        "state": "not_probed",
        "configured_root": str(paths_for(root).models_metalabel),
        "probe_command": "system status --probe-model",
    }


def _capabilities() -> dict[str, dict[str, object]]:
    """Distinguish installed integrations from operational or venue readiness."""
    packages = {
        "vectorbt": "vectorbt",
        "talib": "TA-Lib",
        "nautilus": "nautilus_trader",
        "hyperliquid": "hyperliquid-python-sdk",
        "0xarchive": "requests",
    }
    result = {}
    for capability, package in packages.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = None
        result[capability] = {
            "installed": installed is not None,
            "version": installed,
            "operational_readiness": "not_probed",
        }
    result["karpathy"] = {"installed": True, "operational_readiness": "not_probed"}
    return result


def _metalabel_status(data_root: Path | str) -> dict[str, object]:
    """Compact metalabel readiness for status (default still off)."""
    try:
        from hypervector.ml.metalabel import probe_metalabel

        p = probe_metalabel(data_root=data_root)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        return {
            "enabled_default": False,
            "ready": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "enabled_default": False,
        "ready": bool(p.get("loadable")),
        "bundle_root": p.get("bundle_root"),
        "n_features": p.get("n_features"),
        "calibrator": bool(p.get("calibrator_present")),
        "env_root_set": bool(p.get("env_root_set")),
        "error": p.get("error"),
        "enable_flag": "paper-run --metalabel",
        "modes": ["off", "observe", "scale", "filter"],
        "recommended_annotation_flag": "paper-run --metalabel-mode observe",
    }


def _paper_surface_flags(data_root: Path | str | None = None) -> dict[str, object]:
    """Report paper wiring and explicitly scoped model readiness without clients."""
    from hypervector.paper.book import BookFeed
    from hypervector.paper.fill_models import L2WalkFillModel
    from hypervector.ml.metalabel import probe_metalabel

    book_feed_ok = callable(BookFeed)
    l2_walk_ok = callable(L2WalkFillModel)
    metalabel_probe = probe_metalabel(data_root=data_root)
    return {
        # Phase 4b shadow surface (strings/bools only; never secret values).
        "mode": DEFAULT_EXECUTION_MODE,
        "network": NETWORK_MAINNET,
        "no_submit": True,
        "submitted_default": False,
        "order_intent_schema": ORDER_INTENT_SCHEMA,
        "preferred_fill_model": DEFAULT_PREFERRED_FILL_MODEL,
        "max_book_age_ms": int(DEFAULT_MAX_BOOK_AGE_MS),
        "book_feed": book_feed_ok,
        "l2_walk_available": l2_walk_ok,
        "metalabel_enabled": DEFAULT_METALABEL_ENABLED,
        "metalabel_default_off": True,
        "metalabel_modes": ["off", "observe", "scale", "filter"],
        "recommended_annotation_flag": "--metalabel-mode observe",
        # Ready-to-enable (bundle installed); still off until paper-run --metalabel.
        "metalabel_ready": bool(metalabel_probe.get("loadable")),
        "metalabel_bundle_root": metalabel_probe.get("bundle_root"),
        "metalabel_n_features": metalabel_probe.get("n_features"),
        "metalabel_calibrator": bool(metalabel_probe.get("calibrator_present")),
        "metalabel_error": metalabel_probe.get("error"),
    }


def cmd_paper_check(args: argparse.Namespace) -> int:
    """Print paper/live layout identity and readiness flags (no secret values)."""
    paths = paths_for(args.data_root)
    report = layout_report(paths.root)
    paper = {
        # Alias of mode; Phase 4b default is shadow (mainnet, no venue orders).
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "decisions": str(paths.paper_decisions),
        "ledger": str(paths.paper_ledger),
        "live_feed_loop": True,
        # Default off; paper-run --sandbox sets shadow fields only (no real sandbox client).
        "sandbox_enabled": False,
        "secrets_present": _secrets_present(),
        "secret_env_names": [SECRET_ENV_WALLET, SECRET_ENV_API_KEY],
    }
    paper.update(_paper_surface_flags(paths.root))
    report["paper"] = paper
    live_pol = live_policy_from_env(enabled=False, armed=False)
    ready = live_pol.readiness()
    report["live"] = {
        "enabled": False,
        "decisions": str(paths.live_decisions),
        "ledger": str(paths.live_ledger),
        "submit_wired": bool(ready.get("submit_wired")),
        "note": ready.get(
            "note",
            "Live readiness — use live-check for start gates.",
        ),
        "readiness": ready,
    }
    print(json.dumps(report, indent=2))
    return 0


def cmd_live_check(args: argparse.Namespace) -> int:
    """Live readiness (policy only; never prints secret values; no submit)."""
    paths = paths_for(args.data_root)
    enabled = bool(getattr(args, "enabled", False))
    armed = bool(getattr(args, "armed", False))
    max_notional = float(getattr(args, "max_notional_usd", DEFAULT_MAX_NOTIONAL_USD))
    policy = live_policy_from_env(
        enabled=enabled,
        armed=armed,
        max_notional_usd=max_notional,
    )
    ready = policy.readiness()
    report = {
        "ok": True,
        "root": str(paths.root.resolve()),
        "live_decisions": str(paths.live_decisions),
        "live_ledger": str(paths.live_ledger),
        "live": ready,
        "paper_path_unchanged": True,
        # live-check never places; True only would mean an active submit session.
        "venue_submit": False,
        "submit_wired": bool(ready.get("submit_wired")),
    }
    # Attempt start gate only for diagnostics (do not start daemon).
    try:
        policy.require_start()
        report["start_gate"] = "ok"
    except LivePolicyError as exc:
        report["start_gate"] = "refused"
        report["start_gate_reason"] = str(exc)
    print(json.dumps(report, indent=2, default=str))
    return 0
