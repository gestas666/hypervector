//! Validated report-only import progress, separate from live execution health.

use chrono::DateTime;
use serde::Deserialize;
use serde_json::Value;

/// Backend-authored state of the research importer.
#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResearchSyncState {
    Disabled,
    Waiting,
    Running,
    Ready,
    Deferred,
    Failed,
}

/// Last successful import and any unresolved failure; no execution authority.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortResearchSync {
    pub state: ResearchSyncState,
    pub in_progress: bool,
    pub last_attempt_at_utc: Option<String>,
    pub last_success_at_utc: Option<String>,
    pub last_success_age_seconds: Option<f64>,
    pub last_imported_events: Option<u64>,
    pub error: Option<String>,
}

#[derive(Deserialize)]
struct Raw {
    schema_version: u64,
    execution_authority: String,
    #[serde(flatten)]
    status: CohortResearchSync,
}

pub(crate) fn project(value: Option<Value>) -> Result<Option<CohortResearchSync>, String> {
    let Some(value) = value else { return Ok(None) };
    let raw: Raw = serde_json::from_value(value)
        .map_err(|error| format!("invalid research import status: {error}"))?;
    if raw.schema_version != 1 || raw.execution_authority != "none" {
        return Err("research import status must be schema 1 with no execution authority".into());
    }
    validate(&raw.status)?;
    Ok(Some(raw.status))
}

fn validate(status: &CohortResearchSync) -> Result<(), String> {
    use ResearchSyncState::*;
    let success = status.last_success_at_utc.is_some();
    let attempt = status.last_attempt_at_utc.is_some();
    let error = status.error.is_some();
    let invalid = status.in_progress != (status.state == Running)
        || success != status.last_success_age_seconds.is_some()
        || (!success && status.last_imported_events.is_some())
        || status
            .last_success_age_seconds
            .is_some_and(|age| !age.is_finite() || age < 0.0)
        || status
            .error
            .as_ref()
            .is_some_and(|error| error.trim().is_empty())
        || (matches!(status.state, Failed | Deferred) && (!error || !attempt))
        || (status.state == Running && !attempt)
        || (status.state == Ready && (!success || !attempt || error))
        || (matches!(status.state, Disabled | Waiting) && (attempt || success || error));
    if invalid {
        return Err("research import state, availability and error evidence disagree".into());
    }
    for value in [&status.last_attempt_at_utc, &status.last_success_at_utc]
        .into_iter()
        .flatten()
    {
        DateTime::parse_from_rfc3339(value)
            .map_err(|_| "research import timestamp must be an aware RFC3339 time".to_string())?;
    }
    Ok(())
}
