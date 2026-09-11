"""Bounded read-only checkpoints for an actively appended live cohort."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

from hypervector.research.cohort_configuration_generation import (
    ConfigurationGenerationExpectation,
    configuration_generation_evidence,
    load_configuration_expectation,
)
from hypervector.research.cohort_checkpoint_history import (
    HistoricalProjectionStale,
    merge_complete_historical_projection,
)
from hypervector.research.checkpoint_storage import write_atomic_json
from hypervector.research.cohort_checkpoint_consistency import (
    require_checkpoint_asset_state_consistency,
)
from hypervector.research.cohort_checkpoint_archive_validation import (
    reconcile_equal_coverage_archive as _reconcile_equal_coverage_archive,
    refresh_accounting_epoch_archive as _refresh_accounting_epoch_archive,
)
from hypervector.research.checkpoint_ledger_projection import (
    compact_asset_ledger_rows,
    compact_cohort_ledger_rows,
)
from hypervector.research.cohort_checkpoint_opportunity import (
    load_opportunity_matrix as _load_opportunity_matrix,
    load_supplemental_opportunity_matrix as _load_supplemental_opportunity_matrix,
    merge_opportunity_matrices,
)
from hypervector.research.cohort_allocation_challenger import (
    allocation_challenger_applicable,
    build_allocation_challenger,
)
from hypervector.research.cohort_asymmetric_forward_observer import (
    AsymmetricForwardDeclaration,
    attach_asymmetric_forward_observer,
    load_asymmetric_forward_declaration,
)
from hypervector.research.cohort_eligible_policy_forward import (
    EligiblePolicyForwardSpec,
    build_eligible_policy_forward_report,
    eth_transfer_forward_spec,
)
from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.research.cohort_live_audit import audit_multi_asset_live_run
from hypervector.research.cohort_live_audit_values import (
    configured_symbols,
    run_id as audit_run_id,
    timestamp as ledger_timestamp,
)
from hypervector.research.cohort_live_run_selection import select_armed_live_run
from hypervector.research.cohort_live_lifecycle import build_live_lifecycle
from hypervector.research.cohort_historical_asset_ledgers import (
    snapshot_retired_asset_ledgers,
)
from hypervector.research.cohort_opportunity_matrix_provenance import (
    opportunity_matrix_provenance,
)
from hypervector.research.cohort_risk_utilization import cohort_risk_utilization
from hypervector.research.cohort_side_composition import build_side_composition
from hypervector.research.cohort_transition_checkpoint import transition_drain_summary
from hypervector.research.live_ledger_snapshot import (
    snapshot_current_run_ledger,
    snapshot_decision_ledger,
    snapshot_projected_compatible_execution_ledger,
)
from hypervector.research.seven_asset_checkpoint_acceptance import (
    attach_seven_asset_poststart_acceptance,
)

Record = Mapping[str, object]
FundingEvidenceFn = Callable[[str, int, int], EligiblePolicyFundingEvidence | None]
_HEARTBEAT_STALE_AFTER_SECONDS = 60.0


def build_live_checkpoint(
    cohort_records: Sequence[Record],
    asset_records: Mapping[str, Sequence[Record]],
    *,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    configuration_expectation: ConfigurationGenerationExpectation | None = None,
    venue_portfolio: Mapping[str, object] | None = None,
    execution_opportunity_matrix: Mapping[str, object] | None = None,
    supplemental_execution_opportunity_matrices: Sequence[Mapping[str, object]] = (),
    eligible_policy_forward_spec: EligiblePolicyForwardSpec | None = None,
    eligible_policy_funding_evidence: EligiblePolicyFundingEvidence | None = None,
    portfolio_archive: Mapping[str, object] | None = None,
    portfolio_reflections_complete: bool = True,
    asymmetric_forward_declaration: AsymmetricForwardDeclaration | None = None,
    heartbeat_stale_after_seconds: float | None = None,
    all_time_asset_records: Mapping[str, Sequence[Record]] | None = None,
) -> dict[str, object]:
    """Build advisory evidence without modifying a live strategy or venue."""
    audit = audit_multi_asset_live_run(
        cohort_records,
        asset_records,
        all_time_asset_records=all_time_asset_records,
        run_id=run_id,
    )
    observed_at = generated_at or datetime.now(timezone.utc)
    run = _mapping(audit.get("run"), "audit run")
    selected_run_id = _text(run.get("run_id"), "audit run_id")
    audit["risk_utilization"] = cohort_risk_utilization(
        cohort_records,
        run_id=selected_run_id,
    )
    risk = _mapping(audit["risk_utilization"], "risk utilization")
    if allocation_challenger_applicable(risk):
        audit["allocation_challenger"] = build_allocation_challenger(
            risk,
            _mapping(audit.get("strategy_scorecard"), "strategy scorecard"),
            hype_records=asset_records.get("HYPE", ()),
            run_id=selected_run_id,
        )
    audit["side_composition"] = build_side_composition(audit)
    if (
        execution_opportunity_matrix is not None
        or supplemental_execution_opportunity_matrices
    ):
        matrix = merge_opportunity_matrices(
            execution_opportunity_matrix,
            supplemental_execution_opportunity_matrices,
        )
        matrix["checkpoint_provenance"] = opportunity_matrix_provenance(
            matrix,
            run,
        )
        audit["execution_opportunity_matrix"] = matrix
    if eligible_policy_forward_spec is not None:
        audit["eligible_policy_forward"] = build_eligible_policy_forward_report(
            cohort_records,
            spec=eligible_policy_forward_spec,
            funding_evidence=eligible_policy_funding_evidence,
        )
    if portfolio_archive is not None:
        audit["portfolio_archive"] = _validated_portfolio_archive(portfolio_archive)
        if portfolio_reflections_complete:
            _refresh_accounting_epoch_archive(audit, observed_at)
            _reconcile_equal_coverage_archive(audit)
    if asymmetric_forward_declaration is not None:
        attach_asymmetric_forward_observer(audit, asymmetric_forward_declaration)
    lifecycle = build_live_lifecycle(
        cohort_records,
        asset_records,
        run_id=selected_run_id,
        observed_at=observed_at,
        heartbeat_stale_after_seconds=heartbeat_stale_after_seconds,
    )
    require_checkpoint_asset_state_consistency(lifecycle, audit)
    checkpoint: dict[str, object] = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": _aware_isoformat(observed_at),
        "checkpoint_contract": _checkpoint_contract(),
        "lifecycle": lifecycle,
        "transition_drain": transition_drain_summary(
            _latest_event(
                _run_rows(cohort_records, selected_run_id), "cohort_snapshot"
            ),
            selected_run_id,
        ),
        "audit": audit,
    }
    if configuration_expectation is not None:
        runtime_fingerprint = _text(
            run.get("profile_fingerprint"),
            "audit profile_fingerprint",
        )
        health = _mapping(audit.get("health"), "audit health")
        assets = _mapping(health.get("assets"), "audit asset health")
        checkpoint["configuration_generation"] = configuration_generation_evidence(
            runtime_fingerprint,
            configuration_expectation,
            assets,
        )
    _attach_venue_portfolio(checkpoint, venue_portfolio)
    return checkpoint


def publish_live_checkpoint(
    ledger_root: Path,
    destination: Path,
    *,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    config_path: Path | None = None,
    venue_portfolio: Mapping[str, object] | None = None,
    opportunity_matrix_path: Path | None = None,
    supplemental_opportunity_matrix_paths: Sequence[Path] = (),
    eligible_policy_forward: bool = False,
    funding_evidence_fn: FundingEvidenceFn | None = None,
    portfolio_archive: Mapping[str, object] | None = None,
    asymmetric_forward_journal_path: Path | None = None,
    compatible_execution_history: bool = False,
    complete_historical_checkpoint: Mapping[str, object] | None = None,
    current_run_only: bool = False,
    research_sync: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Snapshot complete ledger prefixes and atomically replace one report."""
    if compatible_execution_history and run_id is None:
        raise ValueError("compatible execution history requires an explicit run_id")
    if current_run_only and run_id is None:
        raise ValueError("current-run-only checkpoint requires an explicit run_id")
    if current_run_only and compatible_execution_history:
        raise ValueError("current-run-only checkpoint cannot merge cached history")
    cohort_path = ledger_root / "decisions.jsonl"
    observed_at = generated_at or datetime.now(timezone.utc)
    with ExitStack() as stack:
        if current_run_only:
            cohort_snapshot = snapshot_current_run_ledger(
                cohort_path,
                allow_incomplete_tail=True,
                run_id=run_id,
            )
        elif compatible_execution_history:
            cohort_snapshot = snapshot_projected_compatible_execution_ledger(
                cohort_path,
                allow_incomplete_tail=True,
                run_id=run_id,
                stream_projector=compact_cohort_ledger_rows,
            )
        else:
            cohort_snapshot = snapshot_decision_ledger(
                cohort_path,
                allow_incomplete_tail=True,
            )
        cohort_rows, cohort_evidence = stack.enter_context(cohort_snapshot)
        _, identity = select_armed_live_run(cohort_rows, run_id)
        cohort_snapshot_cutoff = ledger_timestamp(
            _required_latest_event(
                _run_rows(cohort_rows, audit_run_id(identity)),
                "cohort_snapshot",
            )
        )
        asset_paths = _asset_paths(
            ledger_root,
            cohort_path,
            configured_symbols(identity),
        )
        asset_rows: dict[str, list[dict[str, object]]] = {}
        asset_evidence: dict[str, dict[str, object]] = {}
        for symbol, path in asset_paths.items():
            if current_run_only:
                asset_snapshot = snapshot_current_run_ledger(
                    path,
                    allow_incomplete_tail=True,
                    run_id=audit_run_id(identity),
                )
            elif compatible_execution_history:
                asset_snapshot = snapshot_projected_compatible_execution_ledger(
                    path,
                    allow_incomplete_tail=True,
                    run_id=audit_run_id(identity),
                    stream_projector=partial(
                        compact_asset_ledger_rows,
                        current_run_id=audit_run_id(identity),
                        as_of=cohort_snapshot_cutoff,
                    ),
                )
            else:
                asset_snapshot = snapshot_decision_ledger(
                    path,
                    allow_incomplete_tail=True,
                )
            rows, evidence = stack.enter_context(asset_snapshot)
            asset_rows[symbol] = rows
            asset_evidence[symbol] = {"path": str(path), **evidence}
        if current_run_only:
            retired_rows, retired_evidence = {}, {}
        else:
            retired_rows, retired_evidence = snapshot_retired_asset_ledgers(
                stack,
                ledger_root,
                cohort_path,
                active_symbols=tuple(asset_paths),
                compatible_execution_history=compatible_execution_history,
                run_id=audit_run_id(identity),
            )
        forward_spec = (
            _eligible_policy_forward_spec(cohort_rows, config_path, run_id)
            if eligible_policy_forward
            else None
        )
        funding_evidence = (
            funding_evidence_fn(
                forward_spec.symbol,
                forward_spec.cutoff_time_ms,
                int(observed_at.timestamp() * 1_000),
            )
            if forward_spec is not None and funding_evidence_fn is not None
            else None
        )
        checkpoint = build_live_checkpoint(
            cohort_rows,
            asset_rows,
            run_id=run_id,
            generated_at=observed_at,
            configuration_expectation=(
                load_configuration_expectation(config_path)
                if config_path is not None
                else None
            ),
            venue_portfolio=venue_portfolio,
            execution_opportunity_matrix=(
                _load_opportunity_matrix(opportunity_matrix_path)
                if opportunity_matrix_path is not None
                else None
            ),
            supplemental_execution_opportunity_matrices=[
                _load_supplemental_opportunity_matrix(path)
                for path in supplemental_opportunity_matrix_paths
            ],
            eligible_policy_forward_spec=forward_spec,
            eligible_policy_funding_evidence=funding_evidence,
            portfolio_archive=portfolio_archive,
            portfolio_reflections_complete=not current_run_only,
            all_time_asset_records=asset_rows | retired_rows,
            asymmetric_forward_declaration=(
                load_asymmetric_forward_declaration(asymmetric_forward_journal_path)
                if asymmetric_forward_journal_path is not None
                else None
            ),
            heartbeat_stale_after_seconds=_HEARTBEAT_STALE_AFTER_SECONDS,
        )
    checkpoint["evidence"] = {
        "cohort": {"path": str(cohort_path), **cohort_evidence},
        "assets": asset_evidence,
        "retired_assets": retired_evidence,
    }
    if compatible_execution_history:
        if complete_historical_checkpoint is None:
            raise HistoricalProjectionStale(
                "complete historical checkpoint is unavailable"
            )
        checkpoint = merge_complete_historical_projection(
            checkpoint,
            complete_historical_checkpoint,
        )
        checkpoint_audit = checkpoint.get("audit")
        if not isinstance(checkpoint_audit, dict):
            raise ValueError("merged checkpoint audit must be mutable")
        _refresh_accounting_epoch_archive(checkpoint_audit, observed_at)
    if config_path is not None:
        attach_seven_asset_poststart_acceptance(
            checkpoint,
            config_path,
            observed_at=observed_at,
        )
    if research_sync is not None:
        checkpoint["research_sync"] = dict(research_sync)
    write_atomic_json(destination, checkpoint)
    return checkpoint


def _validated_portfolio_archive(value: Mapping[str, object]) -> dict[str, object]:
    contract = _mapping(value.get("contract"), "portfolio archive contract")
    if (
        value.get("schema_version") != 1
        or value.get("mode") != "cohort_live_portfolio_archive_v1"
        or contract.get("report_only") is not True
        or contract.get("execution_authority") != "none"
        or contract.get("runtime_strategy_changed") is not False
    ):
        raise ValueError("portfolio archive contract is invalid")
    return dict(value)


def _eligible_policy_forward_spec(
    cohort_rows: Sequence[Record],
    config_path: Path | None,
    requested_run_id: str | None,
) -> EligiblePolicyForwardSpec:
    if config_path is None:
        raise ValueError("eligible policy forward journal requires a config")
    config = load_multi_asset_live_config(config_path, mode="observe")
    _, identity = select_armed_live_run(cohort_rows, requested_run_id)
    return eth_transfer_forward_spec(
        config,
        cohort_rows,
        run_id=audit_run_id(identity),
    )


def publish_unavailable_checkpoint(
    destination: Path,
    technical_issue: str,
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Atomically disclose that current checkpoint evidence is unavailable."""
    issue = _text(technical_issue, "checkpoint technical issue")
    observed_at = generated_at or datetime.now(timezone.utc)
    checkpoint: dict[str, object] = {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": _aware_isoformat(observed_at),
        "checkpoint_contract": _checkpoint_contract(),
        "status": {"state": "unavailable", "technical_issue": issue},
    }
    write_atomic_json(destination, checkpoint)
    return checkpoint


def _attach_venue_portfolio(
    checkpoint: dict[str, object],
    venue_portfolio: Mapping[str, object] | None,
) -> None:
    if venue_portfolio is not None:
        checkpoint["venue_portfolio"] = dict(venue_portfolio)


def _asset_paths(
    ledger_root: Path,
    cohort_path: Path,
    symbols: tuple[str, ...],
) -> dict[str, Path]:
    paths = {symbol: ledger_root / f"{symbol.lower()}.jsonl" for symbol in symbols}
    missing = [symbol for symbol, path in paths.items() if not path.is_file()]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"missing configured asset ledgers: {joined}")
    if cohort_path in paths.values():
        raise ValueError("configured asset ledger collides with cohort ledger")
    return paths


def _checkpoint_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "final": False,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_pause": False,
        "automatic_retuning": False,
        "performance_gate": False,
        "balance_gate": False,
    }


def _run_rows(records: Sequence[Record], run_id: str) -> tuple[Record, ...]:
    return tuple(row for row in records if row.get("run_id") == run_id)


def _latest_event(records: Sequence[Record], event_type: str) -> Record | None:
    return next(
        (row for row in reversed(records) if row.get("event_type") == event_type),
        None,
    )


def _required_latest_event(records: Sequence[Record], event_type: str) -> Record:
    result = _latest_event(records, event_type)
    if result is None:
        raise ValueError(f"checkpoint requires a {event_type} event")
    return result


def _asset_state(records: Sequence[Record]) -> str | None:
    transition = _latest_event(records, "state_transition")
    return _payload_text(transition, "state") if transition else None


def _payload_text(record: Record, key: str) -> str | None:
    payload = _mapping(record.get("payload"), "ledger payload")
    value = payload.get(key)
    return _text(value, key) if value is not None else None


def _aware_isoformat(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("checkpoint generation time must be timezone-aware")
    return value.isoformat()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
