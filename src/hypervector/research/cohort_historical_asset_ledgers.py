"""Read-only discovery of retired cohort asset ledgers for all-time history."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from hypervector.research.live_ledger_snapshot import (
    snapshot_compatible_execution_ledger,
    snapshot_decision_ledger,
)


def retired_asset_paths(
    ledger_root: Path,
    cohort_path: Path,
    *,
    active_symbols: tuple[str, ...],
) -> dict[str, Path]:
    """Return retired asset ledgers without granting execution authority."""
    active = {symbol.lower() for symbol in active_symbols}
    paths: dict[str, Path] = {}
    for path in sorted(ledger_root.glob("*.jsonl")):
        if path == cohort_path or path.stem.lower() in active:
            continue
        paths[_ledger_symbol(path)] = path
    return paths


def snapshot_retired_asset_ledgers(
    stack: ExitStack,
    ledger_root: Path,
    cohort_path: Path,
    *,
    active_symbols: tuple[str, ...],
    compatible_execution_history: bool,
    run_id: str,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    """Snapshot retired ledgers solely for complete all-time reporting."""
    if compatible_execution_history:
        return {}, {}
    rows: dict[str, list[dict[str, object]]] = {}
    evidence: dict[str, dict[str, object]] = {}
    paths = retired_asset_paths(ledger_root, cohort_path, active_symbols=active_symbols)
    for symbol, path in paths.items():
        source = (
            snapshot_compatible_execution_ledger(
                path, allow_incomplete_tail=True, run_id=run_id
            )
            if compatible_execution_history
            else snapshot_decision_ledger(path, allow_incomplete_tail=True)
        )
        records, facts = stack.enter_context(source)
        rows[symbol] = records
        evidence[symbol] = {"path": str(path), **facts}
    return rows, evidence


def _ledger_symbol(path: Path) -> str:
    """Recover canonical core or HIP-3 identity from a ledger filename."""
    value = path.stem
    if not value or value == "decisions":
        raise ValueError(f"invalid retired asset ledger path: {path}")
    return value.upper() if not value.startswith("xyz:") else "xyz:" + value[4:].upper()
