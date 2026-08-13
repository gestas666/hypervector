//! Compact display labels for opportunity-matrix run provenance.

use crate::backend_cohort_execution_opportunity_matrix::CohortOpportunityMatrixProvenance;

/// Render an explicit relationship between matrix evidence and the active run.
pub(crate) fn matrix_provenance_text(
    provenance: Option<&CohortOpportunityMatrixProvenance>,
) -> String {
    let Some(provenance) = provenance else {
        return "PROVENANCE UNAVAILABLE".into();
    };
    let run_id = provenance
        .evidence_run_id
        .as_deref()
        .unwrap_or(&provenance.checkpoint_run_id);
    match provenance.relationship.as_str() {
        "current_run" => format!("CURRENT RUN {run_id}"),
        "historical_prior_run" => format!("HISTORICAL PRIOR RUN {run_id}"),
        "different_run" => format!("DIFFERENT RUN {run_id}"),
        "unattributed" => "UNATTRIBUTED MATRIX".into(),
        _ => "PROVENANCE INVALID".into(),
    }
}
