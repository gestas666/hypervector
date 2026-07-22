"""Load Phase 1 export bundles into a Phase 2 StrategyLoadout."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hypervector.export.schema import validate_export_dir


@dataclass(frozen=True)
class StrategyLoadout:
    """Canonical inputs for Nautilus Phase 2 historical sim.

    Signal arrays are intentionally omitted: live/sim alpha re-runs strategy
    logic from ``params`` + risk/cost/exit config. Optional signal parquet may
    be loaded separately for parity tests only.
    """

    strategy_name: str
    role: str | None
    params: dict[str, Any]
    meta: dict[str, Any]
    costs: dict[str, Any] | None
    risk: dict[str, Any] | None
    exit_mode: str | None
    exits: dict[str, Any] | None
    export_dir: Path
    metrics: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    symbol: str = "BTC"
    timeframe: str = "1m"
    init_cash: float | None = None
    schema_version: str | None = None

    def summary(self) -> dict[str, Any]:
        """Compact JSON-serializable description for CLI / logs."""
        return {
            "export_dir": str(self.export_dir),
            "strategy_name": self.strategy_name,
            "role": self.role,
            "run_id": self.run_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "init_cash": self.init_cash,
            "exit_mode": self.exit_mode,
            "has_costs": self.costs is not None,
            "has_risk": self.risk is not None,
            "has_exits": self.exits is not None,
            "schema_version": self.schema_version,
            "param_keys": sorted(self.params.keys()),
            "metric_keys": sorted(self.metrics.keys()),
            "note": "signals are not loadout inputs (replay/parity only)",
        }


def load_strategy_loadout(
    export_dir: Path | str,
    *,
    strict: bool = True,
) -> StrategyLoadout:
    """Parse and validate an export directory into a :class:`StrategyLoadout`.

    ``strict=True`` (default) requires Phase 1.5 fields for Phase 2 readiness.
    """
    root = Path(export_dir)
    report = validate_export_dir(root, strict=strict)
    meta = report["meta"]
    params = dict(report["params"])
    metrics = dict(report["metrics"])

    strategy_name = str(report["strategy"])
    # role may live on params or meta.track (uptrend/downtrend/regime)
    raw_role = params.get("role") or meta.get("track")
    role = str(raw_role) if raw_role is not None else None

    # Strategy hyperparams only — drop identity keys duplicated on loadout
    strategy_params = {
        k: v for k, v in params.items() if k not in ("strategy", "role")
    }

    costs = meta.get("costs") if isinstance(meta.get("costs"), dict) else None
    risk = meta.get("risk") if isinstance(meta.get("risk"), dict) else None
    exits = meta.get("exits") if isinstance(meta.get("exits"), dict) else None
    exit_mode = meta.get("tp_sl_mode") or (exits or {}).get("mode") or params.get("exit_mode")
    if exit_mode is not None:
        exit_mode = str(exit_mode)

    init_cash = meta.get("init_cash")
    if init_cash is not None:
        init_cash = float(init_cash)

    return StrategyLoadout(
        strategy_name=strategy_name,
        role=str(role) if role is not None else None,
        params=strategy_params,
        meta=meta,
        costs=costs,
        risk=risk,
        exit_mode=exit_mode,
        exits=exits,
        export_dir=root.resolve(),
        metrics=metrics,
        run_id=str(meta.get("run_id")) if meta.get("run_id") is not None else None,
        symbol=str(meta.get("symbol") or "BTC"),
        timeframe=str(meta.get("timeframe") or "1m"),
        init_cash=init_cash,
        schema_version=str(meta.get("schema_version")) if meta.get("schema_version") else None,
    )
