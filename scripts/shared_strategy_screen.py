"""Predeclared BTC strategy screen through one causal shared portfolio."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_api import validate_symbol
from hypervector.data.oxa_storage import write_immutable_json
from hypervector.research.apex_directional_signals import (
    build_apex_breakout_entries,
    build_apex_ensemble_entries,
    build_apex_trend_entries,
)
from hypervector.research.shared_bar_portfolio import evaluate_shared_bar_portfolio
from hypervector.research.shared_hypervelocity_signals import (
    build_hypervelocity_event_signals,
    hypervelocity_portfolio_config,
)
from hypervector.research.shared_portfolio_models import (
    SharedPortfolioConfig,
    SharedPortfolioReport,
    SharedPortfolioTrade,
)
from hypervector.research.shared_strategy_signals import (
    build_registered_strategy_pair_signals,
)

_VENUE_MAX_LEVERAGE = {"BTC": 40.0, "ETH": 25.0, "SOL": 20.0, "HYPE": 10.0}


@dataclass(frozen=True)
class ScreenProfile:
    """One predeclared sizing and price-barrier screening hypothesis."""

    name: str
    margin_fraction: float
    leverage: float
    target_bps: float | None
    stop_bps: float | None
    max_hold_minutes: int | None


@dataclass(frozen=True)
class CandidatePair:
    """One registered long/short architecture pair."""

    name: str
    long_strategy: str | None
    short_strategy: str | None


LEGACY_CANDIDATES = (
    CandidatePair("ma_cross", "ma_cross_long", "ma_cross_short"),
    CandidatePair("impulse_1m", "impulse_1m_long", "impulse_1m_short"),
    CandidatePair("crown_stack", "crown_stack_long", "crown_stack_short"),
    CandidatePair("trend_ride", "trend_ride_long", "trend_ride_short"),
    CandidatePair("pine_composite", "pine_composite_long", "pine_composite_short"),
)

SOURCE_CANDIDATES = (
    CandidatePair("donchian_trend", "donchian_trend_long", "donchian_trend_short"),
    CandidatePair(
        "squeeze_breakout", "squeeze_breakout_long", "squeeze_breakout_short"
    ),
    CandidatePair("liquidity_sweep", "liquidity_sweep_long", "liquidity_sweep_short"),
    CandidatePair(
        "zero_lag_reclaim", "zero_lag_reclaim_long", "zero_lag_reclaim_short"
    ),
    CandidatePair(
        "regime_trend_router",
        "regime_trend_router_long",
        "regime_trend_router_short",
    ),
)

SOURCE_LONG_ISOLATION_V1_CANDIDATES = tuple(
    CandidatePair(f"{candidate.name}_long", candidate.long_strategy, None)
    for candidate in SOURCE_CANDIDATES
)

SOURCE_MANAGED_V1_CANDIDATES = tuple(
    candidate
    for candidate in SOURCE_CANDIDATES
    if candidate.name in {"liquidity_sweep", "squeeze_breakout", "zero_lag_reclaim"}
)

ZERO_LAG_SHORT_MANAGED_V1_CANDIDATES = (
    CandidatePair("zero_lag_short", None, "zero_lag_reclaim_short"),
)

LIQUIDITY_SWEEP_LONG_MANAGED_V1_CANDIDATES = (
    CandidatePair("liquidity_sweep_long", "liquidity_sweep_long", None),
)

LIQUIDITY_SWEEP_LONG_WICK_V1_CANDIDATES = (
    CandidatePair("liquidity_sweep_long_wick", "liquidity_sweep_long", None),
)

REGIME_ROUTER_CANDIDATES = (SOURCE_CANDIDATES[-1],)

REGIME_ROUTER_LONG_MANAGED_V1_CANDIDATES = (
    CandidatePair(
        "regime_trend_router_long",
        "regime_trend_router_long",
        None,
    ),
)

HYPERVELOCITY_CANDIDATES = (CandidatePair("hypervelocity_control", None, None),)

HYPERVELOCITY_DIRECTION_CANDIDATES = (
    CandidatePair("hypervelocity_long_only", None, None),
    CandidatePair("hypervelocity_short_only", None, None),
)

APEX_DIRECTIONAL_CANDIDATES = (
    CandidatePair("apex_trend", "apex_trend_long", "apex_trend_short"),
    CandidatePair("apex_ensemble", "apex_ensemble_long", "apex_ensemble_short"),
    CandidatePair("apex_breakout", "apex_breakout_long", "apex_breakout_short"),
)

PROFILES = (
    ScreenProfile("scalp_20_12bps", 0.25, 10.0, 20.0, 12.0, 360),
    ScreenProfile("asymmetric_100_30bps", 0.20, 5.0, 100.0, 30.0, 1_440),
    ScreenProfile("trend_80_40bps", 0.25, 5.0, 80.0, 40.0, 1_440),
    ScreenProfile("managed_60bps_stop", 0.10, 5.0, None, 60.0, 2_880),
)

SOURCE_MANAGED_V1_PROFILES = (PROFILES[-1],)

HYPERVELOCITY_PROFILES = (
    ScreenProfile("hypervelocity_faithful", 0.70, 40.0, 20.0, None, None),
)

HYPERVELOCITY_RISK_PROFILES = (
    ScreenProfile("hypervelocity_50_30", 0.50, 30.0, 8.0 / 30.0 * 100.0, None, None),
    ScreenProfile("hypervelocity_70_30", 0.70, 30.0, 8.0 / 30.0 * 100.0, None, None),
    ScreenProfile("hypervelocity_70_40_control", 0.70, 40.0, 20.0, None, None),
)

HYPERVELOCITY_DIRECTION_PROFILES = HYPERVELOCITY_RISK_PROFILES[:2]

LIQUIDITY_SWEEP_LONG_HV_V1_PROFILES = (
    ScreenProfile(
        "hypervelocity_long_35_30_24h",
        0.35,
        30.0,
        8.0 / 30.0 * 100.0,
        None,
        1_440,
    ),
)

LIQUIDITY_SWEEP_LONG_HV_STOP60_V1_PROFILES = (
    replace(
        LIQUIDITY_SWEEP_LONG_HV_V1_PROFILES[0],
        name="hypervelocity_long_35_30_24h_stop60",
        stop_bps=60.0,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded immutable screening command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--bars", type=Path, required=True)
    parser.add_argument("--funding", type=Path, action="append", required=True)
    parser.add_argument("--start", type=_utc_datetime, required=True)
    parser.add_argument("--end", type=_utc_datetime, required=True)
    parser.add_argument(
        "--execution-timeframe",
        choices=("1min", "5min", "15min", "1h"),
        default="1min",
    )
    parser.add_argument(
        "--cohort",
        choices=(
            "legacy",
            "source",
            "source-managed-v1",
            "source-long-isolation-v1",
            "zero-lag-short-managed-v1",
            "liquidity-sweep-long-managed-v1",
            "liquidity-sweep-long-hv-v1",
            "liquidity-sweep-long-hv-wick-v1",
            "liquidity-sweep-long-hv-stop60-v1",
            "regime-router",
            "regime-router-long-managed-v1",
            "hypervelocity-control",
            "hypervelocity-risk-surface",
            "hypervelocity-direction-surface",
            "apex-directional-v1",
        ),
        default="legacy",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run_screen(
    *,
    symbol: str = "BTC",
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
    execution_timeframe: str = "1min",
    cohort: str = "legacy",
) -> dict[str, object]:
    """Evaluate the fixed candidate cohort without selecting or gating trials."""
    normalized_symbol = _supported_symbol(symbol)
    minute_bars, evidence = load_causal_window(bars_path, funding_paths, start, end)
    bars = resample_execution_bars(minute_bars, execution_timeframe)
    bar_minutes = _timeframe_minutes(execution_timeframe)
    evidence["source_minute_bar_rows"] = evidence.pop("bar_rows")
    evidence["execution_bar_rows"] = len(bars)
    evidence["symbol"] = normalized_symbol
    trials: list[dict[str, object]] = []
    candidates, profiles = _trial_design(cohort)
    for candidate in candidates:
        signals = _candidate_signals(bars, candidate)
        for profile in profiles:
            report = evaluate_shared_bar_portfolio(
                bars,
                signals,
                profile_config(
                    profile,
                    symbol=normalized_symbol,
                    bar_minutes=bar_minutes,
                ),
            )
            trials.append(_trial_summary(candidate, profile, report))
    return {
        "schema_version": 1,
        "mode": "bar_screen_only_not_executable_evidence",
        "symbol": normalized_symbol,
        "portfolio_contract": (
            f"one_shared_15000_usd_equity_one_{normalized_symbol.lower()}_position"
        ),
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "execution_timeframe": execution_timeframe,
        "cohort": cohort,
        "trial_count": len(trials),
        "selection_applied": False,
        "development_selection": _development_selection(cohort),
        "data_evidence": evidence,
        "trials": trials,
        "limitations": [
            "candidate defaults only; no parameter tuning in this pass",
            "bar results cannot establish maker fill probability or capacity",
            "the interval is development evidence and is not a pristine holdout",
        ],
    }


def _trial_design(
    cohort: str,
) -> tuple[tuple[CandidatePair, ...], tuple[ScreenProfile, ...]]:
    if cohort == "legacy":
        return LEGACY_CANDIDATES, PROFILES
    if cohort == "source":
        return SOURCE_CANDIDATES, PROFILES
    if cohort == "source-managed-v1":
        return SOURCE_MANAGED_V1_CANDIDATES, SOURCE_MANAGED_V1_PROFILES
    if cohort == "source-long-isolation-v1":
        return SOURCE_LONG_ISOLATION_V1_CANDIDATES, SOURCE_MANAGED_V1_PROFILES
    if cohort == "zero-lag-short-managed-v1":
        return ZERO_LAG_SHORT_MANAGED_V1_CANDIDATES, SOURCE_MANAGED_V1_PROFILES
    if cohort == "liquidity-sweep-long-managed-v1":
        return LIQUIDITY_SWEEP_LONG_MANAGED_V1_CANDIDATES, SOURCE_MANAGED_V1_PROFILES
    if cohort == "liquidity-sweep-long-hv-v1":
        return (
            LIQUIDITY_SWEEP_LONG_MANAGED_V1_CANDIDATES,
            LIQUIDITY_SWEEP_LONG_HV_V1_PROFILES,
        )
    if cohort == "liquidity-sweep-long-hv-wick-v1":
        return (
            LIQUIDITY_SWEEP_LONG_WICK_V1_CANDIDATES,
            LIQUIDITY_SWEEP_LONG_HV_V1_PROFILES,
        )
    if cohort == "liquidity-sweep-long-hv-stop60-v1":
        return (
            LIQUIDITY_SWEEP_LONG_MANAGED_V1_CANDIDATES,
            LIQUIDITY_SWEEP_LONG_HV_STOP60_V1_PROFILES,
        )
    if cohort == "regime-router":
        return REGIME_ROUTER_CANDIDATES, PROFILES
    if cohort == "regime-router-long-managed-v1":
        return REGIME_ROUTER_LONG_MANAGED_V1_CANDIDATES, SOURCE_MANAGED_V1_PROFILES
    if cohort == "hypervelocity-control":
        return HYPERVELOCITY_CANDIDATES, HYPERVELOCITY_PROFILES
    if cohort == "hypervelocity-risk-surface":
        return HYPERVELOCITY_CANDIDATES, HYPERVELOCITY_RISK_PROFILES
    if cohort == "hypervelocity-direction-surface":
        return HYPERVELOCITY_DIRECTION_CANDIDATES, HYPERVELOCITY_DIRECTION_PROFILES
    if cohort == "apex-directional-v1":
        return APEX_DIRECTIONAL_CANDIDATES, PROFILES
    raise ValueError(f"unknown candidate cohort: {cohort}")


def _candidate_signals(
    bars: pd.DataFrame,
    candidate: CandidatePair,
) -> pd.DataFrame:
    if candidate.name.startswith("hypervelocity_"):
        signals = build_hypervelocity_event_signals(bars)
        return _isolate_hypervelocity_direction(signals, candidate.name)
    if candidate.name.startswith("apex_"):
        return _apex_directional_signals(bars, candidate)
    signals = build_registered_strategy_pair_signals(
        bars,
        long_strategy_name=candidate.long_strategy,
        short_strategy_name=candidate.short_strategy,
    )
    if candidate.name == "liquidity_sweep_long_wick":
        return _attach_long_signal_wick_stop(bars, signals)
    return signals


def _apex_directional_signals(
    bars: pd.DataFrame,
    candidate: CandidatePair,
) -> pd.DataFrame:
    if candidate.name == "apex_trend":
        entries = build_apex_trend_entries(bars)
    elif candidate.name == "apex_ensemble":
        entries = build_apex_ensemble_entries(bars)
    elif candidate.name == "apex_breakout":
        entries = build_apex_breakout_entries(bars)
    else:
        raise ValueError(f"unknown Apex directional candidate: {candidate.name}")
    inactive = pd.Series(False, index=bars.index, dtype=bool)
    return pd.DataFrame(
        {
            "long_entry": entries["long_entry"],
            "short_entry": entries["short_entry"],
            "long_exit": inactive,
            "short_exit": inactive,
            "long_signal_name": candidate.long_strategy,
            "short_signal_name": candidate.short_strategy,
        },
        index=bars.index,
    )


def _attach_long_signal_wick_stop(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    result = signals.copy()
    result["stop_price"] = bars["low"].where(result["long_entry"])
    return result


def _isolate_hypervelocity_direction(
    signals: pd.DataFrame,
    candidate_name: str,
) -> pd.DataFrame:
    result = signals.copy()
    if candidate_name == "hypervelocity_control":
        return result
    if candidate_name == "hypervelocity_long_only":
        result["short_entry"] = False
        return result
    if candidate_name == "hypervelocity_short_only":
        result["long_entry"] = False
        return result
    raise ValueError(f"unknown Hypervelocity direction candidate: {candidate_name}")


def _development_selection(cohort: str) -> dict[str, object] | None:
    if cohort == "source-managed-v1":
        return {
            "source_artifact": (
                "data/logs/research/"
                "shared_strategy_source_development_20250728_20260128_1h_v1.json"
            ),
            "rule": "managed profile with development profit factor above 1 and no liquidation",
            "parameters_changed_after_selection": False,
        }
    if cohort == "zero-lag-short-managed-v1":
        return {
            "source_artifacts": [
                "data/logs/research/shared_strategy_source_development_"
                "20250728_20260128_1h_v1.json",
                "data/logs/research/shared_strategy_source_validation_"
                "20260128_20260428_1h_managed_v1.json",
            ],
            "rule": "only side with profit factor above 1 in development and validation",
            "parameters_changed_after_selection": False,
        }
    if cohort == "liquidity-sweep-long-managed-v1":
        return {
            "source_artifacts": [
                "data/logs/research/shared_strategy_source_development_"
                "20250728_20260128_1h_v1.json",
                "data/logs/research/shared_strategy_source_validation_"
                "20260128_20260428_1h_managed_v1.json",
            ],
            "rule": (
                "only source-managed long side with profit factor above 1 "
                "in development and validation"
            ),
            "parameters_changed_after_selection": False,
        }
    if cohort == "liquidity-sweep-long-hv-v1":
        return {
            "source_artifacts": [
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "development_20250728_20260128_1h_managed_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "validation_20260128_20260428_1h_managed_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "pseudo_holdout_20260428_20260728_1h_managed_v1.json",
            ],
            "rule": (
                "unchanged source signal challenged with the current 35%/30x/"
                "8% target and 24-hour hold contract"
            ),
            "parameters_changed_after_selection": True,
            "changed_parameters": "risk and exit contract only",
        }
    if cohort == "liquidity-sweep-long-hv-wick-v1":
        return {
            "source_artifacts": [
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "development_20250728_20260128_1h_hv35x30_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "validation_20260128_20260428_1h_hv35x30_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "pseudo_holdout_20260428_20260728_1h_hv35x30_v1.json",
            ],
            "rule": (
                "retrospective tail repair using the completed bullish sweep "
                "bar low as structural invalidation"
            ),
            "parameters_changed_after_selection": True,
            "changed_parameters": "causal signal-wick stop added after failure",
        }
    if cohort == "liquidity-sweep-long-hv-stop60-v1":
        return {
            "source_artifacts": [
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "development_20250728_20260128_1h_managed_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "validation_20260128_20260428_1h_managed_v1.json",
                "data/logs/research/shared_strategy_liquidity_sweep_long_"
                "pseudo_holdout_20260428_20260728_1h_managed_v1.json",
            ],
            "rule": (
                "unchanged signal and pre-existing 60 bps managed stop under "
                "the current 35%/30x/8% target/24-hour contract"
            ),
            "parameters_changed_after_selection": True,
            "changed_parameters": "operational risk contract combined with stop",
        }
    if cohort == "regime-router-long-managed-v1":
        return {
            "source_artifact": (
                "data/logs/research/shared_strategy_regime_router_"
                "development_20250728_20260128_1h_v1.json"
            ),
            "rule": (
                "isolate the only regime-router side with development "
                "profit factor above one under the unchanged managed profile"
            ),
            "parameters_changed_after_selection": False,
        }
    return None


def load_causal_window(
    bars_path: Path,
    funding_paths: list[Path],
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Load one gap-free bar interval with complete exact-hour funding."""
    if end <= start:
        raise ValueError("screen end must be after start")
    bars = _indexed_parquet(bars_path)
    bars = bars.loc[(bars.index >= start) & (bars.index < end)].copy()
    _validate_minute_cadence(bars, start, end)
    funding = _funding_series(funding_paths, start, end)
    bars["funding_rate"] = 0.0
    bars.loc[funding.index, "funding_rate"] = funding
    return bars, _data_evidence(bars_path, funding_paths, bars, funding)


def profile_config(
    profile: ScreenProfile,
    *,
    symbol: str = "BTC",
    bar_minutes: int = 1,
) -> SharedPortfolioConfig:
    """Translate price-basis-point barriers into leveraged margin returns."""
    normalized_symbol = _supported_symbol(symbol)
    if profile.name.startswith("hypervelocity_"):
        if normalized_symbol != "BTC":
            raise ValueError("Hypervelocity profiles are currently BTC-only")
        target_margin_pct = _margin_return_pct(profile.target_bps, profile.leverage)
        if target_margin_pct is None:
            raise ValueError("Hypervelocity profile requires a target")
        config = hypervelocity_portfolio_config(
            margin_fraction=profile.margin_fraction,
            leverage=profile.leverage,
            target_margin_pct=target_margin_pct,
        )
        return replace(
            config,
            stop_margin_pct=_margin_return_pct(profile.stop_bps, profile.leverage),
            max_hold_bars=_scaled_max_hold(profile.max_hold_minutes, bar_minutes),
        )
    return SharedPortfolioConfig(
        symbol=normalized_symbol,
        initial_equity=15_000.0,
        margin_fraction=profile.margin_fraction,
        leverage=profile.leverage,
        venue_max_leverage=_VENUE_MAX_LEVERAGE[normalized_symbol],
        target_margin_pct=_margin_return_pct(profile.target_bps, profile.leverage),
        stop_margin_pct=_margin_return_pct(profile.stop_bps, profile.leverage),
        entry_fee_rate=0.00045,
        target_fee_rate=0.00015,
        market_exit_fee_rate=0.00045,
        liquidation_fee_rate=0.00045,
        entry_slippage_bps=2.0,
        market_exit_slippage_bps=2.0,
        max_hold_bars=_scaled_max_hold(profile.max_hold_minutes, bar_minutes),
        reentry_cooldown_bars=1,
        close_on_opposite_signal=True,
        reverse_on_opposite_signal=True,
    )


def _supported_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    validate_symbol(normalized)
    if normalized not in _VENUE_MAX_LEVERAGE:
        supported = ", ".join(_VENUE_MAX_LEVERAGE)
        raise ValueError(f"screen symbol must be one of: {supported}")
    return normalized


def _margin_return_pct(target_bps: float | None, leverage: float) -> float | None:
    if target_bps is None:
        return None
    return target_bps * leverage / 100.0


def resample_execution_bars(
    bars: pd.DataFrame,
    timeframe: str,
) -> pd.DataFrame:
    """Build fully completed execution bars without forward information."""
    minutes = _timeframe_minutes(timeframe)
    if minutes == 1:
        return bars.copy()
    grouped = bars.resample(timeframe, label="left", closed="left")
    result = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        funding_rate=("funding_rate", "sum"),
    )
    complete = grouped.size().eq(minutes)
    return result.loc[complete].dropna()


def _timeframe_minutes(timeframe: str) -> int:
    delta = pd.Timedelta(timeframe)
    minute = pd.Timedelta(minutes=1)
    if delta < minute or delta % minute != pd.Timedelta(0):
        raise ValueError("execution timeframe must be whole positive minutes")
    return int(delta / minute)


def _scaled_max_hold(minutes: int | None, bar_minutes: int) -> int | None:
    if minutes is None:
        return None
    return math.ceil(minutes / bar_minutes)


def _indexed_parquet(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"screen input is missing: {path}")
    frame = pd.read_parquet(path)
    if "timestamp" not in frame:
        raise ValueError(f"screen input has no timestamp: {path}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp").sort_index()


def _validate_minute_cadence(
    bars: pd.DataFrame,
    start: datetime,
    end: datetime,
) -> None:
    expected = int((end - start).total_seconds() / 60.0)
    if len(bars) != expected or not bars.index.is_unique:
        raise ValueError("screen bar window is not complete at one-minute cadence")
    if (
        len(bars) < 2
        or bars.index.to_series().diff().iloc[1:].ne(pd.Timedelta(minutes=1)).any()
    ):
        raise ValueError("screen bar window contains a timestamp gap")


def _funding_series(
    paths: list[Path],
    start: datetime,
    end: datetime,
) -> pd.Series:
    frames = [_indexed_parquet(path) for path in paths]
    funding = pd.concat(frames).sort_index()
    if funding.index.duplicated().any():
        duplicates = funding.loc[funding.index.duplicated(keep=False), "funding_rate"]
        if duplicates.groupby(level=0).nunique().gt(1).any():
            raise ValueError("funding bundles contain conflicting duplicate rates")
        funding = funding.loc[~funding.index.duplicated(keep="first")]
    expected = pd.date_range(start, end, freq="1h", inclusive="left")
    series = funding["funding_rate"].astype(float).reindex(expected)
    if series.isna().any() or not series.map(math.isfinite).all():
        raise ValueError("screen funding is incomplete or non-finite")
    return series


def _data_evidence(
    bars_path: Path,
    funding_paths: list[Path],
    bars: pd.DataFrame,
    funding: pd.Series,
) -> dict[str, object]:
    return {
        "bars_path": str(bars_path.resolve()),
        "bars_sha256": _sha256(bars_path),
        "funding_paths": [str(path.resolve()) for path in funding_paths],
        "funding_sha256": [_sha256(path) for path in funding_paths],
        "bar_rows": len(bars),
        "gap_fill_rows": int(
            bars.get("source", pd.Series(dtype=str)).eq("hl_gap_fill").sum()
        ),
        "funding_events": len(funding),
    }


def _trial_summary(
    candidate: CandidatePair,
    profile: ScreenProfile,
    report: SharedPortfolioReport,
) -> dict[str, object]:
    report_values = report.to_dict()
    keep = (
        "final_equity",
        "net_pnl_usd",
        "return_pct",
        "maximum_drawdown_pct",
        "completed_trades",
        "wins",
        "losses",
        "gross_profit_usd",
        "gross_loss_usd",
        "profit_factor",
        "liquidations",
        "total_fees_usd",
        "funding_cashflow_usd",
        "conflicting_entry_signals",
        "forced_end_exits",
        "insolvent",
        "monthly_net_pnl_usd",
    )
    return {
        "trial_id": f"{candidate.name}__{profile.name}",
        "candidate": asdict(candidate),
        "profile": asdict(profile),
        "metrics": {key: report_values[key] for key in keep},
        "attribution": _trade_attribution(report.trades),
    }


def _trade_attribution(
    trades: tuple[SharedPortfolioTrade, ...],
) -> dict[str, object]:
    """Attribute one shared account's completed trades by side and exit reason."""
    reasons = Counter(trade.exit_reason for trade in trades)
    return {
        "long": _direction_attribution(trades, "long"),
        "short": _direction_attribution(trades, "short"),
        "exit_reasons": dict(sorted(reasons.items())),
    }


def _direction_attribution(
    trades: tuple[SharedPortfolioTrade, ...],
    direction: str,
) -> dict[str, int | float | None]:
    selected = tuple(trade for trade in trades if trade.direction == direction)
    profits = tuple(trade.net_pnl_usd for trade in selected if trade.net_pnl_usd > 0.0)
    losses = tuple(-trade.net_pnl_usd for trade in selected if trade.net_pnl_usd <= 0.0)
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    return {
        "completed_trades": len(selected),
        "wins": len(profits),
        "losses": len(losses),
        "net_pnl_usd": sum(trade.net_pnl_usd for trade in selected),
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
        "fees_usd": sum(trade.fees_usd for trade in selected),
        "funding_cashflow_usd": sum(trade.funding_cashflow_usd for trade in selected),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != pd.Timedelta(0):
        raise argparse.ArgumentTypeError("timestamps must be UTC")
    return parsed.astimezone(UTC)


def main() -> int:
    """Run the screen and publish an immutable JSON artifact."""
    args = build_parser().parse_args()
    report = run_screen(
        symbol=args.symbol,
        bars_path=args.bars,
        funding_paths=args.funding,
        start=args.start,
        end=args.end,
        execution_timeframe=args.execution_timeframe,
        cohort=args.cohort,
    )
    write_immutable_json(args.output, report)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
