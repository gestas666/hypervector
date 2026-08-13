//! Backend-authored provider readiness telemetry contracts.

use std::collections::BTreeMap;

use serde::Deserialize;
use serde_json::Value;

/// Backend-measured setup prerequisites for one provider decision.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortSignalReadiness {
    pub side: Option<String>,
    pub conditions_met: usize,
    pub conditions_required: usize,
    pub readiness_fraction: f64,
    pub blockers: Vec<String>,
    pub indicators: Vec<String>,
    #[serde(default)]
    pub metrics: BTreeMap<String, Value>,
}

/// Cumulative backend coverage of every configured provider-symbol setup.
#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
pub struct CohortSetupCoverage {
    pub expected_provider_symbols: usize,
    pub observed_provider_symbols: usize,
    pub missing_provider_symbols: Vec<String>,
    pub complete: bool,
}

/// Latest completed-bar evaluation even when no entry was eligible.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortProviderEvaluation {
    #[serde(default)]
    pub observed_at: String,
    pub strategy_id: String,
    pub symbol: String,
    pub decision_time_ms: u64,
    pub reference_price: f64,
    pub decision_action: String,
    pub eligible: bool,
    pub reason: String,
    #[serde(default)]
    pub backend_non_action_reason: Option<String>,
    pub side: Option<String>,
    pub score: Option<i64>,
    pub minimum_score: Option<i64>,
    pub trigger: Option<String>,
    pub primary_regime: Option<String>,
    pub state_1m: Option<String>,
    pub state_5m: Option<String>,
    pub context_15m: Option<String>,
    pub confidence: Option<f64>,
    pub readiness: CohortSignalReadiness,
}
