//! Behavior-preserving projection of validated live checkpoint evidence.

use serde_json::Value;

use super::{
    CheckpointDocument, CohortCheckpointTelemetry, CohortConfigurationGeneration,
    CohortLiveAuditStatus, CohortObserverProviderEvidence, CohortVenuePortfolio, LifecycleEvidence,
    LiveAuditEvidence, five_minute_path_counts, parse_profit_lock_evidence,
    project_allocation_challenger, project_asymmetric_forward_observer,
    project_configuration_generation, project_eligible_policy_forward,
    project_execution_opportunity_matrix, project_friction_parity, project_hulk_entry_quality,
    project_live_audit_status, project_maximum_hold_decisions, project_open_trade_reflections,
    project_portfolio, project_portfolio_archive, project_poststart_acceptance,
    project_regime_conflicts, project_risk_utilization, project_side_composition,
    project_trade_reflections, project_venue_portfolio, provider_contract_outcome_count,
    provider_journal, validate_live,
};

pub(super) fn parse_live(
    document: CheckpointDocument,
) -> Result<CohortCheckpointTelemetry, String> {
    let (venue_portfolio, venue_portfolio_issue) =
        project_venue_portfolio(document.venue_portfolio.clone())?;
    let configuration_generation =
        project_configuration_generation(document.configuration_generation)?;
    let poststart_acceptance = project_poststart_acceptance(document.poststart_acceptance)?;
    let lifecycle = document
        .lifecycle
        .ok_or_else(|| "ready checkpoint is missing lifecycle evidence".to_string())?;
    let audit = parse_live_audit(document.audit)?;
    validate_live(&lifecycle, &audit)?;
    let mut checkpoint = project_live_checkpoint(
        document.generated_at_utc,
        lifecycle,
        audit,
        venue_portfolio,
        venue_portfolio_issue,
        configuration_generation,
    )?;
    checkpoint.poststart_acceptance = poststart_acceptance;
    Ok(checkpoint)
}

fn parse_live_audit(value: Option<Value>) -> Result<LiveAuditEvidence, String> {
    serde_json::from_value(
        value.ok_or_else(|| "ready checkpoint is missing audit evidence".to_string())?,
    )
    .map_err(|error| format!("invalid live checkpoint audit: {error}"))
}

fn project_live_checkpoint(
    generated_at_utc: String,
    lifecycle: LifecycleEvidence,
    mut audit: LiveAuditEvidence,
    venue_portfolio: Option<CohortVenuePortfolio>,
    venue_portfolio_issue: Option<String>,
    configuration_generation: Option<CohortConfigurationGeneration>,
) -> Result<CohortCheckpointTelemetry, String> {
    let (run_id, profile_id, profile_fingerprint) =
        crate::backend_cohort_live_audit::project_live_run_identity(audit.run.as_ref())?;
    let identity = LiveIdentity {
        run_id,
        profile_id,
        profile_fingerprint,
    };
    let forward = project_forward_evidence(&audit)?;
    let live_audit_status =
        project_live_audit_status(audit.runtime.take(), audit.health.take(), audit.run.take())?;
    let header = LiveHeader {
        generated_at_utc,
        lifecycle,
        identity,
        configuration_generation,
        venue_portfolio,
        venue_portfolio_issue,
        live_audit_status,
    };
    let mut output = CohortCheckpointTelemetry::default();
    apply_live_counts(&mut output, &audit, forward);
    apply_live_research(&mut output, &mut audit, &header.identity)?;
    apply_live_trades(&mut output, &mut audit)?;
    apply_live_header(&mut output, header);
    Ok(output)
}

struct LiveIdentity {
    run_id: Option<String>,
    profile_id: Option<String>,
    profile_fingerprint: Option<String>,
}

struct LiveHeader {
    generated_at_utc: String,
    lifecycle: LifecycleEvidence,
    identity: LiveIdentity,
    configuration_generation: Option<CohortConfigurationGeneration>,
    venue_portfolio: Option<CohortVenuePortfolio>,
    venue_portfolio_issue: Option<String>,
    live_audit_status: Option<CohortLiveAuditStatus>,
}

struct ForwardProjection {
    resolved: Option<usize>,
    independent: Option<usize>,
    journal: Vec<CohortObserverProviderEvidence>,
}

fn project_forward_evidence(audit: &LiveAuditEvidence) -> Result<ForwardProjection, String> {
    let scorecard_outcomes = provider_contract_outcome_count(audit.trade_reflections.as_ref())?
        .or(Some(audit.execution.closed_trades));
    let Some(outcomes) = &audit.signal_outcomes else {
        return Ok(ForwardProjection {
            resolved: None,
            independent: None,
            journal: Vec::new(),
        });
    };
    let (resolved, independent) = five_minute_path_counts(outcomes)?;
    let journal = provider_journal(
        &audit.readiness,
        outcomes,
        audit.orderbook_opportunity.as_ref(),
        audit.strategy_scorecard.as_ref(),
        scorecard_outcomes,
    )?;
    Ok(ForwardProjection {
        resolved: Some(resolved),
        independent: Some(independent),
        journal,
    })
}

fn apply_live_counts(
    output: &mut CohortCheckpointTelemetry,
    audit: &LiveAuditEvidence,
    forward: ForwardProjection,
) {
    output.coverage_complete = Some(audit.coverage.complete);
    output.technical_gaps = audit.coverage.technical_gaps.clone();
    output.readiness_evaluations = Some(audit.readiness.evaluations);
    output.strategy_intents = audit.routing.as_ref().map(|value| value.strategy_intents);
    output.routing_actions = audit.routing.as_ref().map(|value| value.actions);
    output.forward_evaluations = audit
        .signal_outcomes
        .as_ref()
        .map(|value| value.evaluations);
    output.eligible_signals = audit
        .signal_outcomes
        .as_ref()
        .map(|value| value.eligible_evaluations);
    output.forward_path_coverage_complete = audit
        .signal_outcomes
        .as_ref()
        .map(|value| value.coverage.complete);
    output.five_minute_paths_resolved = forward.resolved;
    output.five_minute_paths_independent = forward.independent;
    output.observer_provider_journal = forward.journal;
    output.closed_trades = Some(audit.execution.closed_trades);
    output.net_pnl_usd = Some(audit.execution.net_pnl_usd);
}

fn apply_live_research(
    output: &mut CohortCheckpointTelemetry,
    audit: &mut LiveAuditEvidence,
    identity: &LiveIdentity,
) -> Result<(), String> {
    output.portfolio = project_portfolio(audit.portfolio.take())?;
    output.portfolio_archive = project_portfolio_archive(audit.portfolio_archive.take())?;
    output.risk_utilization = project_risk_utilization(audit.risk_utilization.take())?;
    output.allocation_challenger = project_allocation_challenger(
        audit.allocation_challenger.take(),
        output.risk_utilization.as_ref(),
    )?;
    output.asymmetric_forward_observer =
        project_asymmetric_forward_observer(audit.asymmetric_forward_observer.take())?;
    output.side_composition = project_side_composition(
        audit.side_composition.take(),
        identity.run_id.as_deref(),
        identity.profile_id.as_deref(),
        identity.profile_fingerprint.as_deref(),
    )?;
    output.regime_conflicts = project_regime_conflicts(audit.regime_conflict_journal.take())?;
    output.maximum_hold_decisions =
        project_maximum_hold_decisions(audit.maximum_hold_decisions.take())?;
    output.profit_lock_challenger =
        parse_profit_lock_evidence(audit.profit_lock_challenger.take())?;
    output.execution_opportunity_matrix =
        project_execution_opportunity_matrix(audit.execution_opportunity_matrix.take())?;
    output.eligible_policy_forward =
        project_eligible_policy_forward(audit.eligible_policy_forward.take())?;
    output.hulk_entry_quality =
        project_hulk_entry_quality(audit.hulk_entry_quality_challenger.take())?;
    output.evidence_state = Some(std::mem::take(&mut audit.learning.evidence_state));
    Ok(())
}

fn apply_live_trades(
    output: &mut CohortCheckpointTelemetry,
    audit: &mut LiveAuditEvidence,
) -> Result<(), String> {
    let (complete, current, all_time, timer, performance) = project_trade_reflections(
        audit.trade_reflections.take(),
        audit.execution.closed_trades,
    )?;
    output.trade_reflection_context_complete = complete;
    output.trade_reflections = current;
    output.all_time_trade_reflections = all_time;
    output.timer_context_evidence = timer;
    output.trade_performance = performance;
    output.open_trade_reflections = project_open_trade_reflections(
        audit.open_trade_reflections.take(),
        audit.execution.open_lifecycles,
    )?;
    output.friction_parity = project_friction_parity(audit.execution.friction_parity.as_ref())?;
    output.fill_details = std::mem::take(&mut audit.execution.fill_details);
    Ok(())
}

fn apply_live_header(output: &mut CohortCheckpointTelemetry, header: LiveHeader) {
    output.configured = true;
    output.available = true;
    output.stale = backend_issue(&header.lifecycle.state).is_some();
    output.generated_at_utc = Some(header.generated_at_utc);
    output.run_id = header.identity.run_id;
    output.profile_id = header.identity.profile_id;
    output.profile_fingerprint = header.identity.profile_fingerprint;
    output.analysis_mode = Some("live_execution".into());
    output.configuration_generation = header.configuration_generation;
    output.lifecycle_state = Some(header.lifecycle.state.clone());
    output.cohort_heartbeat_status = header.lifecycle.cohort_heartbeat_status;
    output.asset_states = header.lifecycle.asset_states;
    output.venue_portfolio = header.venue_portfolio;
    output.venue_portfolio_issue = header.venue_portfolio_issue;
    output.live_audit_status = header.live_audit_status;
    output.issue = backend_issue(&header.lifecycle.state);
}

fn backend_issue(state: &str) -> Option<String> {
    match state {
        "backend_heartbeat_stale" => {
            Some("execution backend heartbeat has not advanced for more than 60s".into())
        }
        "backend_runtime_fault" => {
            Some("execution backend reported a terminal runtime fault".into())
        }
        _ => None,
    }
}
