"""Stateful boundary for low-cost rolling cohort checkpoint publication."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path

from hypervector.research.cohort_checkpoint_history import HistoricalProjectionStale
from hypervector.research.cohort_configuration_generation import (
    load_configuration_expectation,
)
from hypervector.research.cohort_live_portfolio_archive import (
    PORTFOLIO_ARCHIVE_PROJECTION_REVISION,
    CohortAccountingEpoch,
)

PublishFn = Callable[..., dict[str, object]]


def publish_rolling_checkpoint(
    publish_fn: PublishFn,
    ledger_root: Path,
    destination: Path,
    *,
    requested_run_id: str | None,
    config_path: Path,
    once: bool,
    venue_portfolio: Mapping[str, object] | None,
    opportunity_matrix_path: Path | None,
    supplemental_opportunity_matrix_paths: Sequence[Path],
    eligible_policy_forward: bool,
    funding_evidence_fn: object,
    portfolio_archive: Mapping[str, object] | None,
    asymmetric_forward_journal_path: Path | None,
    current_run_only: bool = False,
    accounting_epoch: CohortAccountingEpoch | None = None,
    research_sync: Mapping[str, object] | None = None,
) -> bool:
    """Publish bounded history, falling back to full only when history changed."""
    complete = None if once else load_cached_complete_checkpoint(destination)
    transition_seed = _cached_profile_differs_from_config(complete, config_path)
    bounded_current_run = current_run_only or transition_seed
    selected_run_id = _selected_run_id(requested_run_id, complete)
    options = _publish_options(
        selected_run_id,
        config_path,
        venue_portfolio,
        opportunity_matrix_path,
        supplemental_opportunity_matrix_paths,
        eligible_policy_forward,
        funding_evidence_fn,
        portfolio_archive
        or load_cached_portfolio_archive(destination, accounting_epoch=accounting_epoch),
        asymmetric_forward_journal_path,
        complete,
        bounded_current_run,
    )
    if research_sync is not None:
        options["research_sync"] = research_sync
    try:
        publish_fn(ledger_root, destination, **options)
    except HistoricalProjectionStale:
        options["compatible_execution_history"] = False
        options["complete_historical_checkpoint"] = None
        publish_fn(ledger_root, destination, **options)
        return True
    return False


def _cached_profile_differs_from_config(
    complete: Mapping[str, object] | None,
    config_path: Path,
) -> bool:
    """Bound a first checkpoint when the cache belongs to a prior profile."""
    if complete is None:
        return False
    audit = complete.get("audit")
    run = audit.get("run") if isinstance(audit, Mapping) else None
    cached = run.get("profile_fingerprint") if isinstance(run, Mapping) else None
    if not isinstance(cached, str) or not cached.strip():
        return False
    current = load_configuration_expectation(config_path).profile_fingerprint
    return cached.strip() != current


def load_cached_complete_checkpoint(path: Path) -> Mapping[str, object] | None:
    """Load one prior complete report-only checkpoint, if present."""
    document = _load_checkpoint(path)
    if document is None or not is_complete_live_checkpoint(document):
        return None
    contract = document.get("checkpoint_contract")
    if not isinstance(contract, Mapping):
        return None
    if contract.get("report_only") is not True:
        return None
    if contract.get("execution_authority") != "none":
        return None
    return document


def load_cached_portfolio_archive(
    path: Path,
    *,
    accounting_epoch: CohortAccountingEpoch | None = None,
) -> Mapping[str, object] | None:
    """Load the durable all-time performance archive from a prior checkpoint."""
    document = _load_checkpoint(path)
    if document is None:
        return None
    audit = document.get("audit")
    if not isinstance(audit, Mapping) or audit.get("portfolio_archive") is None:
        return None
    raw_archive = audit.get("portfolio_archive")
    if (
        isinstance(raw_archive, Mapping)
        and raw_archive.get("projection_revision")
        != PORTFOLIO_ARCHIVE_PROJECTION_REVISION
    ):
        return None
    archive = validated_portfolio_archive(raw_archive)
    expected = None if accounting_epoch is None else accounting_epoch.to_dict()
    if archive.get("accounting_epoch") != expected:
        return None
    return archive


def is_complete_live_checkpoint(document: object) -> bool:
    """Return whether a decoded document is a complete live projection."""
    return (
        isinstance(document, Mapping)
        and document.get("schema_version") == 1
        and document.get("mode") == "multi_asset_bidirectional_live_checkpoint"
        and document.get("status") is None
        and isinstance(document.get("lifecycle"), Mapping)
        and isinstance(document.get("audit"), Mapping)
    )


def validated_portfolio_archive(value: object) -> Mapping[str, object]:
    """Validate the read-only archive identity used by the rolling publisher."""
    if not isinstance(value, Mapping):
        raise ValueError("research worker portfolio archive must be an object")
    if value.get("schema_version") != 1:
        raise ValueError("research worker portfolio archive schema is unsupported")
    if value.get("mode") != "cohort_live_portfolio_archive_v1":
        raise ValueError("research worker portfolio archive mode is unsupported")
    if value.get("projection_revision") != PORTFOLIO_ARCHIVE_PROJECTION_REVISION:
        raise ValueError("research worker portfolio archive revision is stale")
    return value


def _load_checkpoint(path: Path) -> Mapping[str, object] | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        raise ValueError(f"cached cohort checkpoint is unreadable: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ValueError("cached cohort checkpoint must be an object")
    return document


def _selected_run_id(
    requested: str | None,
    complete: Mapping[str, object] | None,
) -> str | None:
    if requested is not None or complete is None:
        return requested
    audit = complete.get("audit")
    run = audit.get("run") if isinstance(audit, Mapping) else None
    run_id = run.get("run_id") if isinstance(run, Mapping) else None
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("cached checkpoint run_id is unavailable")
    return run_id.strip()


def _publish_options(
    run_id: str | None,
    config_path: Path,
    venue_portfolio: Mapping[str, object] | None,
    opportunity_matrix_path: Path | None,
    supplemental_paths: Sequence[Path],
    eligible_policy_forward: bool,
    funding_evidence_fn: object,
    portfolio_archive: Mapping[str, object] | None,
    asymmetric_forward_journal_path: Path | None,
    complete: Mapping[str, object] | None,
    current_run_only: bool,
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "config_path": config_path,
        "venue_portfolio": venue_portfolio,
        "opportunity_matrix_path": opportunity_matrix_path,
        "supplemental_opportunity_matrix_paths": tuple(supplemental_paths),
        "eligible_policy_forward": eligible_policy_forward,
        "funding_evidence_fn": funding_evidence_fn,
        "portfolio_archive": portfolio_archive,
        "current_run_only": current_run_only,
        "asymmetric_forward_journal_path": asymmetric_forward_journal_path,
        "compatible_execution_history": (complete is not None and not current_run_only),
        "complete_historical_checkpoint": (None if current_run_only else complete),
    }
