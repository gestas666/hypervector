"""Strict summaries for executable-BBO eligible-signal markouts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median

from hypervector.research.cohort_eligible_signal_markout_models import (
    ExecutableMarkout,
    MarkoutEvidence,
)

_LATEST_MARKOUT_LIMIT = 20
_STANCES = ("aligned", "neutral", "opposed", "unavailable")
_SIDES = ("long", "short")


def summarize_executable_markouts(
    evidence: Mapping[int, MarkoutEvidence],
    horizons: Sequence[int],
    maximum_book_lateness_ms: int,
    provider_cadence_minutes: int | None,
) -> dict[str, object]:
    """Return report-only BBO outcomes with episode-effective counts."""
    outcomes = [item for horizon in horizons for item in evidence[horizon].outcomes]
    return {
        "contract": _contract(),
        "maximum_book_lateness_ms": maximum_book_lateness_ms,
        "horizons": {
            str(horizon): _horizon_summary(
                evidence[horizon],
                horizon,
                provider_cadence_minutes,
            )
            for horizon in horizons
        },
        "latest_markouts": [
            dict(vars(item))
            for item in sorted(
                outcomes,
                key=lambda value: (value.entry_book_time_ms, value.horizon_minutes),
            )[-_LATEST_MARKOUT_LIMIT:]
        ],
    }


def _horizon_summary(
    evidence: MarkoutEvidence,
    horizon_minutes: int,
    provider_cadence_minutes: int | None,
) -> dict[str, object]:
    independent = _non_overlapping(evidence.outcomes, horizon_minutes)
    return {
        "coverage": evidence.coverage.as_payload(),
        "independent_resolved": len(independent),
        "all": _group_summary(independent),
        "by_side": _grouped(independent, "side", _SIDES),
        "by_pressure_stance": _grouped(independent, "pressure_stance", _STANCES),
        "by_state_5m_stance": _grouped(independent, "state_5m_stance", _STANCES),
        "by_context_15m_stance": _grouped(independent, "context_15m_stance", _STANCES),
        "episode_onsets": _episode_summary(
            evidence,
            horizon_minutes,
            provider_cadence_minutes,
        ),
    }


def _episode_summary(
    evidence: MarkoutEvidence,
    horizon_minutes: int,
    provider_cadence_minutes: int | None,
) -> dict[str, object]:
    if provider_cadence_minutes is None:
        return {
            "status": "unavailable",
            "provider_cadence_minutes": None,
            "reason": "provider cadence was not supplied",
        }
    outcomes = [item for item in evidence.outcomes if item.episode_onset is True]
    independent = _non_overlapping(outcomes, horizon_minutes)
    return {
        "status": "available",
        "provider_cadence_minutes": provider_cadence_minutes,
        "coverage": evidence.episode_coverage.as_payload(),
        "independent_resolved": len(independent),
        "independent_paths": [dict(vars(item)) for item in independent],
        "all": _group_summary(independent),
        "by_side": _grouped(independent, "side", _SIDES),
        "by_pressure_stance": _grouped(independent, "pressure_stance", _STANCES),
        "by_state_5m_stance": _grouped(independent, "state_5m_stance", _STANCES),
        "by_context_15m_stance": _grouped(independent, "context_15m_stance", _STANCES),
    }


def _non_overlapping(
    outcomes: Sequence[ExecutableMarkout], horizon_minutes: int
) -> tuple[ExecutableMarkout, ...]:
    selected: list[ExecutableMarkout] = []
    next_available = -1
    for outcome in sorted(outcomes, key=lambda value: value.entry_book_time_ms):
        if outcome.entry_book_time_ms < next_available:
            continue
        selected.append(outcome)
        next_available = outcome.entry_book_time_ms + horizon_minutes * 60_000
    return tuple(selected)


def _grouped(
    outcomes: Sequence[ExecutableMarkout],
    name: str,
    categories: Sequence[str],
) -> dict[str, object]:
    return {
        category: _group_summary(
            [item for item in outcomes if getattr(item, name) == category]
        )
        for category in categories
    }


def _group_summary(outcomes: Sequence[ExecutableMarkout]) -> dict[str, object]:
    gross = [item.gross_bbo_bps for item in outcomes]
    fees = [item.after_fee_bps for item in outcomes if item.after_fee_bps is not None]
    modeled = [
        item.after_modeled_friction_bps
        for item in outcomes
        if item.after_modeled_friction_bps is not None
    ]
    positive = sum(value > 0.0 for value in modeled)
    return {
        "paths": len(outcomes),
        "friction_complete_paths": len(modeled),
        "mean_gross_bbo_bps": _mean(gross),
        "median_gross_bbo_bps": _median(gross),
        "mean_after_fee_bps": _mean(fees),
        "median_after_fee_bps": _median(fees),
        "mean_after_modeled_friction_bps": _mean(modeled),
        "median_after_modeled_friction_bps": _median(modeled),
        "minimum_after_modeled_friction_bps": min(modeled) if modeled else None,
        "maximum_after_modeled_friction_bps": max(modeled) if modeled else None,
        "positive_after_modeled_friction_count": positive,
        "positive_after_modeled_friction_rate": positive / len(modeled)
        if modeled
        else None,
        "mean_excluding_largest_after_modeled_friction_bps": (
            (sum(modeled) - max(modeled)) / (len(modeled) - 1)
            if len(modeled) > 1
            else None
        ),
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "pnl_claimed": False,
        "entry_anchor": "first_book_at_or_after_signal_publication",
        "exit_anchor": "first_book_at_or_after_entry_plus_horizon",
        "entry_liquidity": "taker_bbo_cross",
        "exit_liquidity": "taker_bbo_cross",
        "funding_included": False,
        "thresholds_selected": False,
        "episode_cadence_source": "explicit_provider_timeframe_mapping",
        "episode_onset_definition": (
            "first_signal_after_gap_direction_change_or_stream_boundary"
        ),
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(median(values)) if values else None
