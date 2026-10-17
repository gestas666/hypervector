"""Status command handlers; imported only on dispatch."""

from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
from pathlib import Path
from hypervector.infra import layout_report, paths_for
from importlib.metadata import PackageNotFoundError, version
from hypervector.paper.fill_models import DEFAULT_MAX_BOOK_AGE_MS
from hypervector.paper.order_intent import NETWORK_MAINNET, ORDER_INTENT_SCHEMA
from hypervector.commands.common import _ensure_root, _secrets_present
from hypervector.paper.fill_models import FILL_MODEL_L2_WALK_V1
from hypervector.commands.registry import (
    ACTIONS,
    CLI_COMMANDS,
    GROUP_ORDER,
    LEGACY_ALIASES,
    RETIRED,
)

SECRET_ENV_WALLET = "HYPERVECTOR_HL_WALLET_ADDRESS"
SECRET_ENV_API_KEY = "HYPERVECTOR_HL_API_PRIVATE_KEY"
DEFAULT_PREFERRED_FILL_MODEL = FILL_MODEL_L2_WALK_V1
DEFAULT_METALABEL_ENABLED = False
DEFAULT_EXECUTION_MODE = "shadow"
LIVE_BACKEND = "hypervector.operations.multi_asset_bidirectional_live"


def cmd_infra_init(args: argparse.Namespace) -> int:
    """Create the explicit local data layout and report its paths."""
    paths = _ensure_root(args)
    report = layout_report(paths.root)
    print(json.dumps(report, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Command inventory and capability flags (no secret values; creates nothing)."""
    paths = paths_for(args.data_root)
    out = {
        "ok": True,
        "schema_version": 3,
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
        "legacy_aliases": _legacy_aliases(),
        "retired": dict(RETIRED),
        "capabilities": _capabilities(),
        "paper": {
            "default_mode": DEFAULT_EXECUTION_MODE,
            "no_submit": True,
            "commands": _group_commands("paper"),
        },
        "live": _live_inventory(),
        "honesty": {
            "paper_never_constructs_exec_client": True,
            "live_fail_closed": True,
            "secret_values_never_printed": True,
        },
        "metalabel": _model_inventory(args, paths.root),
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


def _group_commands(group: str) -> list[str]:
    return [f"{group} {action}" for action in ACTIONS.get(group, ())]


def _workflows() -> dict[str, list[str]]:
    return {group: list(ACTIONS[group]) for group in GROUP_ORDER if group in ACTIONS}


def _legacy_aliases() -> dict[str, str]:
    return {
        old: " ".join((*legacy.words, *legacy.insert))
        for old, legacy in sorted(LEGACY_ALIASES.items())
    }


def _live_inventory() -> dict[str, object]:
    """Describe the cohort backend's command surface; status never arms anything."""
    return {
        "backend": LIVE_BACKEND,
        "check_command": "live check",
        "start_command": "live start",
        "commands": _group_commands("live"),
        "requires_for_start": ["--config", "--enabled", "--i-accept-live-risk"],
        "enabled_default": False,
        "armed": False,
        "network": NETWORK_MAINNET,
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
    result["0xarchive"] = _oxa_capability()
    return result


def _oxa_capability() -> dict[str, object]:
    """0xArchive readiness is the API key's presence (boolean only), not a package."""
    from hypervector.runtime_env import dotenv_key_presence

    configured = dotenv_key_presence(("OXA_API_KEY",))["OXA_API_KEY"]
    return {
        "installed": True,
        "api_key_configured": configured,
        "credential_env": "OXA_API_KEY",
        "operational_readiness": "not_probed",
    }


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
        "enable_flag": "paper run --metalabel-mode",
        "modes": ["off", "observe", "scale", "filter"],
        "recommended_annotation_flag": "paper run --metalabel-mode observe",
    }


def _paper_surface_flags(data_root: Path | str | None = None) -> dict[str, object]:
    """Report paper wiring and explicitly scoped model readiness without clients.

    Module availability is probed with ``find_spec``; the fields named in
    ``policy_constants`` are fixed policy values, not probes.
    """
    from hypervector.ml.metalabel import probe_metalabel

    book_feed_ok = find_spec("hypervector.paper.book") is not None
    l2_walk_ok = find_spec("hypervector.paper.fill_models") is not None
    metalabel_probe = probe_metalabel(data_root=data_root)
    return {
        # Shadow surface (strings/bools only; never secret values).
        "policy_constants": [
            "mode",
            "network",
            "no_submit",
            "submitted_default",
            "order_intent_schema",
            "preferred_fill_model",
            "max_book_age_ms",
            "metalabel_enabled",
            "metalabel_default_off",
        ],
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
        # Ready-to-enable (bundle installed); still off until paper run --metalabel-mode.
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
        # Alias of mode; the default is shadow (mainnet, no venue orders).
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "decisions": str(paths.paper_decisions),
        "ledger": str(paths.paper_ledger),
        "live_feed_loop": True,
        # There is no sandbox client; the field stays for report compatibility.
        "sandbox_enabled": False,
        "secrets_present": _secrets_present(),
        "secret_env_names": [SECRET_ENV_WALLET, SECRET_ENV_API_KEY],
    }
    paper.update(_paper_surface_flags(paths.root))
    report["paper"] = paper
    from hypervector.live.policy import live_policy_from_env

    live_pol = live_policy_from_env(enabled=False, armed=False)
    ready = live_pol.readiness()
    report["live"] = {
        "enabled": False,
        "decisions": str(paths.live_decisions),
        "ledger": str(paths.live_ledger),
        "submit_wired": bool(ready.get("submit_wired")),
        "note": ready.get(
            "note",
            "Live readiness — use 'live check' for start gates.",
        ),
        "readiness": ready,
    }
    print(json.dumps(report, indent=2))
    return 0
