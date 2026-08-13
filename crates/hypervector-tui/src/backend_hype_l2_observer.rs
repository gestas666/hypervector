//! Typed read-only projection of the prospective HYPE L2 model sidecar.

use std::fs;
use std::path::PathBuf;
use std::time::{Duration, SystemTime};

use chrono::DateTime;
use serde::Deserialize;

const EXPECTED_MODE: &str = "hype_l2_ridge_prospective_observer_status";
const EXPECTED_OUTCOME_MODE: &str = "hype_l2_ridge_prospective_outcomes_v1";
const STATUS_INACTIVITY_LIMIT: Duration = Duration::from_secs(30);

/// Decision-window coverage attached to one prospective model annotation.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct HypeL2CoverageTelemetry {
    pub books: Option<u64>,
    pub maximum_interval_ms: Option<u64>,
    pub start_boundary_age_ms: Option<u64>,
    pub end_boundary_age_ms: Option<u64>,
}

/// Latest annotation generated for a future HYPE entry decision.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2ObservationTelemetry {
    pub status: String,
    pub decision_time_ms: u64,
    pub side: Option<String>,
    pub predicted_gross_return_bps: Option<f64>,
    pub training_score_percentile: Option<f64>,
    pub score_band: Option<String>,
    pub reason: Option<String>,
    pub bundle_sha256: Option<String>,
    #[serde(default)]
    pub coverage: HypeL2CoverageTelemetry,
    pub execution_authority: Option<String>,
    pub report_only: Option<bool>,
    pub runtime_strategy_changed: Option<bool>,
    pub automatic_promotion: Option<bool>,
}

/// Exact annotation-to-lifecycle state counts.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2OutcomeCountsTelemetry {
    pub observations: usize,
    pub scored: usize,
    pub coverage_unavailable: usize,
    pub awaiting_entry_fill: usize,
    pub open: usize,
    pub resolved: usize,
    pub unreconciled: usize,
}

/// Latest authoritative lifecycle joined to one prospective model score.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2OutcomeTelemetry {
    pub status: String,
    pub decision_time_ms: u64,
    pub side: String,
    pub score_band: Option<String>,
    pub predicted_gross_return_bps: Option<f64>,
    pub training_score_percentile: Option<f64>,
    pub entry_trade_id: Option<u64>,
    pub entry_timestamp_ms: Option<u64>,
    pub entry_price: Option<f64>,
    pub entry_size: Option<f64>,
    pub actual_gross_return_bps: Option<f64>,
    pub actual_net_return_bps: Option<f64>,
    pub marked_gross_return_bps: Option<f64>,
    pub marked_net_return_bps: Option<f64>,
    pub marked_net_pnl_usd: Option<f64>,
    pub fees_usd: Option<f64>,
    pub funding_usd: Option<f64>,
    pub net_pnl_usd: Option<f64>,
    pub execution_authority: String,
    pub report_only: bool,
    pub automatic_promotion: bool,
}

/// Aggregate resolved calibration of the prospective model annotations.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2ResolvedPerformanceTelemetry {
    pub resolved: usize,
    pub wins: usize,
    pub losses: usize,
    pub net_return_bps: Option<f64>,
    pub mean_net_return_bps: Option<f64>,
    pub profit_factor: Option<f64>,
}

/// Read-only score/outcome reconciliation attached to observer status.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2OutcomeSummaryTelemetry {
    pub schema_version: u64,
    pub mode: String,
    pub status: String,
    pub technical_issue: Option<String>,
    pub contract: HypeL2OutcomeContractTelemetry,
    pub counts: Option<HypeL2OutcomeCountsTelemetry>,
    pub latest_outcome: Option<HypeL2OutcomeTelemetry>,
    pub resolved_performance: Option<HypeL2ResolvedPerformanceTelemetry>,
    pub confidence: String,
}

/// Safety boundary carried by outcome calibration evidence.
#[derive(Debug, Clone, Deserialize)]
pub struct HypeL2OutcomeContractTelemetry {
    pub report_only: bool,
    pub execution_authority: String,
    pub runtime_strategy_changed: bool,
    pub automatic_promotion: bool,
    pub performance_gate: bool,
}

/// Read-only health and latest output of the HYPE L2 Ridge observer.
#[derive(Debug, Clone, Default)]
pub struct HypeL2ObserverTelemetry {
    pub configured: bool,
    pub available: bool,
    pub stale: bool,
    pub issue: Option<String>,
    pub state: Option<String>,
    pub bundle: Option<String>,
    pub journal: Option<String>,
    pub polls: Option<u64>,
    pub durable_books_observed: Option<u64>,
    pub last_book_exchange_ts_ms: Option<i64>,
    pub latest_observation: Option<HypeL2ObservationTelemetry>,
    pub outcome_summary: Option<HypeL2OutcomeSummaryTelemetry>,
    pub updated_at_utc: Option<String>,
}

impl HypeL2ObserverTelemetry {
    fn unavailable(issue: impl Into<String>) -> Self {
        Self {
            configured: true,
            issue: Some(issue.into()),
            ..Self::default()
        }
    }
}

#[derive(Debug, Deserialize)]
struct ObserverStatusDocument {
    schema_version: u64,
    mode: String,
    state: String,
    execution_authority: String,
    report_only: bool,
    runtime_strategy_changed: bool,
    bundle: String,
    journal: String,
    polls: u64,
    durable_books_observed: u64,
    last_book_exchange_ts_ms: Option<i64>,
    latest_observation: Option<HypeL2ObservationTelemetry>,
    outcome_summary: Option<HypeL2OutcomeSummaryTelemetry>,
    updated_at_utc: String,
}

/// Parse and validate one report-only HYPE L2 observer status document.
pub fn parse_hype_l2_observer_status(content: &str) -> Result<HypeL2ObserverTelemetry, String> {
    let document: ObserverStatusDocument = serde_json::from_str(content)
        .map_err(|error| format!("invalid HYPE L2 observer status JSON: {error}"))?;
    validate_document(&document)?;
    if let Some(observation) = document.latest_observation.as_ref() {
        validate_observation(observation)?;
    }
    if let Some(summary) = document.outcome_summary.as_ref() {
        validate_outcome_summary(summary)?;
    }
    Ok(HypeL2ObserverTelemetry {
        configured: true,
        available: true,
        state: Some(document.state),
        bundle: Some(document.bundle),
        journal: Some(document.journal),
        polls: Some(document.polls),
        durable_books_observed: Some(document.durable_books_observed),
        last_book_exchange_ts_ms: document.last_book_exchange_ts_ms,
        latest_observation: document.latest_observation,
        outcome_summary: document.outcome_summary,
        updated_at_utc: Some(document.updated_at_utc),
        ..HypeL2ObserverTelemetry::default()
    })
}

fn validate_outcome_summary(summary: &HypeL2OutcomeSummaryTelemetry) -> Result<(), String> {
    if summary.schema_version != 1 || summary.mode != EXPECTED_OUTCOME_MODE {
        return Err("HYPE L2 outcome summary identity is invalid".into());
    }
    validate_outcome_contract(&summary.contract)?;
    match summary.status.as_str() {
        "unavailable" => validate_unavailable_outcomes(summary),
        "observed" => validate_observed_outcomes(summary),
        _ => Err("HYPE L2 outcome summary status is invalid".into()),
    }
}

fn validate_outcome_contract(contract: &HypeL2OutcomeContractTelemetry) -> Result<(), String> {
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_promotion
        || contract.performance_gate
    {
        return Err("HYPE L2 outcome summary violates report-only contract".into());
    }
    Ok(())
}

fn validate_unavailable_outcomes(summary: &HypeL2OutcomeSummaryTelemetry) -> Result<(), String> {
    if summary.technical_issue.as_deref().is_none_or(str::is_empty)
        || summary.counts.is_some()
        || summary.latest_outcome.is_some()
        || summary.resolved_performance.is_some()
    {
        return Err("unavailable HYPE L2 outcome summary is success-shaped".into());
    }
    Ok(())
}

fn validate_observed_outcomes(summary: &HypeL2OutcomeSummaryTelemetry) -> Result<(), String> {
    let counts = summary
        .counts
        .as_ref()
        .ok_or_else(|| "observed HYPE L2 outcome summary has no counts".to_string())?;
    let performance = summary.resolved_performance.as_ref().ok_or_else(|| {
        "observed HYPE L2 outcome summary has no resolved performance".to_string()
    })?;
    let classified = counts.coverage_unavailable
        + counts.awaiting_entry_fill
        + counts.open
        + counts.resolved
        + counts.unreconciled;
    if classified != counts.observations
        || counts.scored + counts.coverage_unavailable != counts.observations
        || performance.resolved != counts.resolved
        || performance.wins + performance.losses > performance.resolved
    {
        return Err("HYPE L2 outcome summary counts are inconsistent".into());
    }
    if let Some(outcome) = summary.latest_outcome.as_ref() {
        validate_outcome(outcome)?;
    }
    Ok(())
}

fn validate_outcome(outcome: &HypeL2OutcomeTelemetry) -> Result<(), String> {
    if outcome.decision_time_ms == 0
        || !matches!(outcome.side.as_str(), "long" | "short")
        || outcome.execution_authority != "none"
        || !outcome.report_only
        || outcome.automatic_promotion
        || !matches!(
            outcome.status.as_str(),
            "coverage_unavailable" | "awaiting_entry_fill" | "open" | "resolved" | "unreconciled"
        )
    {
        return Err("HYPE L2 latest outcome identity is invalid".into());
    }
    if outcome.status == "open" && outcome.marked_net_return_bps.is_none() {
        return Err("open HYPE L2 outcome has no marked return".into());
    }
    if outcome.status == "resolved" && outcome.actual_net_return_bps.is_none() {
        return Err("resolved HYPE L2 outcome has no actual return".into());
    }
    Ok(())
}

fn validate_document(document: &ObserverStatusDocument) -> Result<(), String> {
    if document.schema_version != 1 || document.mode != EXPECTED_MODE {
        return Err("HYPE L2 observer status schema or mode is unsupported".into());
    }
    if document.execution_authority != "none"
        || !document.report_only
        || document.runtime_strategy_changed
    {
        return Err("HYPE L2 observer violates the report-only contract".into());
    }
    if !matches!(document.state.as_str(), "running" | "stopped") {
        return Err("HYPE L2 observer lifecycle state is invalid".into());
    }
    if document.bundle.trim().is_empty() || document.journal.trim().is_empty() {
        return Err("HYPE L2 observer evidence paths are empty".into());
    }
    DateTime::parse_from_rfc3339(&document.updated_at_utc)
        .map_err(|error| format!("invalid HYPE L2 observer update time: {error}"))?;
    Ok(())
}

fn validate_observation(observation: &HypeL2ObservationTelemetry) -> Result<(), String> {
    if observation.decision_time_ms == 0
        || !matches!(observation.side.as_deref(), Some("long" | "short"))
    {
        return Err("HYPE L2 observation decision identity is invalid".into());
    }
    if observation.execution_authority.as_deref() != Some("none")
        || observation.report_only != Some(true)
        || observation.runtime_strategy_changed != Some(false)
        || observation.automatic_promotion != Some(false)
    {
        return Err("HYPE L2 observation violates the report-only contract".into());
    }
    match observation.status.as_str() {
        "scored" => validate_score(observation),
        "coverage_unavailable" if observation.reason.as_deref().is_some_and(|v| !v.is_empty()) => {
            Ok(())
        }
        _ => Err("HYPE L2 observation status is invalid".into()),
    }
}

fn validate_score(observation: &HypeL2ObservationTelemetry) -> Result<(), String> {
    let percentile = observation
        .training_score_percentile
        .ok_or_else(|| "HYPE L2 scored observation has no percentile".to_string())?;
    if !observation
        .predicted_gross_return_bps
        .is_some_and(f64::is_finite)
        || !percentile.is_finite()
        || !(0.0..=1.0).contains(&percentile)
        || observation.score_band.as_deref().is_none_or(str::is_empty)
        || observation.coverage.books.is_none()
    {
        return Err("HYPE L2 scored observation values are invalid".into());
    }
    Ok(())
}

/// Independent file source that cannot mutate or invalidate backend telemetry.
pub struct HypeL2ObserverSource {
    path: Option<PathBuf>,
    signature: Option<(u64, SystemTime)>,
    cached: HypeL2ObserverTelemetry,
}

impl HypeL2ObserverSource {
    /// Configure one optional status checkpoint path.
    pub fn new(path: Option<PathBuf>) -> Self {
        Self {
            path,
            signature: None,
            cached: HypeL2ObserverTelemetry::default(),
        }
    }

    /// Refresh status while retaining the last valid value as explicitly stale.
    pub fn refresh(&mut self) -> HypeL2ObserverTelemetry {
        let Some(path) = self.path.as_ref() else {
            return HypeL2ObserverTelemetry::default();
        };
        let metadata = match fs::metadata(path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("observer status unavailable: {error}")),
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.signature == Some(signature) {
            return apply_freshness(self.cached.clone(), modified, SystemTime::now());
        }
        self.load(path.clone(), signature)
    }

    fn load(&mut self, path: PathBuf, signature: (u64, SystemTime)) -> HypeL2ObserverTelemetry {
        let content = match fs::read_to_string(&path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("observer status read failed: {error}")),
        };
        match parse_hype_l2_observer_status(&content) {
            Ok(status) => {
                self.signature = Some(signature);
                self.cached = apply_freshness(status, signature.1, SystemTime::now());
                self.cached.clone()
            }
            Err(error) => self.failed(error),
        }
    }

    fn failed(&self, issue: String) -> HypeL2ObserverTelemetry {
        if self.cached.available {
            let mut stale = self.cached.clone();
            stale.stale = true;
            stale.issue = Some(issue);
            stale
        } else {
            HypeL2ObserverTelemetry::unavailable(issue)
        }
    }
}

fn apply_freshness(
    mut status: HypeL2ObserverTelemetry,
    modified: SystemTime,
    now: SystemTime,
) -> HypeL2ObserverTelemetry {
    let inactive = now
        .duration_since(modified)
        .is_ok_and(|age| age > STATUS_INACTIVITY_LIMIT);
    let stopped = status.state.as_deref() == Some("stopped");
    status.stale = inactive || stopped;
    if status.stale && status.issue.is_none() {
        status.issue = Some(if stopped {
            "HYPE L2 observer reports stopped".into()
        } else {
            "HYPE L2 observer status has not refreshed for more than 30s".into()
        });
    }
    status
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::*;

    #[test]
    fn missing_configured_status_is_unavailable_not_empty() {
        let directory = tempfile::tempdir().expect("tempdir");
        let mut source = HypeL2ObserverSource::new(Some(directory.path().join("missing.json")));

        let status = source.refresh();

        assert!(status.configured);
        assert!(!status.available);
        assert!(
            status
                .issue
                .as_deref()
                .is_some_and(|value| value.contains("unavailable"))
        );
    }

    #[test]
    fn invalid_replacement_retains_last_valid_status_as_stale() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("status.json");
        fs::write(&path, valid_status()).expect("valid status fixture");
        let mut source = HypeL2ObserverSource::new(Some(path.clone()));
        let first = source.refresh();
        assert!(first.available);
        assert!(!first.stale);

        fs::write(&path, "{invalid").expect("invalid status fixture");
        let retained = source.refresh();

        assert!(retained.available);
        assert!(retained.stale);
        assert_eq!(retained.durable_books_observed, Some(317));
        assert!(
            retained
                .issue
                .as_deref()
                .is_some_and(|value| value.contains("invalid"))
        );
    }

    fn valid_status() -> &'static str {
        r#"{
            "schema_version":1,
            "mode":"hype_l2_ridge_prospective_observer_status",
            "state":"running",
            "execution_authority":"none",
            "report_only":true,
            "runtime_strategy_changed":false,
            "bundle":"data/models/hype_l2_ridge_observe_v1.json",
            "journal":"data/live/research/hype_l2_ridge_observations.jsonl",
            "polls":42,
            "durable_books_observed":317,
            "last_book_exchange_ts_ms":1785995321732,
            "latest_observation":null,
            "updated_at_utc":"2026-08-06T05:49:01+00:00"
        }"#
    }
}
