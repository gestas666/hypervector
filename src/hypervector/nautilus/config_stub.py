"""Offline Nautilus Phase 2 config stub — construct without network or keys.

Does not start a TradingNode or BacktestEngine. Produces a serializable
description plus optional real Nautilus config objects when the package is
importable, so Phase 2 can wire a real engine later without inventing paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout


@dataclass(frozen=True)
class Phase2StubConfig:
    """Offline Phase 2 configuration snapshot."""

    loadout: StrategyLoadout
    data_root: Path
    catalog_path: Path
    log_path: Path
    execution_mode: str = "phase2_historical"
    venue: str = "HYPERLIQUID"
    instrument_id_hint: str = "BTC-PERP.HYPERLIQUID"
    paper_live_implemented: bool = True
    notes: tuple[str, ...] = field(
        default_factory=lambda: (
            "phase2-run is historical Nautilus only",
            "paper/shadow dry-run → paper-run (no venue orders)",
            "live venue submit → live-run (enabled+armed+secrets)",
            "Re-run strategy from params; do not replay signals as alpha",
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "venue": self.venue,
            "instrument_id_hint": self.instrument_id_hint,
            "data_root": str(self.data_root),
            "catalog_path": str(self.catalog_path),
            "log_path": str(self.log_path),
            "paper_live_implemented": self.paper_live_implemented,
            "notes": list(self.notes),
            "loadout": self.loadout.summary(),
            "costs": self.loadout.costs,
            "risk": self.loadout.risk,
            "exit_mode": self.loadout.exit_mode,
            "exits": self.loadout.exits,
            "params": self.loadout.params,
        }


def build_phase2_stub_config(
    export_dir: Path | str,
    *,
    data_root: Path | str = "data",
    strict: bool = True,
) -> Phase2StubConfig:
    """Load export → loadout and resolve offline artifact paths under data root.

    Paths point at ``data/nautilus/backtest`` and ``data/logs/nautilus`` without
    creating network clients or requiring API keys.
    """
    root = Path(data_root)
    paths = paths_for(root)
    loadout = load_strategy_loadout(export_dir, strict=strict)
    return Phase2StubConfig(
        loadout=loadout,
        data_root=root.resolve(),
        catalog_path=paths.nautilus_backtest.resolve(),
        log_path=paths.logs_nautilus.resolve(),
    )


def try_import_nautilus_backtest_types() -> dict[str, Any]:
    """Probe Nautilus backtest public types offline (no engine start).

    Returns a small capability map. Safe when nautilus_trader is installed;
    raises ImportError if the package is missing (caller may catch).
    """
    import nautilus_trader
    from nautilus_trader.adapters.hyperliquid import (
        HYPERLIQUID,
        HYPERLIQUID_VENUE,
        HyperliquidDataClientConfig,
        HyperliquidExecClientConfig,
    )

    # Construct configs only — no connect / no private key required for data cfg
    data_cfg = HyperliquidDataClientConfig()
    exec_cfg = HyperliquidExecClientConfig()

    return {
        "nautilus_version": getattr(nautilus_trader, "__version__", None),
        "venue": str(HYPERLIQUID_VENUE),
        "adapter": HYPERLIQUID,
        "data_client_config_type": type(data_cfg).__name__,
        "exec_client_config_type": type(exec_cfg).__name__,
        "data_http_timeout_secs": data_cfg.http_timeout_secs,
        "exec_private_key_set": exec_cfg.private_key is not None,
        "engine_started": False,
    }


def phase2_check_report(
    export_dir: Path | str,
    *,
    data_root: Path | str = "data",
    strict: bool = True,
    probe_nautilus: bool = True,
) -> dict[str, Any]:
    """Full CLI-oriented Phase 2 readiness report (offline)."""
    stub = build_phase2_stub_config(export_dir, data_root=data_root, strict=strict)
    report: dict[str, Any] = {
        "ok": True,
        "phase2_stub": stub.to_dict(),
        # Honesty: paper/shadow dry-run is implemented via paper-run (not phase2-run).
        # Live venue submit remains a later phase (4b-live).
        "paper_live": {
            "implemented": True,
            "phase2_run_modes": False,
            "paper_dry_run": {
                "implemented": True,
                "command": "paper-run",
                "default_mode": "shadow",
                "no_submit": True,
            },
            "live_submit": {
                "implemented": True,
                "command": "live-run",
                "requires": ["--enabled", "--i-accept-live-risk", "secrets"],
                "message": (
                    "live-run places only when enabled+armed+secrets; "
                    "paper-run remains no-submit"
                ),
            },
            "message": (
                "phase2-run is historical only; paper/shadow dry-run is paper-run "
                "(default mode=shadow, no venue orders); live venue submit is live-run"
            ),
        },
    }
    if probe_nautilus:
        try:
            report["nautilus_probe"] = try_import_nautilus_backtest_types()
        except ImportError as exc:
            report["nautilus_probe"] = {"ok": False, "error": str(exc)}
    return report
