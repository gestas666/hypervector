//! Validation and projection for growth-profile transition approval evidence.

use std::collections::BTreeSet;

use serde::Deserialize;

/// Fingerprint-bound profile-change approval carried by the preflight.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct GrowthPreflightApprovalTelemetry {
    pub state: String,
    pub approval_status: Option<String>,
    pub approval_document: Option<String>,
    pub retired_execution_scopes: Vec<String>,
    pub replacement_execution_scopes: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ProfileChangeApproval {
    state: String,
    approval_required: bool,
    approval_status: Option<String>,
    approval_document: Option<String>,
    retired_execution_scopes: Vec<String>,
    replacement_execution_scopes: Vec<String>,
    execution_authority: String,
}

pub(crate) fn validate_profile_change_approval(
    approval: Option<&ProfileChangeApproval>,
) -> Result<(), String> {
    let Some(approval) = approval else {
        return Ok(());
    };
    let scopes_valid = unique_text(&approval.retired_execution_scopes)
        && unique_text(&approval.replacement_execution_scopes);
    let state_valid = match approval.state.as_str() {
        "approved_profile_change" => {
            approval.approval_required
                && approval.approval_status.as_deref() == Some("approved_for_live_transition")
                && approval
                    .approval_document
                    .as_deref()
                    .is_some_and(|value| !value.trim().is_empty())
        }
        "unchanged_profile" => {
            !approval.approval_required
                && approval.approval_status.is_none()
                && approval.approval_document.is_none()
                && approval.retired_execution_scopes.is_empty()
                && approval.replacement_execution_scopes.is_empty()
        }
        _ => false,
    };
    if approval.execution_authority != "none" || !scopes_valid || !state_valid {
        return Err("growth preflight profile change approval is invalid".into());
    }
    Ok(())
}

pub(crate) fn project_profile_change_approval(
    approval: ProfileChangeApproval,
) -> GrowthPreflightApprovalTelemetry {
    GrowthPreflightApprovalTelemetry {
        state: approval.state,
        approval_status: approval.approval_status,
        approval_document: approval.approval_document,
        retired_execution_scopes: approval.retired_execution_scopes,
        replacement_execution_scopes: approval.replacement_execution_scopes,
    }
}

fn unique_text(values: &[String]) -> bool {
    values.iter().all(|value| !value.trim().is_empty())
        && values.iter().collect::<BTreeSet<_>>().len() == values.len()
}
