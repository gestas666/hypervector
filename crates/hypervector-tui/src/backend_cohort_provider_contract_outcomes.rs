//! Validation for the execution-history scope used by provider scorecards.

use serde::Deserialize;

const PROVIDER_HISTORY_SCOPE: &str = "provider_execution_contract_history";

#[derive(Debug, Deserialize)]
pub(crate) struct RawProviderContractOutcomeEvidence {
    scope: String,
    compatible_trades: usize,
    performance: RawProviderContractPerformance,
}

#[derive(Debug, Deserialize)]
struct RawProviderContractPerformance {
    scope: String,
    total: RawProviderContractTotal,
}

#[derive(Debug, Deserialize)]
struct RawProviderContractTotal {
    closed_trades: usize,
}

pub(crate) fn project_outcome_count(
    evidence: Option<&RawProviderContractOutcomeEvidence>,
) -> Result<Option<usize>, String> {
    let Some(value) = evidence else {
        return Ok(None);
    };
    if value.scope != PROVIDER_HISTORY_SCOPE
        || value.performance.scope != PROVIDER_HISTORY_SCOPE
        || value.compatible_trades != value.performance.total.closed_trades
    {
        return Err("provider contract history outcome count is inconsistent".into());
    }
    Ok(Some(value.compatible_trades))
}
