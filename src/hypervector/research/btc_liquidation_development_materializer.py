"""Development-only episode economics for BTC liquidation candidates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from hypervector.data.hl_funding_evidence import HlFundingEvidence
from hypervector.research.btc_liquidation_covariate_models import (
    BookSnapshot,
    EntryAssessment,
    FundingAdjustedHorizon,
    FundingSettlement,
    HorizonReplay,
    PublicTrade,
    ReplayEpisode,
)
from hypervector.research.btc_liquidation_covariate_replay import (
    apply_long_funding,
    evaluate_entry,
    replay_outcomes,
)
from hypervector.research.btc_liquidation_regime_evidence import (
    select_regime_at_decision,
)


@dataclass(frozen=True)
class DevelopmentEpisodeReplay:
    """One development entry assessment and its frozen economic outcomes."""

    entry: EntryAssessment
    outcomes: tuple[FundingAdjustedHorizon, ...]
    regime: dict[str, object]


def funding_settlements(
    evidence: HlFundingEvidence,
) -> tuple[FundingSettlement, ...]:
    """Convert verified official numeric rows into exact replay settlements."""
    settlements: list[FundingSettlement] = []
    for row in evidence.rows:
        if row.get("source") != "hl_funding_history":
            raise ValueError("development funding row is not official evidence")
        event_time = row.get("event_ts_ms")
        rate = row.get("funding_rate")
        if isinstance(event_time, bool) or not isinstance(event_time, int):
            raise ValueError("development funding timestamp must be an integer")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise ValueError("development funding rate must be numeric")
        settlements.append(FundingSettlement(event_time, Decimal(str(rate))))
    times = tuple(row.event_time_ms for row in settlements)
    if any(left >= right for left, right in zip(times, times[1:])):
        raise ValueError("development funding settlements must be ordered and unique")
    return tuple(settlements)


def evaluate_development_episode(
    episode: ReplayEpisode,
    *,
    trades: tuple[PublicTrade, ...],
    books: tuple[BookSnapshot, ...],
    funding: HlFundingEvidence,
    settlements: tuple[FundingSettlement, ...],
    regime_labels: pd.DataFrame,
    horizons_ms: tuple[int, ...],
) -> DevelopmentEpisodeReplay:
    """Evaluate one episode using frozen causal entry and outcome semantics."""
    if episode.partition != "development":
        raise ValueError("economic materializer accepts development episodes only")
    entry = evaluate_entry(episode, trades=trades, books=books)
    regime = select_regime_at_decision(
        regime_labels,
        pd.Timestamp(entry.decision_time_ms, unit="ms", tz="UTC"),
    )
    if entry.status != "eligible" or entry.decision_book_time_ms is None:
        return DevelopmentEpisodeReplay(entry, (), regime)
    outcomes = replay_outcomes(entry, books=books, horizons_ms=horizons_ms)
    adjusted = tuple(
        _apply_funding(row, entry.decision_book_time_ms, settlements, funding)
        for row in outcomes
    )
    return DevelopmentEpisodeReplay(entry, adjusted, regime)


def _apply_funding(
    outcome: HorizonReplay,
    entry_time_ms: int,
    settlements: tuple[FundingSettlement, ...],
    evidence: HlFundingEvidence,
) -> FundingAdjustedHorizon:
    if outcome.status == "resolved":
        if outcome.exit_book_time_ms is None:
            raise ValueError("resolved development outcome has no exit timestamp")
        evidence.require_covers(entry_time_ms, outcome.exit_book_time_ms)
    return apply_long_funding(
        outcome,
        entry_time_ms=entry_time_ms,
        settlements=settlements,
    )
