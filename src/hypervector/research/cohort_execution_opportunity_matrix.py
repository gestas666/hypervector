"""Fixed cross-portfolio matrix for executable exact-one-blocker opportunities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from hypervector.research.cohort_live_audit_values import nonnegative_int, number
from hypervector.research.cohort_one_blocker_execution_feasibility import (
    OneBlockerExecutionContract,
    OpiCohort,
    build_one_blocker_execution_feasibility,
)
from hypervector.research.cohort_signal_candidates import evaluation_candidates

Record = Mapping[str, object]
Pair = tuple[str, str]
Hypothesis = tuple[str, str, str]
_OPI_COHORTS: tuple[OpiCohort, ...] = ("aligned", "opposed", "all")


@dataclass(frozen=True)
class ProviderReplaySettings:
    """Configured notional, entry delay, and stop proxy for one provider-symbol."""

    maximum_entry_delay_ms: int
    notional_usd: float
    stop_proxy_bps: float

    def __post_init__(self) -> None:
        """Reject settings that cannot represent the deployed provider contract."""
        if (
            isinstance(self.maximum_entry_delay_ms, bool)
            or not isinstance(self.maximum_entry_delay_ms, int)
            or self.maximum_entry_delay_ms < 1
        ):
            raise ValueError("maximum entry delay must be a positive integer")
        for value, label in (
            (self.notional_usd, "notional"),
            (self.stop_proxy_bps, "stop proxy"),
        ):
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{label} must be positive and finite")


def build_execution_opportunity_matrix(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    funding_rows: Mapping[str, Sequence[Record]],
    *,
    settings_by_pair: Mapping[Pair, ProviderReplaySettings],
    horizon_minutes: int = 60,
    taker_fee_rate: float = 0.000432,
    maximum_context_age_ms: int = 30_000,
    maximum_exit_delay_ms: int = 30_000,
) -> dict[str, object]:
    """Compare executable blocker hypotheses under three fixed OPI cohorts."""
    observed_hypotheses = _hypotheses(cohort_records)
    hypotheses = tuple(
        hypothesis
        for hypothesis in observed_hypotheses
        if hypothesis[:2] in settings_by_pair
    )
    excluded = tuple(
        hypothesis
        for hypothesis in observed_hypotheses
        if hypothesis[:2] not in settings_by_pair
    )
    results = _comparison_results(
        hypotheses,
        cohort_records,
        asset_records,
        funding_rows,
        settings_by_pair,
        horizon_minutes,
        taker_fee_rate,
        maximum_context_age_ms,
        maximum_exit_delay_ms,
    )
    return _matrix_report(
        observed_hypotheses, hypotheses, excluded, results, horizon_minutes
    )


def _comparison_results(
    hypotheses: Sequence[Hypothesis],
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    funding_rows: Mapping[str, Sequence[Record]],
    settings_by_pair: Mapping[Pair, ProviderReplaySettings],
    horizon_minutes: int,
    taker_fee_rate: float,
    maximum_context_age_ms: int,
    maximum_exit_delay_ms: int,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for strategy_id, symbol, blocker in hypotheses:
        settings = settings_by_pair[(strategy_id, symbol)]
        if symbol not in asset_records or symbol not in funding_rows:
            raise ValueError(f"missing asset or funding evidence for {symbol}")
        for cohort in _OPI_COHORTS:
            report = build_one_blocker_execution_feasibility(
                cohort_records,
                {symbol: asset_records[symbol]},
                funding_rows[symbol],
                contract=_contract(
                    strategy_id,
                    symbol,
                    blocker,
                    cohort,
                    settings,
                    horizon_minutes,
                    taker_fee_rate,
                    maximum_context_age_ms,
                    maximum_exit_delay_ms,
                ),
            )
            results.append(_comparison(report, strategy_id, symbol, blocker, cohort))
    return results


def _matrix_report(
    observed: Sequence[Hypothesis],
    hypotheses: Sequence[Hypothesis],
    excluded: Sequence[Hypothesis],
    results: Sequence[dict[str, object]],
    horizon_minutes: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "cohort_execution_opportunity_matrix",
        "contract": {
            "report_only": True,
            "execution_authority": "none",
            "live_strategy_changed": False,
            "portfolio_pnl_claimed": False,
            "thresholds_fitted": False,
            "horizon_minutes": horizon_minutes,
            "opi_cohorts": list(_OPI_COHORTS),
            "comparisons_are_not_additive": True,
        },
        "hypotheses": len(hypotheses),
        "comparisons": len(results),
        "scope": _hypothesis_scope(observed, hypotheses, excluded),
        "results": list(results),
        "limitations": [
            "observe-only hypotheses are attributed in scope and excluded from replay",
            "aligned, opposed, and all cohorts overlap and cannot be pooled as PnL",
            "each blocker relaxation is a separate descriptive hypothesis",
            "small and one-sided samples do not establish repeatable edge",
            "BBO replay remains an estimate rather than proof of an IOC fill",
        ],
    }


def _hypothesis_scope(
    observed: Sequence[Hypothesis],
    executable: Sequence[Hypothesis],
    excluded: Sequence[Hypothesis],
) -> dict[str, object]:
    return {
        "observed_hypotheses": len(observed),
        "executable_hypotheses": len(executable),
        "excluded_non_executable_hypotheses": [
            {"strategy_id": strategy_id, "symbol": symbol, "blocker": blocker}
            for strategy_id, symbol, blocker in excluded
        ],
    }


def _hypotheses(records: Sequence[Record]) -> tuple[Hypothesis, ...]:
    candidates, _, _ = evaluation_candidates(records)
    return tuple(
        sorted(
            {
                (candidate.strategy_id, candidate.symbol, candidate.blockers[0])
                for candidate in candidates
                if candidate.side in {"long", "short"}
                and not candidate.eligible
                and len(candidate.blockers) == 1
            }
        )
    )


def _contract(
    strategy_id: str,
    symbol: str,
    blocker: str,
    cohort: OpiCohort,
    settings: ProviderReplaySettings,
    horizon_minutes: int,
    taker_fee_rate: float,
    maximum_context_age_ms: int,
    maximum_exit_delay_ms: int,
) -> OneBlockerExecutionContract:
    return OneBlockerExecutionContract(
        strategy_id=strategy_id,
        symbol=symbol,
        blocker=blocker,
        horizon_minutes=horizon_minutes,
        maximum_context_age_ms=maximum_context_age_ms,
        maximum_entry_delay_ms=settings.maximum_entry_delay_ms,
        maximum_exit_delay_ms=maximum_exit_delay_ms,
        notional_usd=settings.notional_usd,
        taker_fee_rate=taker_fee_rate,
        stop_proxy_bps=settings.stop_proxy_bps,
        opi_cohort=cohort,
    )


def _comparison(
    report: Mapping[str, object],
    strategy_id: str,
    symbol: str,
    blocker: str,
    cohort: OpiCohort,
) -> dict[str, object]:
    sides = _mapping(report.get("by_side"), "by-side result")
    long = _mapping(sides.get("long"), "long result")
    short = _mapping(sides.get("short"), "short result")
    executions = _records(report.get("executions"), "executions")
    net = [number(row.get("net_return_bps"), "net return") for row in executions]
    entry_times = [
        nonnegative_int(row.get("entry_time_ms"), "entry time") for row in executions
    ]
    exit_times = [
        nonnegative_int(row.get("exit_time_ms"), "exit time") for row in executions
    ]
    resolved = len(net)
    total = sum(net)
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "blocker": blocker,
        "opi_cohort": cohort,
        "resolved": resolved,
        "wins": sum(value > 0.0 for value in net),
        "losses": sum(value < 0.0 for value in net),
        "total_net_return_bps": total,
        "net_return_excluding_largest_winner_bps": (_net_excluding_largest_winner(net)),
        "mean_net_return_bps": total / resolved if resolved else None,
        "first_entry_time_ms": min(entry_times) if entry_times else None,
        "last_exit_time_ms": max(exit_times) if exit_times else None,
        "profit_factor": _profit_factor(net),
        "largest_abs_contribution_fraction": _concentration(net),
        "stop_proxy_crosses": sum(
            bool(row.get("crossed_stop_proxy")) for row in executions
        ),
        "long": dict(long),
        "short": dict(short),
        "coverage": dict(_mapping(report.get("coverage"), "coverage")),
    }


def _profit_factor(values: Sequence[float]) -> float | None:
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    return gains / losses if losses else None


def _concentration(values: Sequence[float]) -> float | None:
    absolute = sum(abs(value) for value in values)
    return (
        max((abs(value) for value in values), default=0.0) / absolute
        if absolute
        else None
    )


def _net_excluding_largest_winner(values: Sequence[float]) -> float | None:
    if not values:
        return None
    largest_winner = max((value for value in values if value > 0.0), default=0.0)
    return sum(values) - largest_winner


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError(f"{label} rows must be mappings")
    return tuple(row for row in value if isinstance(row, Mapping))
