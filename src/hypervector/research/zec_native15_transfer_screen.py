"""Preregistered native fifteen-minute ZEC strategy-transfer screen."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from hypervector.research.causal_screen_inputs import load_causal_bar_window
from hypervector.research.fixed_risk_signal_screen import (
    DEFAULT_PROFILES,
    FrictionProfile,
    scored_inputs,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_portfolio_attribution import trade_attribution
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
)
from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_signals,
)

Direction = Literal["long", "short"]
ConfigBuilder = Callable[[FrictionProfile], SharedPortfolioConfig]
SupportGate = Callable[[Mapping[str, object]], bool]

HYPOTHESIS_ID = "v81-zec-native15-managed-transfer-20260903"
MINIMUM_COMPLETED_TRADES = 12
MAXIMUM_DRAWDOWN_PCT = 5.0


@dataclass(frozen=True)
class CandidateContract:
    """One immutable source-derived family-side transfer."""

    candidate_id: str
    strategy_name: str
    direction: Direction

    def __post_init__(self) -> None:
        """Reject aliases or side mismatches in the frozen candidate inventory."""
        suffix = f"_{self.direction}"
        if not self.candidate_id or self.candidate_id != self.strategy_name:
            raise ValueError("candidate ID must equal its registered strategy name")
        if not self.strategy_name.endswith(suffix):
            raise ValueError("candidate strategy and direction do not match")


_CANDIDATES = tuple(
    CandidateContract(f"{family}_{direction}", f"{family}_{direction}", direction)
    for family in (
        "squeeze_breakout",
        "liquidity_sweep",
        "zero_lag_reclaim",
        "regime_trend_router",
    )
    for direction in ("long", "short")
)


def candidate_contracts() -> tuple[CandidateContract, ...]:
    """Return the exact preregistered candidate inventory in stable order."""
    return _CANDIDATES


def resolve_candidates(
    candidate_ids: Sequence[str] | None,
) -> tuple[CandidateContract, ...]:
    """Resolve an optional survivor subset without allowing aliases or repeats."""
    if candidate_ids is None:
        return candidate_contracts()
    requested = tuple(candidate_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("candidate selection contains a duplicate candidate")
    known = {candidate.candidate_id for candidate in _CANDIDATES}
    unknown = sorted(set(requested).difference(known))
    if unknown:
        raise ValueError(f"unknown candidate selection: {', '.join(unknown)}")
    return tuple(row for row in _CANDIDATES if row.candidate_id in requested)


def portfolio_config(profile: FrictionProfile) -> SharedPortfolioConfig:
    """Return the exact V81 small-probation risk and friction contract."""
    return SharedPortfolioConfig(
        symbol="ZEC",
        initial_equity=5_000.0,
        margin_fraction=0.02,
        leverage=5.0,
        venue_max_leverage=10.0,
        maximum_notional_usd=500.0,
        stop_margin_pct=3.0,
        entry_fee_rate=0.00045,
        target_fee_rate=0.00045,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=profile.slippage_bps,
        market_exit_slippage_bps=profile.slippage_bps,
        max_hold_bars=192,
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=False,
    )


def profile_supported(metrics: Mapping[str, object]) -> bool:
    """Apply every preregistered per-profile support criterion."""
    completed = _integer_metric(metrics, "completed_trades")
    net = _float_metric(metrics, "net_pnl_usd")
    raw_profit_factor = metrics.get("profit_factor")
    profit_factor = (
        None if raw_profit_factor is None else _float_metric(metrics, "profit_factor")
    )
    ex_largest = _float_metric(metrics, "net_excluding_largest_winner_usd")
    drawdown = _float_metric(metrics, "maximum_drawdown_pct")
    liquidations = _integer_metric(metrics, "liquidations")
    insolvent = metrics.get("insolvent")
    if not isinstance(insolvent, bool):
        raise TypeError("profile metric insolvent must be a boolean")
    return bool(
        completed >= MINIMUM_COMPLETED_TRADES
        and net > 0.0
        and profit_factor is not None
        and profit_factor > 1.0
        and ex_largest > 0.0
        and drawdown >= -MAXIMUM_DRAWDOWN_PCT
        and liquidations == 0
        and not insolvent
    )


def run_partition_screen(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
    candidate_ids: Sequence[str] | None = None,
) -> dict[str, object]:
    """Evaluate one opened chronological partition without execution authority."""
    return run_managed_transfer_partition(
        bars_path=bars_path,
        funding_paths=funding_paths,
        source_start=source_start,
        score_start=score_start,
        end=end,
        partition=partition,
        candidate_ids=candidate_ids,
        config_builder=portfolio_config,
        hypothesis_id=HYPOTHESIS_ID,
        mode="v81_zec_native15_managed_transfer_report_only",
    )


def run_managed_transfer_partition(
    *,
    bars_path: Path,
    funding_paths: list[Path],
    source_start: datetime,
    score_start: datetime,
    end: datetime,
    partition: str,
    candidate_ids: Sequence[str] | None,
    config_builder: ConfigBuilder,
    hypothesis_id: str,
    mode: str,
) -> dict[str, object]:
    """Evaluate a frozen candidate subset and managed risk contract."""
    bars, evidence = load_causal_bar_window(
        bars_path,
        funding_paths,
        source_start,
        end,
        bar_timeframe="15min",
    )
    candidates = resolve_candidates(candidate_ids)
    results = tuple(
        _candidate_report(bars, score_start, candidate, config_builder)
        for candidate in candidates
    )
    return {
        "schema_version": 1,
        "mode": mode,
        "hypothesis_id": hypothesis_id,
        "partition": partition,
        "source_start_utc": source_start.isoformat(),
        "start_utc": score_start.isoformat(),
        "end_exclusive_utc": end.isoformat(),
        "execution_timeframe": "15min",
        "data_evidence": evidence,
        "candidate_count": len(results),
        "candidates": list(results),
        "supported_candidate_ids": [
            row["candidate"]["candidate_id"]
            for row in results
            if row["supported_in_partition"]
        ],
        "execution_authority": "none",
        "automatic_live_change": False,
    }


def _candidate_report(
    bars: pd.DataFrame,
    score_start: datetime,
    candidate: CandidateContract,
    config_builder: ConfigBuilder,
) -> dict[str, object]:
    signals = _candidate_signals(bars, candidate)
    scored_bars, scored_signals = scored_inputs(bars, signals, score_start)
    profiles = tuple(
        build_profile_report(
            profile,
            candidate.direction,
            evaluate_shared_bar_portfolio(
                scored_bars,
                scored_signals,
                config_builder(profile),
            ),
            profile_supported,
        )
        for profile in DEFAULT_PROFILES
    )
    return {
        "candidate": asdict(candidate),
        "signal_count": int(scored_signals[f"{candidate.direction}_entry"].sum()),
        "profiles": list(profiles),
        "supported_in_partition": all(row["supported"] for row in profiles),
    }


def _candidate_signals(
    bars: pd.DataFrame,
    candidate: CandidateContract,
) -> pd.DataFrame:
    long_name = candidate.strategy_name if candidate.direction == "long" else None
    short_name = candidate.strategy_name if candidate.direction == "short" else None
    return build_registered_strategy_pair_signals(
        bars,
        long_strategy_name=long_name,
        short_strategy_name=short_name,
    )


def build_profile_report(
    profile: FrictionProfile,
    direction: Direction,
    report: SharedPortfolioReport,
    support_gate: SupportGate,
) -> dict[str, object]:
    """Project one portfolio report through a caller-supplied evidence gate."""
    values = report.to_dict()
    attribution = trade_attribution(report.trades)[direction]
    largest = float(attribution["largest_winner_usd"] or 0.0)
    metrics = {
        "completed_trades": values["completed_trades"],
        "wins": values["wins"],
        "losses": values["losses"],
        "net_pnl_usd": values["net_pnl_usd"],
        "profit_factor": values["profit_factor"],
        "net_excluding_largest_winner_usd": report.net_pnl_usd - largest,
        "maximum_drawdown_pct": values["maximum_drawdown_pct"],
        "liquidations": values["liquidations"],
        "total_fees_usd": values["total_fees_usd"],
        "funding_cashflow_usd": values["funding_cashflow_usd"],
        "insolvent": values["insolvent"],
        "monthly_net_pnl_usd": values["monthly_net_pnl_usd"],
    }
    return {
        "friction": asdict(profile),
        "metrics": metrics,
        "attribution": attribution,
        "supported": support_gate(metrics),
    }


def _integer_metric(metrics: Mapping[str, object], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"profile metric {key} must be an integer")
    return value


def _float_metric(metrics: Mapping[str, object], key: str) -> float:
    value = metrics.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"profile metric {key} must be numeric")
    return float(value)
