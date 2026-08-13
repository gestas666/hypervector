"""Typed report-only strategy-evidence records."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyDirectionalEvidence:
    """One side-specific historical statement without execution authority."""

    side: str
    research_state: str
    confidence: str
    cadence: str
    summary: str
    evidence_source: str
    execution_effect: str = "report_only"

    def as_payload(self) -> dict[str, object]:
        """Serialize one directional qualification."""
        return asdict(self)


@dataclass(frozen=True)
class StrategyResearchEvidence:
    """One non-gating research statement for a provider-symbol mapping."""

    strategy_id: str
    symbol: str
    research_state: str
    confidence: str
    cadence: str
    summary: str
    evidence_source: str
    execution_effect: str = "report_only"
    directional_evidence: tuple[StrategyDirectionalEvidence, ...] = ()

    def as_payload(self) -> dict[str, object]:
        """Serialize the evidence without granting routing authority."""
        payload = asdict(self)
        payload["directional_evidence"] = [
            item.as_payload() for item in self.directional_evidence
        ]
        return payload
