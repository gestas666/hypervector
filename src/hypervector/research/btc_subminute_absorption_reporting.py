"""After-cost reporting and preregistered disposition for BTC absorption."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

import pandas as pd

from hypervector.research.btc_subminute_absorption_replay import (
    BtcAbsorptionReplayReport,
)


_SCENARIOS = (
    "nominal_midpoint_stop_proxy",
    "latency_and_slippage_stress",
    "public_trade_stop_proxy",
)
_EVALUATION_PARTITIONS = ("validation", "pseudo_holdout")
_CANDIDATE = "sell_flow_absorption_candidate"
_CONTROL = "extreme_sell_uptrend_control"
_UNRECONCILED_REASONS = frozenset(
    {
        "outcome_path_incomplete",
        "funding_book_unavailable",
        "exit_book_unavailable",
        "exit_visible_depth_incomplete",
        "unknown_replay_rejection",
    }
)


def summarize_btc_absorption_replay(
    signals: pd.DataFrame,
    report: BtcAbsorptionReplayReport,
    partition: str,
    arm: str,
    scenario: str,
) -> dict[str, object]:
    """Return one complete partition-arm-scenario result row."""
    times = pd.DatetimeIndex(pd.to_datetime(signals["available_at_utc"], utc=True))
    trades = report.trades
    net = _numeric(trades, "net_pnl_usd")
    positive, negative, gross_profit, gross_loss = _pnl_parts(net)
    return {
        "partition": partition,
        "arm": arm,
        "scenario": scenario,
        "signal_count": len(signals),
        "attempted_signals": report.attempted_signals,
        "completed_trades": len(trades),
        "wins": len(positive),
        "losses": len(negative),
        "target_exits": _exit_count(trades, "fixed_target"),
        "stop_exits": _exit_count(trades, "protective_stop_proxy"),
        "maximum_hold_exits": _exit_count(trades, "maximum_hold"),
        "gross_pnl_usd": float(_numeric(trades, "gross_pnl_usd").sum()),
        "fees_usd": float(_numeric(trades, "fee_usd").sum()),
        "funding_usd": float(_numeric(trades, "funding_usd").sum()),
        "net_pnl_usd": float(net.sum()),
        "net_expectancy_bps": _mean_or_none(_numeric(trades, "net_return_bps")),
        "profit_factor": None if gross_loss == 0.0 else gross_profit / gross_loss,
        "profit_factor_unbounded": gross_profit > 0.0 and gross_loss == 0.0,
        "maximum_drawdown_pct": _maximum_drawdown_pct(net),
        "net_pnl_excluding_largest_winner_usd": _without_largest_winner(net),
        "median_interarrival_hours": _median_interarrival_hours(times),
        "events_per_week": _events_per_week(times),
        "monthly_event_counts": _monthly_counts(times),
        "entry_capacity_rejections": report.rejections.get(
            "entry_visible_depth_incomplete", 0
        ),
        "entry_book_rejections": report.rejections.get("entry_book_unavailable", 0),
        "symbol_occupancy_rejections": report.rejections.get("symbol_position_open", 0),
        "unreconciled_lifecycle_paths": sum(
            count
            for reason, count in report.rejections.items()
            if reason in _UNRECONCILED_REASONS
        ),
        "rejections": dict(sorted(report.rejections.items())),
        "execution_authority": report.execution_authority,
        "orders_attempted": report.orders_attempted,
    }


def evaluate_btc_absorption_support(
    summaries: Sequence[Mapping[str, object]],
    trades: pd.DataFrame,
) -> dict[str, object]:
    """Apply every preregistered historical support requirement."""
    failed: list[str] = []
    for partition in _EVALUATION_PARTITIONS:
        for scenario in _SCENARIOS:
            candidate = _one_summary(summaries, partition, _CANDIDATE, scenario)
            control = _one_summary(summaries, partition, _CONTROL, scenario)
            if candidate is None or control is None:
                failed.append("required_result_row_missing")
                continue
            _evaluate_row(candidate, control, failed)
    concentration = _monthly_concentration(trades)
    if concentration is None:
        failed.append("monthly_concentration_unverifiable")
    elif concentration > 0.5:
        failed.append("largest_month_contribution_above_50pct")
    unique = sorted(set(failed))
    supported = not unique
    return {
        "supported": supported,
        "failed_requirements": unique,
        "largest_month_net_contribution_fraction": concentration,
        "disposition": (
            "report_only_supported_not_live_ready"
            if supported
            else "reject_exact_candidate_without_retuning"
        ),
        "automatic_live_change": False,
        "execution_authority": "none",
    }


def _evaluate_row(
    candidate: Mapping[str, object],
    control: Mapping[str, object],
    failed: list[str],
) -> None:
    if _integer(candidate, "completed_trades") < 13:
        failed.append("candidate_completed_trades_below_13")
    if _number(candidate, "net_pnl_usd") <= 0.0:
        failed.append("candidate_net_pnl_not_positive")
    if not _profitable(candidate):
        failed.append("candidate_profit_factor_not_above_one")
    if _number(candidate, "net_pnl_excluding_largest_winner_usd") <= 0.0:
        failed.append("candidate_largest_winner_removal_not_positive")
    candidate_expectancy = _optional_number(candidate, "net_expectancy_bps")
    control_expectancy = _optional_number(control, "net_expectancy_bps")
    if (
        candidate_expectancy is None
        or control_expectancy is None
        or candidate_expectancy <= control_expectancy
    ):
        failed.append("candidate_expectancy_not_above_control")
    if _integer(candidate, "unreconciled_lifecycle_paths") != 0:
        failed.append("candidate_has_unreconciled_lifecycle_paths")


def _one_summary(
    summaries: Sequence[Mapping[str, object]],
    partition: str,
    arm: str,
    scenario: str,
) -> Mapping[str, object] | None:
    rows = [
        row
        for row in summaries
        if row.get("partition") == partition
        and row.get("arm") == arm
        and row.get("scenario") == scenario
    ]
    if len(rows) > 1:
        raise ValueError("BTC absorption summary identity is duplicated")
    return rows[0] if rows else None


def _monthly_concentration(trades: pd.DataFrame) -> float | None:
    required = {"partition", "arm", "scenario", "exit_time_ms", "net_pnl_usd"}
    if trades.empty or not required.issubset(trades.columns):
        return None
    selected = trades.loc[
        trades["partition"].isin(_EVALUATION_PARTITIONS) & trades["arm"].eq(_CANDIDATE)
    ].copy()
    if selected.empty:
        return None
    selected["month"] = pd.to_datetime(
        selected["exit_time_ms"], unit="ms", utc=True
    ).dt.strftime("%Y-%m")
    monthly = selected.groupby(["scenario", "month"])["net_pnl_usd"].sum()
    fractions: list[float] = []
    for scenario in _SCENARIOS:
        values = monthly.loc[scenario] if scenario in monthly.index.levels[0] else None
        if values is None or float(values.sum()) <= 0.0:
            return None
        fractions.append(float(values.max()) / float(values.sum()))
    return max(fractions)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if column not in frame:
        raise ValueError(f"BTC absorption trades missing reporting column: {column}")
    output = pd.to_numeric(frame[column], errors="raise").astype(float)
    if not output.map(math.isfinite).all():
        raise ValueError(f"BTC absorption trade {column} must be finite")
    return output


def _pnl_parts(
    net: pd.Series,
) -> tuple[pd.Series, pd.Series, float, float]:
    positive, negative = net[net > 0.0], net[net <= 0.0]
    return positive, negative, float(positive.sum()), float(-negative.sum())


def _exit_count(trades: pd.DataFrame, reason: str) -> int:
    return 0 if trades.empty else int(trades["exit_reason"].eq(reason).sum())


def _maximum_drawdown_pct(net: pd.Series) -> float:
    if net.empty:
        return 0.0
    equity = 5_000.0 + net.cumsum()
    peaks = pd.concat([pd.Series([5_000.0]), equity]).cummax().iloc[1:]
    return float(
        ((peaks.to_numpy() - equity.to_numpy()) / peaks.to_numpy()).max() * 100.0
    )


def _without_largest_winner(net: pd.Series) -> float:
    positive = net.loc[net > 0.0]
    return float(net.sum() - (positive.max() if not positive.empty else 0.0))


def _median_interarrival_hours(times: pd.DatetimeIndex) -> float | None:
    if len(times) < 2:
        return None
    return float(pd.Series(times).diff().dt.total_seconds().dropna().median() / 3_600.0)


def _events_per_week(times: pd.DatetimeIndex) -> float | None:
    median = _median_interarrival_hours(times)
    return None if median is None or median <= 0.0 else 168.0 / median


def _monthly_counts(times: pd.DatetimeIndex) -> dict[str, int]:
    if times.empty:
        return {}
    months = pd.Series(times.strftime("%Y-%m"))
    return {
        str(key): int(value)
        for key, value in months.value_counts().sort_index().items()
    }


def _mean_or_none(values: pd.Series) -> float | None:
    return None if values.empty else float(values.mean())


def _profitable(row: Mapping[str, object]) -> bool:
    factor = _optional_number(row, "profit_factor")
    return (
        factor is not None
        and factor > 1.0
        or row.get("profit_factor_unbounded") is True
    )


def _number(row: Mapping[str, object], key: str) -> float:
    value = _optional_number(row, key)
    if value is None:
        raise ValueError(f"BTC absorption summary {key} must be numeric")
    return value


def _optional_number(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"BTC absorption summary {key} must be finite")
    return numeric


def _integer(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"BTC absorption summary {key} must be an integer")
    return value
