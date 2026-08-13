//! Strict projection of the report-only aligned zero-opposition timer observer.

use std::collections::BTreeMap;

use serde::Deserialize;

const MODE: &str = "aligned_zero_opposition_timer_extension_observer_v1";

/// Aggregate five-minute evidence for causally aligned timer exits.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortAlignedTimerExtensionEvidence {
    pub timer_exits: usize,
    pub eligible: usize,
    pub ineligible: usize,
    pub resolved: usize,
    pub positive: usize,
    pub negative: usize,
    pub unchanged: usize,
    pub protective_stop_hits: usize,
    pub censored: usize,
    pub missing_data: usize,
    pub incremental_gross_pnl_usd: f64,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawAlignedTimerExtensionEvidence {
    schema_version: u64,
    mode: String,
    contract: RawContract,
    policy: RawPolicy,
    decisions: RawDecisions,
    horizon: RawHorizon,
}

#[derive(Debug, Deserialize)]
struct RawContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct RawPolicy {
    horizon_minutes: u16,
    requires_15m_context_alignment: bool,
    requires_complete_zero_opposition: bool,
    retains_protective_stop: bool,
}

#[derive(Debug, Deserialize)]
struct RawDecisions {
    timer_exits: usize,
    eligible: usize,
    ineligible: usize,
    by_reason: BTreeMap<String, usize>,
}

#[derive(Debug, Deserialize)]
struct RawHorizon {
    eligible_extensions: usize,
    resolved: usize,
    positive: usize,
    negative: usize,
    unchanged: usize,
    protective_stop_hits: usize,
    censored: usize,
    missing_data: usize,
    incremental_gross_pnl_usd: f64,
}

pub(crate) fn project_aligned_timer_extension(
    raw: Option<RawAlignedTimerExtensionEvidence>,
    expected_timer_exits: usize,
) -> Result<Option<CohortAlignedTimerExtensionEvidence>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_envelope(&value)?;
    validate_decisions(&value.decisions, expected_timer_exits)?;
    validate_horizon(&value.horizon, value.decisions.eligible)?;
    Ok(Some(CohortAlignedTimerExtensionEvidence {
        timer_exits: value.decisions.timer_exits,
        eligible: value.decisions.eligible,
        ineligible: value.decisions.ineligible,
        resolved: value.horizon.resolved,
        positive: value.horizon.positive,
        negative: value.horizon.negative,
        unchanged: value.horizon.unchanged,
        protective_stop_hits: value.horizon.protective_stop_hits,
        censored: value.horizon.censored,
        missing_data: value.horizon.missing_data,
        incremental_gross_pnl_usd: value.horizon.incremental_gross_pnl_usd,
    }))
}

fn validate_envelope(value: &RawAlignedTimerExtensionEvidence) -> Result<(), String> {
    let contract = &value.contract;
    let policy = &value.policy;
    if value.schema_version != 1
        || value.mode != MODE
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
        || contract.performance_gate
        || contract.balance_gate
        || policy.horizon_minutes != 5
        || !policy.requires_15m_context_alignment
        || !policy.requires_complete_zero_opposition
        || !policy.retains_protective_stop
    {
        return Err("aligned timer extension contract is not frozen report-only evidence".into());
    }
    Ok(())
}

fn validate_decisions(value: &RawDecisions, expected: usize) -> Result<(), String> {
    let eligible_reason = value.by_reason.get("eligible").copied().unwrap_or(0);
    if value.timer_exits != expected
        || value.eligible + value.ineligible != value.timer_exits
        || value.by_reason.values().sum::<usize>() != value.timer_exits
        || eligible_reason != value.eligible
        || value
            .by_reason
            .keys()
            .any(|reason| reason.trim().is_empty())
    {
        return Err("aligned timer extension decision counts are inconsistent".into());
    }
    Ok(())
}

fn validate_horizon(value: &RawHorizon, eligible: usize) -> Result<(), String> {
    if value.eligible_extensions != eligible
        || value.resolved + value.censored + value.missing_data != eligible
        || value.positive + value.negative + value.unchanged != value.resolved
        || value.protective_stop_hits > value.resolved
        || !value.incremental_gross_pnl_usd.is_finite()
    {
        return Err("aligned timer extension horizon is inconsistent".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn rejects_execution_authority() {
        let mut raw = valid_raw();
        raw.contract.execution_authority = "live".into();

        let error =
            project_aligned_timer_extension(Some(raw), 1).expect_err("authority must be rejected");

        assert!(error.contains("frozen report-only"));
    }

    #[test]
    fn rejects_inconsistent_eligibility_counts() {
        let mut raw = valid_raw();
        raw.decisions.eligible = 0;

        let error =
            project_aligned_timer_extension(Some(raw), 1).expect_err("counts must reconcile");

        assert!(error.contains("decision counts"));
    }

    fn valid_raw() -> RawAlignedTimerExtensionEvidence {
        serde_json::from_value(json!({
            "schema_version": 1,
            "mode": MODE,
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_strategy_changes": false,
                "performance_gate": false,
                "balance_gate": false
            },
            "policy": {
                "horizon_minutes": 5,
                "requires_15m_context_alignment": true,
                "requires_complete_zero_opposition": true,
                "retains_protective_stop": true
            },
            "decisions": {
                "timer_exits": 1,
                "eligible": 1,
                "ineligible": 0,
                "by_reason": {"eligible": 1}
            },
            "horizon": {
                "eligible_extensions": 1,
                "resolved": 1,
                "positive": 1,
                "negative": 0,
                "unchanged": 0,
                "protective_stop_hits": 0,
                "censored": 0,
                "missing_data": 0,
                "incremental_gross_pnl_usd": 0.13
            }
        }))
        .expect("valid aligned timer observer")
    }
}
