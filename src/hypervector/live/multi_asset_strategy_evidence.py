"""Report-only research evidence bound to cohort provider-symbol mappings."""

from __future__ import annotations

from hypervector.live.multi_asset_live_config import StrategyProviderConfig
from hypervector.live.multi_asset_strategy_evidence_models import (
    StrategyResearchEvidence,
)

# Accepted evidence keyed by (strategy_id, symbol). Empty until a profile's
# research is reviewed; every unlisted mapping reports as unreviewed.
_EVIDENCE: dict[tuple[str, str], StrategyResearchEvidence] = {}


def strategy_evidence_payloads(
    providers: tuple[StrategyProviderConfig, ...],
) -> list[dict[str, object]]:
    """Cover every configured mapping without changing its execution scope."""
    records = [
        strategy_research_evidence(provider.strategy_id, symbol)
        for provider in providers
        for symbol in provider.symbols
    ]
    return [record.as_payload() for record in records]


def strategy_research_evidence(
    strategy_id: str,
    symbol: str,
) -> StrategyResearchEvidence:
    """Return explicit evidence or an equally explicit unreviewed record."""
    return _EVIDENCE.get((strategy_id, symbol)) or _unreviewed(strategy_id, symbol)


def _unreviewed(strategy_id: str, symbol: str) -> StrategyResearchEvidence:
    return StrategyResearchEvidence(
        strategy_id,
        symbol,
        "unreviewed_exact_mapping",
        "low",
        "not established for this exact provider-symbol mapping",
        "No accepted matched outcome record is bound to this exact mapping; "
        "execution eligibility is an operator scope choice, not evidence of edge.",
        "none",
    )
