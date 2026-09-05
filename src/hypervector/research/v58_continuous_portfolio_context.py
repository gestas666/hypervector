"""Checkpoint-bound portfolio opportunity context for continuous V58 research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from hypervector.data.jsonl_prefix import read_jsonl_verified_prefix
from hypervector.data.oxa_storage import file_evidence
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)
from hypervector.live.multi_asset_observer_config import with_observer_ledger_root
from hypervector.research.cohort_successor_observer_status import (
    SuccessorObserverEvidence,
)
from hypervector.research.v58_opportunity_cotrigger import (
    build_opportunity_cotrigger_report,
    contract_from_live_config,
)
from hypervector.research.v58_observer_technical_state import (
    require_reportable_v58_observer_status,
)

Record = Mapping[str, object]


@dataclass(frozen=True)
class PortfolioOpportunityContext:
    """Validated same-prefix opportunity and concurrent-margin evidence."""

    summary: dict[str, object]
    co_trigger_cycles: int
    latest_co_trigger: dict[str, object] | None
    evidence: dict[str, object]
    execution_authority: str = "none"


def load_v58_portfolio_context(
    config_path: Path,
    *,
    observer: SuccessorObserverEvidence,
) -> PortfolioOpportunityContext:
    """Build portfolio context from the observer-authenticated ledger prefix."""
    _require_observer(observer.status)
    ledger = _mapping(
        observer.evidence.get("observer_ledger"), "observer ledger evidence"
    )
    ledger_path = Path(_text(ledger.get("path"), "observer ledger path"))
    config_evidence = file_evidence(config_path)
    config = _observer_config(config_path, ledger_path, observer.status)
    rows = read_jsonl_verified_prefix(
        ledger_path,
        "V58 observer ledger",
        length=_integer(ledger.get("stable_bytes"), "stable ledger bytes"),
        expected_sha256=_text(ledger.get("sha256"), "ledger sha256"),
    )
    report = build_opportunity_cotrigger_report(
        rows,
        contract=contract_from_live_config(config),
        run_id=_text(observer.status.get("run_id"), "observer run id"),
        source_evidence={"observer_ledger": dict(ledger)},
    )
    if file_evidence(config_path) != config_evidence:
        raise ValueError("V58 config changed during portfolio context evaluation")
    return _context(report, config_path, config_evidence, ledger)


def portfolio_context_payload(
    context: PortfolioOpportunityContext,
) -> dict[str, object]:
    """Serialize portfolio context without implying edge or loss probability."""
    return {
        **context.summary,
        "co_trigger_cycles": context.co_trigger_cycles,
        "latest_co_trigger": context.latest_co_trigger,
        "edge_claim": False,
        "joint_loss_probability_claim": False,
        "execution_authority": context.execution_authority,
    }


def _observer_config(
    config_path: Path, ledger_path: Path, status: Record
) -> MultiAssetLiveConfig:
    base = load_multi_asset_live_config(config_path, mode="observe")
    config = with_observer_ledger_root(base, ledger_path.parent)
    expected = {
        "profile_id": status.get("profile_id"),
        "profile_fingerprint": status.get("profile_fingerprint"),
    }
    if any(getattr(config, field) != value for field, value in expected.items()):
        raise ValueError("V58 portfolio context profile identity is invalid")
    if config.cohort_ledger.resolve() != ledger_path.resolve():
        raise ValueError("V58 portfolio context ledger path is invalid")
    return config


def _context(
    report: Record,
    config_path: Path,
    config_evidence: Record,
    ledger: Record,
) -> PortfolioOpportunityContext:
    contract = _mapping(report.get("contract"), "portfolio context contract")
    if contract.get("execution_authority") != "none":
        raise ValueError("V58 portfolio context has execution authority")
    summary = dict(_mapping(report.get("summary"), "portfolio context summary"))
    raw_cycles = report.get("co_trigger_cycles")
    if not isinstance(raw_cycles, list):
        raise ValueError("portfolio co-trigger cycles must be an array")
    latest = dict(_mapping(raw_cycles[-1], "latest co-trigger")) if raw_cycles else None
    evidence = {
        "config": {"path": str(config_path.resolve()), **config_evidence},
        "observer_ledger": dict(ledger),
    }
    return PortfolioOpportunityContext(summary, len(raw_cycles), latest, evidence)


def _require_observer(status: Record) -> None:
    expected = {
        "freshness_status": "fresh",
        "provider_symbol_routes": 10,
        "routed_actions": 0,
        "report_only": True,
        "execution_authority": "none",
    }
    if any(status.get(field) != value for field, value in expected.items()):
        raise ValueError("V58 portfolio observer contract is invalid")
    require_reportable_v58_observer_status(status, "V58 portfolio observer")


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value
