//! Backend-owned research qualification for each provider-symbol mapping.

use std::collections::BTreeSet;

use serde::Deserialize;

use crate::backend_cohort::CohortProvider;
use crate::backend_telemetry::LedgerRow;

/// One report-only evidence statement that cannot alter routing.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortStrategyEvidence {
    pub strategy_id: String,
    pub symbol: String,
    pub research_state: String,
    pub confidence: String,
    pub cadence: String,
    pub summary: String,
    pub evidence_source: String,
    pub execution_effect: String,
}

pub(crate) fn project_strategy_evidence(
    identity: &LedgerRow,
    providers: &[CohortProvider],
) -> Result<Vec<CohortStrategyEvidence>, String> {
    let Some(value) = identity.extra.get("strategy_evidence").cloned() else {
        return Ok(Vec::new());
    };
    let records: Vec<CohortStrategyEvidence> = serde_json::from_value(value)
        .map_err(|error| format!("invalid cohort strategy_evidence: {error}"))?;
    let expected: BTreeSet<(&str, &str)> = providers
        .iter()
        .flat_map(|provider| {
            provider
                .symbols
                .iter()
                .map(move |symbol| (provider.strategy_id.as_str(), symbol.as_str()))
        })
        .collect();
    let actual: BTreeSet<(&str, &str)> = records
        .iter()
        .map(|record| (record.strategy_id.as_str(), record.symbol.as_str()))
        .collect();
    if records.len() != actual.len() || actual != expected {
        return Err("cohort strategy evidence must cover each provider-symbol once".into());
    }
    if records.iter().any(invalid_record) {
        return Err("cohort strategy evidence contains an invalid record".into());
    }
    Ok(records)
}

fn invalid_record(record: &CohortStrategyEvidence) -> bool {
    let text = [
        record.research_state.as_str(),
        record.cadence.as_str(),
        record.summary.as_str(),
        record.evidence_source.as_str(),
    ];
    text.iter().any(|value| value.trim().is_empty())
        || !valid_research_confidence(&record.confidence)
        || record.execution_effect != "report_only"
}

/// Return whether a backend research confidence label is supported.
pub(crate) fn valid_research_confidence(value: &str) -> bool {
    matches!(value, "high" | "medium" | "low_to_medium" | "low")
}
