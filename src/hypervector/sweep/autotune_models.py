"""Search configuration and public result contracts."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

#: Ranking objectives shared by the search, the elites and the export.
OBJECTIVES: tuple[str, ...] = ("net_pnl", "score", "sharpe")
DEFAULT_OBJECTIVE = "net_pnl"
#: One seed for the Karpathy RNG and the Optuna TPE sampler, so boards and
#: code cannot drift apart.
SEARCH_SEED = 42
#: Chronological share of bars searched; the rest is the report-only holdout.
DEFAULT_TRAIN_FRACTION = 0.7
SELECTION_TRAIN_ONLY = "train_only"
SELECTION_IN_SAMPLE = "full_window_in_sample"


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
    #: Out-of-sample holdout metrics when a holdout exists, otherwise the
    #: in-sample metrics of the selected trial, labelled with
    #: ``evaluation_window`` and ``selection_basis``.
    best_metrics: dict[str, object]
    export_dir: Path | None
    board_path: Path
    objective: str = DEFAULT_OBJECTIVE
    selection_basis: str = SELECTION_IN_SAMPLE
    train_metrics: dict[str, object] = field(default_factory=dict)
    holdout_metrics: dict[str, object] | None = None
    best_trial_number: int | None = None
    best_trade_count: int | None = None
    n_trials_requested: int = 0
    space_exhausted: bool = False
    warnings: list[str] = field(default_factory=list)
    #: Fee model the trials were measured with, and the one the caller asked
    #: for; they differ only when a strategy contract overrides it.
    fee_model_used: str = ""
    fee_model_requested: str = ""


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
    strict_hl_only: bool
    force_refresh: bool
    objective: str = DEFAULT_OBJECTIVE
    train_fraction: float = 1.0
    sampler_requested: str | None = None
    #: The caller's fee model when a strategy contract replaced it
    #: (``fee_model`` is always the one used); ``None`` means no override.
    fee_model_requested: str | None = None
    #: History freshness, as ``--pin-cache`` / ``--max-cache-age-hours``:
    #: pinning serves the cached window as is (``max_cache_age=None``), hours
    #: refresh only windows older than that; neither keeps the loader default.
    pin_cache: bool = False
    max_cache_age_hours: float | None = None
    #: ``False`` keeps the history load offline (``pipeline run`` after its
    #: data stage pinned the window): stale is served as is, a miss fails.
    allow_network: bool = True

    @property
    def requested_fee_model(self) -> str:
        return self.fee_model_requested or self.fee_model
