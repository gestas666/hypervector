use chrono::DateTime;

use super::{
    CheckpointDocument, LIVE_MODE, LifecycleEvidence, LiveAuditEvidence, OBSERVER_MODE,
    ObserverAuditEvidence, ObserverEvidence,
};

pub(super) fn validate_envelope(document: &CheckpointDocument) -> Result<(), String> {
    if document.schema_version != 1 {
        return Err("unsupported checkpoint schema version".into());
    }
    if !matches!(document.mode.as_str(), LIVE_MODE | OBSERVER_MODE) {
        return Err("unexpected checkpoint mode".into());
    }
    DateTime::parse_from_rfc3339(&document.generated_at_utc)
        .map_err(|error| format!("invalid checkpoint timestamp: {error}"))?;
    if document.status.is_some()
        && (document.lifecycle.is_some() || document.observer.is_some() || document.audit.is_some())
    {
        return Err("checkpoint cannot be both ready and unavailable".into());
    }
    if document.mode == LIVE_MODE && document.observer.is_some() {
        return Err("live checkpoint cannot carry observer lifecycle evidence".into());
    }
    if document.mode == OBSERVER_MODE && document.lifecycle.is_some() {
        return Err("observer checkpoint cannot carry live lifecycle evidence".into());
    }
    Ok(())
}

pub(super) fn validate_live(
    lifecycle: &LifecycleEvidence,
    audit: &LiveAuditEvidence,
) -> Result<(), String> {
    if lifecycle.state.trim().is_empty() || lifecycle.asset_states.is_empty() {
        return Err("checkpoint lifecycle evidence is incomplete".into());
    }
    if !audit.execution.net_pnl_usd.is_finite()
        || audit.learning.evidence_state.trim().is_empty()
        || audit
            .signal_outcomes
            .as_ref()
            .is_some_and(|outcomes| outcomes.eligible_evaluations > outcomes.evaluations)
        || (audit.strategy_scorecard.is_some() && audit.signal_outcomes.is_none())
    {
        return Err("checkpoint audit evidence is invalid".into());
    }
    Ok(())
}

pub(super) fn validate_observer(
    observer: &ObserverEvidence,
    audit: &ObserverAuditEvidence,
) -> Result<(), String> {
    let last_observed_valid = DateTime::parse_from_rfc3339(&observer.last_observed_at_utc).is_ok();
    if observer.state != "setup_process_observation"
        || observer.run_id.trim().is_empty()
        || !last_observed_valid
        || audit.runtime.poll_cycles == 0
        || audit.learning.evidence_state != "setup_and_signal_paths_only_no_execution_outcomes"
        || audit.signal_outcomes.eligible_evaluations > audit.signal_outcomes.evaluations
    {
        return Err("checkpoint observer evidence is invalid".into());
    }
    Ok(())
}
