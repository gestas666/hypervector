"""Report-only 15-minute approximation of the v25 HIP-3 lifecycle shape."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Literal

import pandas as pd

from hypervector.research.hip3_breakout_pressure_transfer import (
    quote_aware_portfolio_config,
)
from hypervector.research.hip3_swing_transfer import (
    Hip3ExecutionFriction,
    Hip3TransferAsset,
    Hip3TransferWindows,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_models import SharedPortfolioConfig
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


@dataclass(frozen=True)
class Hip3DeployedLifecycleSpec:
    """Frozen fixed-stop and completed-bar timer used by v25 HIP-3 routes."""

    stop_bps: float = 80.0
    maximum_hold_seconds: int = 86_400
    bar_minutes: int = 15
    signal_exit_policy: Literal["ignore", "honor", "early_adverse"] = "ignore"
    early_exit_max_bars: int = 8
    early_exit_max_mfe_bps: float = 20.0
    early_exit_min_adverse_bps: float = 13.0

    def __post_init__(self) -> None:
        """Reject values that cannot map exactly onto the research bar clock."""
        if not math.isfinite(self.stop_bps) or self.stop_bps <= 0.0:
            raise ValueError("HIP-3 deployed stop_bps must be positive")
        values = (self.maximum_hold_seconds, self.bar_minutes)
        if any(
            isinstance(value, bool) or not isinstance(value, int) for value in values
        ):
            raise ValueError("HIP-3 deployed timer values must be integers")
        if self.maximum_hold_seconds <= 0 or self.bar_minutes <= 0:
            raise ValueError("HIP-3 deployed timer values must be positive")
        if self.maximum_hold_seconds % (self.bar_minutes * 60):
            raise ValueError("HIP-3 deployed hold must contain whole completed bars")
        if self.signal_exit_policy not in {"ignore", "honor", "early_adverse"}:
            raise ValueError(
                "HIP-3 signal_exit_policy must be ignore, honor, or early_adverse"
            )
        if (
            isinstance(self.early_exit_max_bars, bool)
            or not isinstance(self.early_exit_max_bars, int)
            or self.early_exit_max_bars <= 0
        ):
            raise ValueError("HIP-3 early_exit_max_bars must be positive")
        for name in ("early_exit_max_mfe_bps", "early_exit_min_adverse_bps"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"HIP-3 {name} must be positive")

    @property
    def maximum_hold_bars(self) -> int:
        """Return the exact inclusive completed-bar lifecycle ceiling."""
        return self.maximum_hold_seconds // (self.bar_minutes * 60)


@dataclass(frozen=True)
class Hip3DeployedLifecycleCell:
    """One bar-level development or validation result under named friction."""

    symbol: str
    phase: str
    friction: str
    report: SharedPortfolioReport
    tail_suppressed_entries: int
    gap_crossing_trades: int
    execution_authority: str = "none"


def deployed_lifecycle_signals(
    signals: pd.DataFrame,
    *,
    spec: Hip3DeployedLifecycleSpec | None = None,
) -> pd.DataFrame:
    """Retain live entry intents and remove research-only exit/barrier metadata."""
    lifecycle = spec or Hip3DeployedLifecycleSpec()
    required = {"long_entry", "short_entry"}
    if lifecycle.signal_exit_policy != "ignore":
        required.update({"long_exit", "short_exit"})
    missing = sorted(required.difference(signals.columns))
    if missing:
        raise ValueError(f"HIP-3 deployed signals missing columns: {missing}")
    output = signals.copy()
    if lifecycle.signal_exit_policy == "ignore":
        output["long_exit"] = False
        output["short_exit"] = False
    output["stop_price"] = float("nan")
    output["target_price"] = float("nan")
    return output


def deployed_lifecycle_portfolio_config(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    *,
    stress: bool,
    spec: Hip3DeployedLifecycleSpec | None = None,
) -> SharedPortfolioConfig:
    """Map v25 fixed-stop/hold semantics onto the shared causal simulator."""
    lifecycle = spec or Hip3DeployedLifecycleSpec()
    base = quote_aware_portfolio_config(asset, friction, stress=stress)
    stop_margin_pct = lifecycle.stop_bps * base.leverage / 100.0
    conditional = lifecycle.signal_exit_policy == "early_adverse"
    return replace(
        base,
        target_margin_pct=None,
        stop_margin_pct=stop_margin_pct,
        max_hold_bars=lifecycle.maximum_hold_bars,
        same_direction_reentry_requires_reset=False,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=False,
        signal_exit_max_age_bars=(
            lifecycle.early_exit_max_bars if conditional else None
        ),
        signal_exit_max_mfe_bps=(
            lifecycle.early_exit_max_mfe_bps if conditional else None
        ),
        signal_exit_min_adverse_bps=(
            lifecycle.early_exit_min_adverse_bps if conditional else None
        ),
    )


def evaluate_deployed_lifecycle(
    asset: Hip3TransferAsset,
    friction: Hip3ExecutionFriction,
    signals: pd.DataFrame,
    windows: Hip3TransferWindows,
    *,
    spec: Hip3DeployedLifecycleSpec | None = None,
) -> tuple[Hip3DeployedLifecycleCell, ...]:
    """Approximate the live shape without reading the sealed holdout window."""
    if not asset.bars.index.equals(signals.index):
        raise ValueError("HIP-3 deployed bars and signals require the same index")
    lifecycle = spec or Hip3DeployedLifecycleSpec()
    deployed = deployed_lifecycle_signals(signals, spec=lifecycle)
    phases = (
        ("development", windows.development_start_utc, windows.development_end_utc),
        ("validation", windows.development_end_utc, windows.validation_end_utc),
    )
    cells: list[Hip3DeployedLifecycleCell] = []
    for phase, start, end in phases:
        selected = asset.bars.index.to_series().ge(start)
        selected &= asset.bars.index.to_series().lt(end)
        bars = asset.bars.loc[selected].copy()
        phase_signals = deployed.loc[selected].copy()
        if len(bars) < 2:
            raise ValueError(f"HIP-3 deployed {phase} requires at least two bars")
        suppressed = _suppress_unresolved_tail_entries(
            phase_signals,
            end=end,
            spec=lifecycle,
        )
        for stress in (False, True):
            config = deployed_lifecycle_portfolio_config(
                asset,
                friction,
                stress=stress,
                spec=lifecycle,
            )
            report = evaluate_shared_bar_portfolio(bars, phase_signals, config)
            cells.append(
                Hip3DeployedLifecycleCell(
                    asset.symbol,
                    phase,
                    "stress" if stress else "nominal",
                    report,
                    suppressed,
                    _gap_crossing_trade_count(report, bars),
                )
            )
    return tuple(cells)


def _suppress_unresolved_tail_entries(
    signals: pd.DataFrame,
    *,
    end: pd.Timestamp,
    spec: Hip3DeployedLifecycleSpec,
) -> int:
    cutoff = (
        end
        - pd.Timedelta(seconds=spec.maximum_hold_seconds)
        - pd.Timedelta(minutes=spec.bar_minutes)
    )
    tail = signals.index.to_series().ge(cutoff)
    entries = signals.loc[tail, ["long_entry", "short_entry"]]
    suppressed = int(entries.to_numpy(dtype=bool).sum())
    signals.loc[tail, ["long_entry", "short_entry"]] = False
    return suppressed


def _gap_crossing_trade_count(
    report: SharedPortfolioReport,
    bars: pd.DataFrame,
) -> int:
    if "gap_before_bars" not in bars:
        return 0
    gaps = bars["gap_before_bars"].astype(int)
    return sum(
        int(gaps.iloc[trade.entry_position + 1 : trade.exit_position + 1].sum() > 0)
        for trade in report.trades
    )
