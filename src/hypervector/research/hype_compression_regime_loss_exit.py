"""Fixed-entry HYPE compression regime-loss exit comparisons."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from typing import TYPE_CHECKING, Sequence

import pandas as pd

from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_regime_loss_exit_policy import (
    RegimeLossExitObservation,
    evaluate_regime_loss_exit,
)
from hypervector.research.cohort_regime_loss_exit_economics import (
    regime_loss_exit_policy_id,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitReplayConfig,
    HypeExitTrade,
)

if TYPE_CHECKING:
    from hypervector.research.hype_compression_regime_loss_study import (
        HypeCompressionRegimeLossStudy,
    )


@dataclass(frozen=True)
class FixedLifecycleRegimeLossExit:
    """One paired control-versus-candidate lifecycle result."""

    policy_triggered: bool
    candidate_applied: bool
    candidate_disposition: str
    trigger_decision_time_utc: str | None
    candidate_exit_time_utc: str
    candidate_exit_price: float
    candidate_funding_bps: float
    actual_net_return_bps: float
    candidate_net_return_bps: float


@dataclass(frozen=True)
class FixedRegimeLossComparison:
    """Paired lifecycle report and exact rows for one frozen exit policy."""

    report: dict[str, object]
    trade_rows: pd.DataFrame


def build_hype_compression_regime_loss_study(
    development: pd.DataFrame,
    confirmation_segments: tuple[pd.DataFrame, ...],
    *,
    frozen_compression_policy_id: str,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> HypeCompressionRegimeLossStudy:
    """Build the single frozen transferred-policy study without live authority."""
    from hypervector.research.hype_compression_regime_loss_study import (
        build_hype_compression_regime_loss_study as build_study,
    )

    return build_study(
        development,
        confirmation_segments,
        frozen_compression_policy_id=frozen_compression_policy_id,
        config=config,
        fold_count=fold_count,
    )


def replay_fixed_lifecycle_regime_loss_exit(
    market: pd.DataFrame,
    control: HypeExitTrade,
    config: HypeExitReplayConfig,
    *,
    loss_threshold_bps: float,
    persistence_decisions: int,
) -> FixedLifecycleRegimeLossExit:
    """Apply one causal exit to a frozen control lifecycle without reallocating."""
    entry_position, actual_exit_position = _lifecycle_positions(market, control)
    observations = _observations(
        market,
        control,
        entry_position,
        actual_exit_position,
    )
    result = evaluate_regime_loss_exit(
        side=control.side,
        entry_price=control.entry_price,
        observations=observations,
        loss_threshold_bps=loss_threshold_bps,
        persistence_decisions=persistence_decisions,
    )
    trigger_position = _trigger_position(market, result.trigger_decision_time_ms)
    applies = trigger_position is not None and trigger_position < actual_exit_position
    if not applies:
        return _retained_control(control, result.trigger_decision_time_ms)
    return _candidate_result(
        market,
        control,
        config,
        entry_position,
        trigger_position,
        result.trigger_decision_time_ms,
    )


def compare_fixed_regime_loss_exits(
    market: pd.DataFrame,
    controls: Sequence[HypeExitTrade],
    config: HypeExitReplayConfig,
    *,
    loss_threshold_bps: float,
    persistence_decisions: int,
    fold_count: int,
) -> FixedRegimeLossComparison:
    """Compare paired exits while holding entry identities and capital use fixed."""
    ordered = tuple(sorted(controls, key=lambda trade: trade.entry_time_utc))
    _validate_comparison(ordered, fold_count)
    results = tuple(
        replay_fixed_lifecycle_regime_loss_exit(
            market,
            control,
            config,
            loss_threshold_bps=loss_threshold_bps,
            persistence_decisions=persistence_decisions,
        )
        for control in ordered
    )
    rows = pd.DataFrame(
        [
            {
                "side": control.side,
                "signal_time_utc": control.signal_time_utc,
                "entry_time_utc": control.entry_time_utc,
                "actual_exit_time_utc": control.exit_time_utc,
                "actual_exit_reason": control.exit_reason,
                **asdict(result),
            }
            for control, result in zip(ordered, results, strict=True)
        ]
    )
    report = _comparison_report(
        results,
        loss_threshold_bps,
        persistence_decisions,
        fold_count,
    )
    return FixedRegimeLossComparison(report, rows)


def combine_fixed_regime_loss_comparisons(
    comparisons: Sequence[FixedRegimeLossComparison],
    *,
    loss_threshold_bps: float,
    persistence_decisions: int,
    fold_count: int,
) -> FixedRegimeLossComparison:
    """Combine disjoint continuous-segment results without changing identities."""
    if not comparisons:
        raise ValueError("HYPE regime-loss combination requires comparisons")
    rows = pd.concat([item.trade_rows for item in comparisons], ignore_index=True)
    names = tuple(field.name for field in fields(FixedLifecycleRegimeLossExit))
    results = tuple(
        FixedLifecycleRegimeLossExit(**{name: row[name] for name in names})
        for _, row in rows.iterrows()
    )
    _validate_comparison_rows(results, fold_count)
    report = _comparison_report(
        results,
        loss_threshold_bps,
        persistence_decisions,
        fold_count,
    )
    return FixedRegimeLossComparison(report, rows)


def _comparison_report(
    results: Sequence[FixedLifecycleRegimeLossExit],
    threshold: float,
    persistence: int,
    fold_count: int,
) -> dict[str, object]:
    actual = [result.actual_net_return_bps for result in results]
    candidate = [result.candidate_net_return_bps for result in results]
    candidate_metrics = _return_metrics(candidate)
    actual_metrics = _return_metrics(actual)
    return {
        "schema_version": 1,
        "mode": "hype_compression_fixed_entry_regime_loss_exit_v1",
        "execution_authority": "none",
        "policy_id": regime_loss_exit_policy_id(persistence, threshold),
        "loss_threshold_bps": threshold,
        "persistence_decisions": persistence,
        "entry_lifecycles": len(results),
        "candidate_applied_lifecycles": sum(
            result.candidate_applied for result in results
        ),
        "actual": actual_metrics,
        "candidate": candidate_metrics,
        "candidate_minus_actual_net_bps": (
            float(candidate_metrics["net_return_bps"])
            - float(actual_metrics["net_return_bps"])
        ),
        "fold_candidate_minus_actual_net_bps": _fold_deltas(
            actual, candidate, fold_count
        ),
        "capital_reallocation_modeled": False,
    }


def _return_metrics(values: Sequence[float]) -> dict[str, object]:
    profits = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value <= 0.0)
    largest = max((value for value in values if value > 0.0), default=0.0)
    return {
        "net_return_bps": sum(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value <= 0.0 for value in values),
        "profit_factor": profits / losses if losses else None,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "without_largest_winner_net_bps": sum(values) - largest,
    }


def _maximum_drawdown(values: Sequence[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _fold_deltas(
    actual: Sequence[float], candidate: Sequence[float], fold_count: int
) -> list[float]:
    boundaries = [len(actual) * fold // fold_count for fold in range(fold_count + 1)]
    return [
        sum(candidate[start:end]) - sum(actual[start:end])
        for start, end in zip(boundaries[:-1], boundaries[1:], strict=True)
    ]


def _validate_comparison(controls: Sequence[HypeExitTrade], fold_count: int) -> None:
    if not controls:
        raise ValueError("HYPE regime-loss comparison requires control lifecycles")
    if isinstance(fold_count, bool) or not isinstance(fold_count, int):
        raise TypeError("HYPE regime-loss fold count must be an integer")
    if not 1 <= fold_count <= len(controls):
        raise ValueError("HYPE regime-loss fold count must fit control lifecycles")


def _validate_comparison_rows(
    results: Sequence[FixedLifecycleRegimeLossExit], fold_count: int
) -> None:
    if not results:
        raise ValueError("HYPE regime-loss combination requires lifecycle rows")
    if not 1 <= fold_count <= len(results):
        raise ValueError("HYPE combined fold count must fit lifecycle rows")


def _observations(
    market: pd.DataFrame,
    control: HypeExitTrade,
    entry_position: int,
    actual_exit_position: int,
) -> tuple[RegimeLossExitObservation, ...]:
    rows: list[RegimeLossExitObservation] = []
    for completed_position in range(entry_position, actual_exit_position):
        next_position = completed_position + 1
        rows.append(
            RegimeLossExitObservation(
                decision_time_ms=_timestamp_ms(market.index[next_position]),
                completed_close_price=float(market["close"].iloc[completed_position]),
                next_open_price=float(market["open"].iloc[next_position]),
                structure_support_score=_support_score(
                    market.iloc[completed_position], control.side
                ),
            )
        )
    return tuple(rows)


def _support_score(row: pd.Series, side: str) -> float | None:
    structural = row["structural_direction"]
    readiness = {"metrics": {"structural_direction": structural}}
    provider = {
        "status": "observed",
        "primary_regime": row["state_5m"],
        "readiness": readiness,
    }
    canonical = provider | {
        "state_1m": row["state_1m"],
        "state_5m": row["state_5m"],
        "context_15m": row["context_15m"],
    }
    assessment = build_regime_assessment(
        side,
        {"signal_provider": provider, "canonical_regime": canonical},
    )
    value = assessment["structure_support_score"]
    return None if value is None else float(value)


def _candidate_result(
    market: pd.DataFrame,
    control: HypeExitTrade,
    config: HypeExitReplayConfig,
    entry_position: int,
    exit_position: int,
    trigger_ms: int | None,
) -> FixedLifecycleRegimeLossExit:
    raw_exit = float(market["open"].iloc[exit_position])
    exit_price = _adverse_exit(raw_exit, control.side, config.slippage_bps_per_side)
    direction = 1.0 if control.side == "long" else -1.0
    gross = direction * (exit_price / control.entry_price - 1.0) * 10_000.0
    fees = config.fee_bps_per_side * (1.0 + exit_price / control.entry_price)
    funding = _funding_bps(
        market,
        control,
        entry_position,
        exit_position,
    )
    return FixedLifecycleRegimeLossExit(
        True,
        True,
        "candidate_exit_applied",
        _timestamp(trigger_ms),
        market.index[exit_position].isoformat(),
        exit_price,
        funding,
        control.net_return_bps,
        gross - fees + funding,
    )


def _funding_bps(
    market: pd.DataFrame,
    control: HypeExitTrade,
    entry_position: int,
    exit_position: int,
) -> float:
    direction = 1.0 if control.side == "long" else -1.0
    total = 0.0
    for position in range(entry_position + 1, exit_position + 1):
        rate = float(market["funding_rate"].iloc[position])
        mark_ratio = float(market["open"].iloc[position]) / control.entry_price
        total += -direction * rate * mark_ratio * 10_000.0
    return total


def _retained_control(
    control: HypeExitTrade,
    trigger_ms: int | None,
) -> FixedLifecycleRegimeLossExit:
    return FixedLifecycleRegimeLossExit(
        trigger_ms is not None,
        False,
        (
            "actual_exit_precedes_or_coincides"
            if trigger_ms is not None
            else "policy_not_triggered"
        ),
        _timestamp(trigger_ms),
        control.exit_time_utc,
        control.exit_price,
        control.funding_bps,
        control.net_return_bps,
        control.net_return_bps,
    )


def _lifecycle_positions(
    market: pd.DataFrame,
    control: HypeExitTrade,
) -> tuple[int, int]:
    _validate_market(market)
    entry = pd.Timestamp(control.entry_time_utc)
    exit_time = pd.Timestamp(control.exit_time_utc)
    try:
        entry_position = int(market.index.get_loc(entry))
        exit_position = int(market.index.get_loc(exit_time))
    except KeyError as error:
        raise ValueError(
            "HYPE control lifecycle timestamp is absent from market"
        ) from error
    if exit_position <= entry_position:
        raise ValueError("HYPE control exit must follow its entry")
    return entry_position, exit_position


def _validate_market(market: pd.DataFrame) -> None:
    required = {
        "open",
        "close",
        "funding_rate",
        "state_1m",
        "state_5m",
        "context_15m",
        "structural_direction",
    }
    missing = sorted(required.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE regime-loss market missing columns: {missing}")
    if not isinstance(market.index, pd.DatetimeIndex) or market.index.tz is None:
        raise ValueError("HYPE regime-loss market requires an aware DatetimeIndex")
    if market.index.has_duplicates or not market.index.is_monotonic_increasing:
        raise ValueError("HYPE regime-loss market index must be ordered and unique")
    if not market.index.to_series().diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("HYPE regime-loss market requires exact one-minute cadence")


def _trigger_position(market: pd.DataFrame, trigger_ms: int | None) -> int | None:
    if trigger_ms is None:
        return None
    timestamp = pd.Timestamp(trigger_ms, unit="ms", tz="UTC")
    try:
        return int(market.index.get_loc(timestamp))
    except KeyError as error:
        raise ValueError("HYPE regime-loss trigger is absent from market") from error


def _adverse_exit(price: float, side: str, slippage_bps: float) -> float:
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("HYPE regime-loss exit price must be positive and finite")
    fraction = slippage_bps / 10_000.0
    return price * (1.0 - fraction if side == "long" else 1.0 + fraction)


def _timestamp_ms(value: pd.Timestamp) -> int:
    return int(value.to_datetime64().astype("datetime64[ms]").astype("int64"))


def _timestamp(value: int | None) -> str | None:
    return (
        None if value is None else pd.Timestamp(value, unit="ms", tz="UTC").isoformat()
    )
