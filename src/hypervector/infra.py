"""Local data layout: raw evidence, DuckDB research, and runtime separation.

All runtime paths hang off a configurable data root (default ``./data``).
Never mix paper and live ledgers. DuckDB is analytical, not a live event bus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Relative subdirs under data root (I2 + Phase 2/3 paper prep)
DATA_SUBDIRS: tuple[str, ...] = (
    "cache",
    "cache/book",
    "cache/events/hyperliquid",
    "cache/vendor/0xarchive",
    "research",
    "runs",
    "exports",
    "logs/research",
    "logs/nautilus",
    "nautilus/backtest",
    "paper/ledger",
    "paper/decisions",
    "live",
    "live/ledger",
    "live/decisions",
    "models/metalabel",
)


@dataclass(frozen=True)
class DataPaths:
    """Resolved paths for a data root."""

    root: Path
    cache: Path
    cache_book: Path
    cache_events_hyperliquid: Path
    cache_vendor_0xarchive: Path
    research: Path
    research_db: Path
    runs: Path
    runs_db: Path
    exports: Path
    logs_research: Path
    logs_nautilus: Path
    nautilus_backtest: Path
    paper_ledger: Path
    paper_decisions: Path
    paper_db: Path
    live: Path
    live_ledger: Path
    live_decisions: Path
    models_metalabel: Path


def paths_for(root: Path | str) -> DataPaths:
    """Return path constants for ``root`` without creating directories."""
    r = Path(root)
    return DataPaths(
        root=r,
        cache=r / "cache",
        cache_book=r / "cache" / "book",
        cache_events_hyperliquid=r / "cache" / "events" / "hyperliquid",
        cache_vendor_0xarchive=r / "cache" / "vendor" / "0xarchive",
        research=r / "research",
        research_db=r / "research" / "market.duckdb",
        runs=r / "runs",
        runs_db=r / "runs" / "hypervector.db",
        exports=r / "exports",
        logs_research=r / "logs" / "research",
        logs_nautilus=r / "logs" / "nautilus",
        nautilus_backtest=r / "nautilus" / "backtest",
        paper_ledger=r / "paper" / "ledger",
        paper_decisions=r / "paper" / "decisions",
        paper_db=r / "paper" / "paper.db",
        live=r / "live",
        live_ledger=r / "live" / "ledger",
        live_decisions=r / "live" / "decisions",
        models_metalabel=r / "models" / "metalabel",
    )


def ensure_data_layout(root: Path | str) -> DataPaths:
    """Idempotently create the I2 + paper/live/nautilus directory tree."""
    paths = paths_for(root)
    paths.root.mkdir(parents=True, exist_ok=True)
    for rel in DATA_SUBDIRS:
        (paths.root / rel).mkdir(parents=True, exist_ok=True)
    return paths


def layout_report(root: Path | str) -> dict[str, object]:
    """JSON-serializable status of layout (exists flags)."""
    paths = paths_for(root)
    dirs = {
        "cache": paths.cache,
        "cache_events_hyperliquid": paths.cache_events_hyperliquid,
        "cache_vendor_0xarchive": paths.cache_vendor_0xarchive,
        "research": paths.research,
        "runs": paths.runs,
        "exports": paths.exports,
        "logs_research": paths.logs_research,
        "logs_nautilus": paths.logs_nautilus,
        "nautilus_backtest": paths.nautilus_backtest,
        "paper_ledger": paths.paper_ledger,
        "paper_decisions": paths.paper_decisions,
        "live": paths.live,
        "live_ledger": paths.live_ledger,
        "live_decisions": paths.live_decisions,
        "models_metalabel": paths.models_metalabel,
    }
    return {
        "root": str(paths.root.resolve()),
        "dirs": {k: {"path": str(p), "exists": p.is_dir()} for k, p in dirs.items()},
        "runs_db": str(paths.runs_db),
        "research_db": str(paths.research_db),
        "paper_db": str(paths.paper_db),
        "rules": {
            "paper_live_separated": True,
            "gitignored_data": True,
            "no_postgres_redis_k8s": True,
        },
    }
