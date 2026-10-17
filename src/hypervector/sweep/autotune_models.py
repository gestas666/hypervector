"""Search configuration and public result contracts."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutotuneResult:
    strategy_name: str
    symbol: str
    timeframe: str
    lookback_days: int
    n_trials: int
    sampler_used: str
    best_params: dict[str, object]
    best_exit_cfg: dict[str, object]
    best_metrics: dict[str, object]
    export_dir: Path | None
    board_path: Path


@dataclass(frozen=True)
class SearchSettings:
    """One explicitly configured bounded research search."""

    root: Path
    strategy_name: str
    symbol: str
    timeframe: str
    lookback_days: int
    n_trials: int
    fee_model: str
    book_data_path: str | Path | None
    sampler: str
    no_export: bool
    apply_penalties: bool
    strict_hl_only: bool
    force_refresh: bool
