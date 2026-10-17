"""Export bundle schema validation (Phase 1 → Phase 2 handoff contract).

Canonical live inputs live in meta + params. Signal arrays are optional and
never treated as live alpha (replay/parity only).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXPORT_SCHEMA_VERSION = "1"

REQUIRED_FILES: tuple[str, ...] = ("meta.json", "params.json", "metrics.json")

# Always required on meta after schema hardening
META_REQUIRED: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "package_version",
    "symbol",
    "timeframe",
)

# Phase 1.5 / Phase 2 readiness fields (required when strict=True)
META_PHASE15_REQUIRED: tuple[str, ...] = (
    "init_cash",
    "costs",
    "risk",
    "tp_sl_mode",
    "exits",
)

PARAMS_REQUIRED: tuple[str, ...] = ("strategy",)

# Mirror of hypervector.sweep.metrics.REQUIRED_METRIC_KEYS (kept literal so the
# loader path never imports the sweep/VectorBT stack; a test pins equality).
REQUIRED_METRIC_KEYS: tuple[str, ...] = (
    "net_pnl",
    "total_return_pct",
    "sharpe",
    "trade_count",
    "wins",
    "losses",
    "win_pct",
    "max_drawdown",
)

OPTIONAL_FILES: tuple[str, ...] = (
    "metrics.csv",
    "signals.parquet",
    "regime_labels.parquet",
)

VALID_TP_SL_MODES: frozenset[str] = frozenset({"fixed_rr", "atr", "trail"})


class ExportSchemaError(ValueError):
    """Raised when an export directory fails schema validation."""

    def __init__(self, path: Path | str, errors: list[str]) -> None:
        self.path = Path(path)
        self.errors = list(errors)
        msg = f"export schema invalid at {self.path}: " + "; ".join(self.errors)
        super().__init__(msg)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExportSchemaError(
            path.parent, [f"{path.name}: invalid JSON ({exc})"]
        ) from exc
    except OSError as exc:
        raise ExportSchemaError(
            path.parent, [f"{path.name}: unreadable ({exc})"]
        ) from exc


def _check_costs(costs: Any, errors: list[str], *, prefix: str = "meta.costs") -> None:
    if not isinstance(costs, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ("taker_fee", "slippage_bps"):
        if key not in costs:
            errors.append(f"{prefix}.{key} missing")
        else:
            try:
                float(costs[key])
            except (TypeError, ValueError):
                errors.append(f"{prefix}.{key} must be numeric")


def _check_risk(risk: Any, errors: list[str], *, prefix: str = "meta.risk") -> None:
    if not isinstance(risk, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key in ("risk_pct_min", "risk_pct_max"):
        if key not in risk:
            errors.append(f"{prefix}.{key} missing")
            continue
        try:
            float(risk[key])
        except (TypeError, ValueError):
            errors.append(f"{prefix}.{key} must be numeric")
    lo = risk.get("risk_pct_min")
    hi = risk.get("risk_pct_max")
    try:
        if lo is not None and hi is not None and float(lo) > float(hi):
            errors.append(f"{prefix}: risk_pct_min must be <= risk_pct_max")
    except (TypeError, ValueError):
        pass


def _check_exits(exits: Any, errors: list[str], *, prefix: str = "meta.exits") -> None:
    if not isinstance(exits, dict):
        errors.append(f"{prefix} must be an object")
        return
    mode = exits.get("mode")
    if mode is None or mode == "":
        errors.append(f"{prefix}.mode missing")
    elif str(mode) not in VALID_TP_SL_MODES:
        errors.append(
            f"{prefix}.mode={mode!r} invalid "
            f"(expected one of {sorted(VALID_TP_SL_MODES)})"
        )
    for key in ("sl_pct", "rr", "atr_length", "sl_atr_mult", "trail_atr_mult"):
        if key not in exits:
            errors.append(f"{prefix}.{key} missing")
            continue
        try:
            float(exits[key])
        except (TypeError, ValueError):
            errors.append(f"{prefix}.{key} must be numeric")


def validate_export_dir(
    path: Path | str,
    *,
    strict: bool = False,
    require_costed: bool = False,
    require_metrics: bool = False,
) -> dict[str, Any]:
    """Validate an export bundle directory.

    Returns a structured report including loaded meta/params/metrics summaries.
    Raises :class:`ExportSchemaError` when required contract is violated.

    Parameters
    ----------
    path:
        Directory containing meta.json / params.json / metrics.json.
    strict:
        When True, also require Phase 1.5 fields (init_cash, costs, risk, tp_sl_mode)
        so the bundle is Phase 2 loadout-ready.
    require_costed:
        Opt-in: reject bundles measured with ``meta.apply_costs`` false.
    require_metrics:
        Opt-in: reject bundles whose metrics lack any REQUIRED_METRIC_KEYS.

    Zero-cost diagnostics and missing metric keys are always reported as
    non-fatal ``warnings`` (plus ``apply_costs`` / ``missing_metric_keys``)
    so loaders keep working while operators can see what was certified.
    """
    root = Path(path)
    errors: list[str] = []

    if not root.is_dir():
        raise ExportSchemaError(root, ["path is not a directory"])

    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            errors.append(f"missing required file {name}")

    if errors:
        raise ExportSchemaError(root, errors)

    meta = _read_json(root / "meta.json")
    params = _read_json(root / "params.json")
    metrics = _read_json(root / "metrics.json")

    if not isinstance(meta, dict):
        errors.append("meta.json must be a JSON object")
        meta = {}
    if not isinstance(params, dict):
        errors.append("params.json must be a JSON object")
        params = {}
    if not isinstance(metrics, dict):
        errors.append("metrics.json must be a JSON object")
        metrics = {}

    for key in META_REQUIRED:
        if key not in meta or meta[key] in (None, ""):
            errors.append(f"meta.{key} missing")

    schema_ver = meta.get("schema_version")
    if schema_ver is not None and str(schema_ver) != EXPORT_SCHEMA_VERSION:
        errors.append(
            f"meta.schema_version={schema_ver!r} unsupported "
            f"(expected {EXPORT_SCHEMA_VERSION!r})"
        )

    for key in PARAMS_REQUIRED:
        if key not in params or params[key] in (None, ""):
            errors.append(f"params.{key} missing")

    # strategy may also appear on meta for convenience
    strategy = params.get("strategy") or meta.get("strategy")
    if not strategy:
        errors.append("strategy missing from params and meta")

    if "tp_sl_mode" in meta and meta["tp_sl_mode"] is not None:
        mode = str(meta["tp_sl_mode"])
        if mode not in VALID_TP_SL_MODES:
            errors.append(
                f"meta.tp_sl_mode={mode!r} invalid (expected one of {sorted(VALID_TP_SL_MODES)})"
            )

    if "costs" in meta and meta["costs"] is not None:
        _check_costs(meta["costs"], errors)
    if "risk" in meta and meta["risk"] is not None:
        _check_risk(meta["risk"], errors)
    if "exits" in meta and meta["exits"] is not None:
        _check_exits(meta["exits"], errors)
        # Mode string and exits.mode should agree when both present
        if (
            isinstance(meta.get("exits"), dict)
            and meta.get("tp_sl_mode") is not None
            and meta["exits"].get("mode") is not None
            and str(meta["tp_sl_mode"]) != str(meta["exits"]["mode"])
        ):
            errors.append(
                f"meta.tp_sl_mode={meta['tp_sl_mode']!r} disagrees with "
                f"meta.exits.mode={meta['exits']['mode']!r}"
            )

    if "init_cash" in meta and meta["init_cash"] is not None:
        try:
            cash = float(meta["init_cash"])
            if cash <= 0:
                errors.append("meta.init_cash must be > 0")
        except (TypeError, ValueError):
            errors.append("meta.init_cash must be numeric")

    if strict:
        # costs / risk / exits shapes were already checked above when present
        for key in META_PHASE15_REQUIRED:
            if key not in meta or meta[key] in (None, ""):
                errors.append(f"strict: meta.{key} missing")

    apply_costs = meta.get("apply_costs")
    missing_metrics = [key for key in REQUIRED_METRIC_KEYS if key not in metrics]
    warnings: list[str] = []
    if apply_costs is False:
        warnings.append(
            "metrics measured with apply_costs=false (zero-cost diagnostic)"
        )
    if missing_metrics:
        warnings.append(f"metrics missing {', '.join(missing_metrics)}")
    if require_costed and apply_costs is False:
        errors.append("meta.apply_costs is false (zero-cost diagnostic)")
    if require_metrics:
        errors.extend(f"metrics.{key} missing" for key in missing_metrics)

    present_optional = [name for name in OPTIONAL_FILES if (root / name).is_file()]

    if errors:
        raise ExportSchemaError(root, errors)

    return {
        "ok": True,
        "path": str(root.resolve()),
        "schema_version": str(meta.get("schema_version")),
        "strict": strict,
        "strategy": strategy,
        "run_id": meta.get("run_id"),
        "symbol": meta.get("symbol"),
        "timeframe": meta.get("timeframe"),
        "track": meta.get("track"),
        "init_cash": meta.get("init_cash"),
        "tp_sl_mode": meta.get("tp_sl_mode"),
        "has_costs": isinstance(meta.get("costs"), dict),
        "has_risk": isinstance(meta.get("risk"), dict),
        "has_exits": isinstance(meta.get("exits"), dict),
        "optional_files": present_optional,
        "apply_costs": apply_costs,
        "missing_metric_keys": missing_metrics,
        "warnings": warnings,
        "metric_keys": sorted(metrics.keys()),
        "param_keys": sorted(params.keys()),
        "meta": meta,
        "params": params,
        "metrics": metrics,
    }
