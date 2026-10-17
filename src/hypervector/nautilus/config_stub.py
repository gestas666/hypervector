"""Offline Nautilus Phase 2 config stub — construct without network or keys.

Does not start a TradingNode or BacktestEngine. Produces a serializable
description plus optional real Nautilus config objects when the package is
importable, so Phase 2 can wire a real engine later without inventing paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypervector.infra import paths_for
from hypervector.nautilus.errors import UnknownStrategyError, UnsupportedNautilusSymbol
from hypervector.nautilus.load_export import StrategyLoadout, load_strategy_loadout
from hypervector.nautilus.venue_spec import (
    research_symbol_to_instrument,
    resolve_venue_spec,
)

_SIGNAL_PROBE_BARS = 600


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
            "nautilus run is historical Nautilus only",
            "paper/shadow dry-run → paper run (no venue orders)",
            "live execution → live start (--enabled --i-accept-live-risk)",
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
    venue = "HYPERLIQUID"
    return Phase2StubConfig(
        loadout=loadout,
        data_root=root.resolve(),
        catalog_path=paths.nautilus_backtest.resolve(),
        log_path=paths.logs_nautilus.resolve(),
        venue=venue,
        instrument_id_hint=f"{research_symbol_to_instrument(loadout.symbol)}.{venue}",
    )


def _timeframe_to_pandas_freq(timeframe: str) -> str:
    m = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", str(timeframe).lower())
    if not m:
        raise ValueError(f"unsupported timeframe for signal probe: {timeframe!r}")
    units = {"m": "min", "h": "h", "d": "D"}
    return f"{m.group(1)}{units[m.group(2)]}"


def signal_probe(
    loadout: StrategyLoadout, *, bars: int = _SIGNAL_PROBE_BARS
) -> dict[str, Any]:
    """Dry-run the strategy builder with the export params on synthetic OHLCV.

    Catches exports whose params the builder rejects (they would fail
    ``nautilus run`` as a technical failure) at check time. Offline only.
    """
    from hypervector.data.sources import fixture_ohlcv
    from hypervector.nautilus.signals import signals_from_ohlcv

    try:
        freq = _timeframe_to_pandas_freq(loadout.timeframe)
        df = fixture_ohlcv(n_bars=int(bars), freq=freq, drift=5.0, wave_period=40)
        frame = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        entries, exits, direction = signals_from_ohlcv(
            frame, loadout.strategy_name, dict(loadout.params)
        )
        if len(entries) != len(frame) or len(exits) != len(frame):
            raise ValueError(
                f"builder returned {len(entries)}/{len(exits)} rows for {len(frame)} bars"
            )
    except Exception as exc:
        return {
            "ok": False,
            "bars": int(bars),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "ok": True,
        "bars": int(bars),
        "direction": str(direction),
        "entries": int(entries.astype(bool).sum()),
        "exits": int(exits.astype(bool).sum()),
    }


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
    probe_signals: bool = True,
) -> dict[str, Any]:
    """Full CLI-oriented Phase 2 readiness report (offline).

    ``ok`` predicts ``nautilus run``: it is false when the symbol has no
    known venue geometry or the strategy builder rejects the export params.
    An unregistered strategy raises :class:`UnknownStrategyError` (an invalid
    bundle, reported like a schema error).
    """
    from hypervector.nautilus.costs import (
        resolve_phase2_conviction,
        resolve_phase2_costs,
    )
    from hypervector.nautilus.signals import resolve_strategy_spec

    stub = build_phase2_stub_config(export_dir, data_root=data_root, strict=strict)
    loadout = stub.loadout
    try:
        resolve_strategy_spec(loadout.strategy_name)
    except KeyError:
        raise UnknownStrategyError(loadout.export_dir, loadout.strategy_name) from None

    try:
        venue_spec: dict[str, Any] | None = resolve_venue_spec(
            loadout.symbol, loadout.meta
        ).to_dict()
        unsupported_reason = None
    except UnsupportedNautilusSymbol as exc:
        venue_spec = None
        unsupported_reason = str(exc)
    conviction, conviction_source = resolve_phase2_conviction(loadout, None)

    report: dict[str, Any] = {
        "ok": unsupported_reason is None,
        "strategy_registered": True,
        "nautilus_run_supported": unsupported_reason is None,
        "unsupported_reason": unsupported_reason,
        "instrument": venue_spec,
        "cost_model": resolve_phase2_costs(loadout).to_dict(),
        "conviction": conviction,
        "conviction_source": conviction_source,
        "phase2_stub": stub.to_dict(),
        # Honesty: paper/shadow dry-run is 'paper run' (not 'nautilus run').
        # Live execution is 'live start' with both authority flags.
        "paper_live": {
            "implemented": True,
            "phase2_run_modes": False,
            "paper_dry_run": {
                "implemented": True,
                "command": "paper run",
                "default_mode": "shadow",
                "no_submit": True,
            },
            "live_submit": {
                "implemented": True,
                "command": "live start",
                "requires": ["--config", "--enabled", "--i-accept-live-risk"],
                "message": (
                    "live start places only with --enabled --i-accept-live-risk; "
                    "paper run remains no-submit"
                ),
            },
            "message": (
                "nautilus run is historical only; paper/shadow dry-run is paper run "
                "(default mode=shadow, no venue orders); live execution is live start"
            ),
        },
    }
    if probe_signals:
        report["signal_probe"] = signal_probe(loadout)
        if not report["signal_probe"]["ok"]:
            report["ok"] = False
    if probe_nautilus:
        try:
            report["nautilus_probe"] = try_import_nautilus_backtest_types()
        except ImportError as exc:
            report["nautilus_probe"] = {"ok": False, "error": str(exc)}
    return report
