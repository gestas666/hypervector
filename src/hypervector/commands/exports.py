"""Strategy bundle references, bundle inventory and stored-trial selection.

Engine-free on purpose: only the standard library, the export schema and the
CLI's refusal type are imported, so ``export list`` and ``export show`` never
load pandas or an engine. Nothing here creates a directory.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
from typing import Any

from hypervector.commands.common import CommandRefused
from hypervector.export.schema import ExportSchemaError, validate_export_dir

LATEST = "latest"
EXPORTS_DIR = "exports"
METALABEL_DIR = Path("models") / "metalabel"
# Files Metalabeler.from_root needs: the booster and its feature names.
METALABEL_REQUIRED_FILES: tuple[str, ...] = (
    "metalabel_lgbm.txt",
    "metalabel_metadata.json",
)
TRIAL_METRICS: tuple[str, ...] = (
    "net_pnl",
    "total_return_pct",
    "sharpe",
    "trade_count",
    "wins",
    "losses",
    "win_pct",
    "max_drawdown",
)


# --- references -----------------------------------------------------------------


def resolve_export(ref: str | Path, data_root: Path | str) -> Path:
    """Resolve ``--export REF`` to an absolute strategy bundle directory.

    Order: an existing directory (absolute or relative to cwd); ``latest``, the
    newest strictly valid bundle under ``<root>/exports``; a candidate id under
    ``<root>/exports``. Anything else is a refusal (exit 2) naming every place
    that was searched.
    """
    return _resolve_reference(
        ref,
        Path(data_root) / EXPORTS_DIR,
        kind="strategy bundle",
        latest=latest_export,
        latest_rule="passes strict validation",
    )


def resolve_metalabel_bundle(ref: str | Path, data_root: Path | str) -> Path:
    """Resolve ``--metalabel-bundle REF`` under ``<root>/models/metalabel``.

    Same order as :func:`resolve_export`. The resolved directory must hold the
    files the metalabel loader expects, else the reference is refused.
    """
    root = Path(data_root) / METALABEL_DIR
    bundle = _resolve_reference(
        ref,
        root,
        kind="metalabel bundle",
        latest=latest_metalabel_bundle,
        latest_rule=f"holds {' and '.join(METALABEL_REQUIRED_FILES)}",
    )
    missing = [
        name for name in METALABEL_REQUIRED_FILES if not (bundle / name).is_file()
    ]
    if missing:
        raise CommandRefused(
            f"metalabel bundle {bundle} is missing {', '.join(missing)}"
        )
    return bundle


def _resolve_reference(
    ref: str | Path,
    root: Path,
    *,
    kind: str,
    latest: Callable[[Path], Path | None],
    latest_rule: str,
) -> Path:
    text = str(ref).strip()
    if not text:
        raise CommandRefused(f"empty {kind} reference")
    direct = Path(text).expanduser()
    if direct.is_dir():
        return direct.resolve()
    looked = [f"directory {direct.resolve()}"]
    if text == LATEST:
        chosen = latest(root)
        if chosen is not None:
            return chosen.resolve()
        looked.append(f"'latest' under {root} (newest bundle that {latest_rule})")
    elif _is_plain_name(name := text.rstrip("/" + os.sep)):
        # 'export_uptrend_1/' (shell completion) names the same candidate id.
        candidate = root / name
        if candidate.is_dir():
            return candidate.resolve()
        looked.append(f"candidate id {candidate}")
    raise CommandRefused(
        f"{kind} reference {text!r} not found; looked for " + "; ".join(looked)
    )


def _is_plain_name(text: str) -> bool:
    return Path(text).name == text and text not in (".", "..")


def latest_export(exports_root: Path) -> Path | None:
    """The newest bundle under ``exports_root`` that passes strict validation."""
    valid = [
        entry
        for entry in _bundle_dirs(exports_root)
        if _strict_report(entry)[0] is not None
    ]
    return _newest(valid, _export_recency)


def latest_metalabel_bundle(models_root: Path) -> Path | None:
    """The newest model bundle under ``models_root`` (or the installed root itself)."""
    candidates = [models_root, *_bundle_dirs(models_root)]
    usable = [
        path
        for path in candidates
        if all((path / name).is_file() for name in METALABEL_REQUIRED_FILES)
    ]
    return _newest(usable, _metalabel_recency)


def _bundle_dirs(root: Path) -> list[Path]:
    """Bundle directories; hidden ones (``.staging-*`` exports in flight) are not."""
    if not root.is_dir():
        return []
    return sorted(
        entry
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def _newest(paths: Sequence[Path], recency: Callable[[Path], float]) -> Path | None:
    """Most recent by recency key, ties broken by name (last name wins)."""
    if not paths:
        return None
    return max(paths, key=lambda path: (recency(path), path.name))


def _export_recency(path: Path) -> float:
    stamp = _parse_utc(_read_object(path / "meta.json").get("created_at_utc"))
    return stamp.timestamp() if stamp is not None else _mtime(path)


def _metalabel_recency(path: Path) -> float:
    return _mtime(path / METALABEL_REQUIRED_FILES[0])


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _read_object(path: Path) -> dict[str, Any]:
    """A JSON object file read leniently (inventory never fails on one bundle)."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _strict_report(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        return validate_export_dir(path, strict=True), []
    except ExportSchemaError as exc:
        return None, list(exc.errors)


# --- inventory --------------------------------------------------------------------


def bundle_summary(path: Path) -> dict[str, Any]:
    """One inventory entry; invalid bundles are described, never hidden."""
    report, errors = _strict_report(path)
    meta = report["meta"] if report else _read_object(path / "meta.json")
    params = report["params"] if report else _read_object(path / "params.json")
    created = _parse_utc(meta.get("created_at_utc"))
    if created is None:
        created = datetime.fromtimestamp(_mtime(path), tz=UTC)
    return {
        "candidate_id": path.name,
        "export_dir": str(path.resolve()),
        "strategy": params.get("strategy") or meta.get("strategy"),
        "symbol": meta.get("symbol"),
        "timeframe": meta.get("timeframe"),
        "track": meta.get("track"),
        "created_at_utc": created.isoformat(timespec="seconds"),
        "strict_valid": report is not None,
        "errors": errors,
    }


def list_exports(
    data_root: Path | str,
    *,
    strategy: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[dict[str, Any]]:
    """Every bundle under ``<root>/exports``, newest first, optionally filtered."""
    entries = []
    for path in _bundle_dirs(Path(data_root) / EXPORTS_DIR):
        entry = bundle_summary(path)
        wanted = (
            ("strategy", strategy),
            ("symbol", symbol),
            ("timeframe", timeframe),
        )
        if all(value is None or entry[key] == value for key, value in wanted):
            entries.append((_export_recency(path), path.name, entry))
    entries.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [entry for _, _, entry in entries]


def cmd_list(args: argparse.Namespace) -> int:
    """List strategy bundles with their strict validity (read-only)."""
    root = Path(args.data_root) / EXPORTS_DIR
    entries = list_exports(
        args.data_root,
        strategy=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    report = {
        "ok": True,
        "exports_dir": str(root.resolve()),
        "count": len(entries),
        "invalid_count": sum(not entry["strict_valid"] for entry in entries),
        "exports": entries,
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show one bundle's meta, params, metrics and strict validation (read-only)."""
    path = resolve_export(args.export, args.data_root)
    report, errors = _strict_report(path)
    summary = bundle_summary(path)
    out = {
        "ok": True,
        "candidate_id": path.name,
        "export_dir": str(path),
        "strict_valid": report is not None,
        "validation": {"strict": True, "valid": report is not None, "errors": errors},
        "meta": report["meta"] if report else _read_object(path / "meta.json"),
        "params": report["params"] if report else _read_object(path / "params.json"),
        "metrics": report["metrics"] if report else _read_object(path / "metrics.json"),
        "created_at_utc": summary["created_at_utc"],
        "optional_files": report["optional_files"] if report else [],
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


# --- stored trial selection -------------------------------------------------------


def select_export_trial(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_id: str | None = None,
    track: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any] | None:
    """Pick the stored sweep trial to publish as a bundle.

    Only measured ``ok`` trials that carry ``research_meta`` (costs, risk, exits,
    cash) and match every given filter are eligible. The best by net PnL, then
    total return, wins; trials with costs applied are preferred so a
    ``--no-costs`` diagnostic never becomes the export. Weak or negative results
    stay eligible: selection is a ranking, not a gate.
    """
    ready = [
        dict(row)
        for row in rows
        if row.get("status") == "ok"
        and isinstance(row.get("research_meta"), dict)
        and row["research_meta"]
        and trial_matches(
            row,
            run_id=run_id,
            track=track,
            strategy=strategy,
            symbol=symbol,
            timeframe=timeframe,
        )
    ]
    ready.sort(key=_trial_rank)
    costed = [row for row in ready if costs_applied(row)]
    if costed:
        return costed[0]
    return ready[0] if ready else None


def trial_matches(
    row: Mapping[str, Any],
    *,
    run_id: str | None = None,
    track: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> bool:
    """True when a stored trial matches every given filter (symbol/timeframe from meta)."""
    meta = row.get("research_meta") or {}
    if not isinstance(meta, Mapping):
        meta = {}
    checks = (
        (run_id, row.get("run_id")),
        (track, row.get("track")),
        (strategy, row.get("strategy")),
        (symbol, row.get("symbol", meta.get("symbol"))),
        (timeframe, row.get("timeframe", meta.get("timeframe"))),
    )
    return all(
        wanted is None or (actual is not None and str(actual) == str(wanted))
        for wanted, actual in checks
    )


def explain_no_export_trial(
    rows: Sequence[Mapping[str, Any]], filters: Mapping[str, object]
) -> str:
    """Why selection found nothing: no rows, no filter match, or no research_meta."""
    given = {key: value for key, value in filters.items() if value is not None}
    described = ", ".join(f"{key}={value}" for key, value in given.items()) or "none"
    matching = [row for row in rows if trial_matches(row, **given)]  # type: ignore[arg-type]
    if not rows:
        return "no stored sweep trials; run 'backtest sweep' first"
    if not matching:
        return f"no stored sweep trial matches the filters ({described})"
    if any(row.get("status") == "ok" for row in matching):
        return (
            "ok trials exist but none have research_meta "
            "(costs/risk/exits/cash); re-run 'backtest sweep' "
            "so the bundle configuration is stored"
        )
    return f"no ok trials to export (filters: {described})"


def costs_applied(row: Mapping[str, Any]) -> bool:
    """Whether a stored trial was measured with fees and slippage applied."""
    meta = row.get("research_meta") or {}
    if "apply_costs" in meta:
        return bool(meta["apply_costs"])
    # Rows without the flag: a zero fee model or zero taker fee is diagnostic-only.
    if meta.get("fee_model") == "zero":
        return False
    costs = meta.get("costs") or {}
    try:
        return float(costs.get("taker_fee", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def _trial_rank(row: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        -_number(row.get("net_pnl")),
        -_number(row.get("total_return_pct")),
        _number(row.get("id"), default=math.inf),
    )


def _number(value: object, *, default: float = -math.inf) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) else number
