//! Strict provenance projection for report-only opportunity matrices.

use chrono::DateTime;
use serde::Deserialize;

/// Relationship between one attached matrix and the checkpoint rendering it.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortOpportunityMatrixProvenance {
    pub relationship: String,
    pub checkpoint_run_id: String,
    pub checkpoint_first_observed_at_utc: String,
    pub evidence_run_id: Option<String>,
    pub evidence_config_path: Option<String>,
    pub matrix_updated_at_utc: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct CohortOpportunityMatrixProvenanceRaw {
    relationship: String,
    checkpoint_run_id: String,
    checkpoint_first_observed_at_utc: String,
    evidence_run_id: Option<String>,
    evidence_config_path: Option<String>,
    matrix_updated_at_utc: Option<String>,
}

pub(crate) fn project_opportunity_matrix_provenance(
    raw: Option<CohortOpportunityMatrixProvenanceRaw>,
) -> Result<Option<CohortOpportunityMatrixProvenance>, String> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    validate_provenance(&raw)?;
    Ok(Some(CohortOpportunityMatrixProvenance {
        relationship: raw.relationship,
        checkpoint_run_id: raw.checkpoint_run_id,
        checkpoint_first_observed_at_utc: raw.checkpoint_first_observed_at_utc,
        evidence_run_id: raw.evidence_run_id,
        evidence_config_path: raw.evidence_config_path,
        matrix_updated_at_utc: raw.matrix_updated_at_utc,
    }))
}

fn validate_provenance(raw: &CohortOpportunityMatrixProvenanceRaw) -> Result<(), String> {
    let first_observed = parse_timestamp(
        &raw.checkpoint_first_observed_at_utc,
        "checkpoint first-observed timestamp",
    )?;
    validate_required_text(&raw.checkpoint_run_id, "checkpoint run ID")?;
    validate_optional_text(raw.evidence_run_id.as_deref(), "evidence run ID")?;
    validate_optional_text(raw.evidence_config_path.as_deref(), "evidence config path")?;
    let matrix_updated = raw
        .matrix_updated_at_utc
        .as_deref()
        .map(|value| parse_timestamp(value, "matrix update timestamp"))
        .transpose()?;
    let evidence = raw.evidence_run_id.as_deref();
    let same_run = evidence == Some(raw.checkpoint_run_id.as_str());
    let different_run = evidence.is_some() && !same_run;
    let relationship_valid = match raw.relationship.as_str() {
        "current_run" => same_run,
        "historical_prior_run" => {
            different_run && matrix_updated.is_some_and(|updated| updated < first_observed)
        }
        "different_run" => different_run,
        "unattributed" => evidence.is_none(),
        _ => false,
    };
    if !relationship_valid {
        return Err("opportunity matrix checkpoint provenance is inconsistent".into());
    }
    Ok(())
}

fn parse_timestamp(value: &str, field: &str) -> Result<DateTime<chrono::FixedOffset>, String> {
    DateTime::parse_from_rfc3339(value)
        .map_err(|error| format!("invalid opportunity matrix {field}: {error}"))
}

fn validate_required_text(value: &str, field: &str) -> Result<(), String> {
    if value.trim().is_empty() {
        return Err(format!("opportunity matrix {field} must be non-empty"));
    }
    Ok(())
}

fn validate_optional_text(value: Option<&str>, field: &str) -> Result<(), String> {
    if value.is_some_and(|text| text.trim().is_empty()) {
        return Err(format!(
            "opportunity matrix {field} must be non-empty when present"
        ));
    }
    Ok(())
}
