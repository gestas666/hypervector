//! Projection and identity checks for concurrent report-only challengers.

use std::collections::BTreeSet;

use crate::backend_cohort_execution_opportunity_matrix::project_forward_challenger;
use crate::backend_cohort_forward_challenger::{
    CohortForwardOneBlockerChallenger, ForwardOneBlockerChallengerRaw,
};

pub(crate) fn project_supplemental_forward_challengers(
    primary: &Option<CohortForwardOneBlockerChallenger>,
    raw: Vec<ForwardOneBlockerChallengerRaw>,
) -> Result<Vec<CohortForwardOneBlockerChallenger>, String> {
    let mut identities = BTreeSet::new();
    if let Some(challenger) = primary {
        identities.insert(candidate_identity(challenger)?);
    }
    let mut projected = Vec::with_capacity(raw.len());
    for value in raw {
        let challenger = project_forward_challenger(Some(value))?
            .ok_or_else(|| "supplemental forward challenger is absent".to_string())?;
        let identity = candidate_identity(&challenger)?;
        if !identities.insert(identity.clone()) {
            return Err(format!("duplicate candidate strategy identity: {identity}"));
        }
        projected.push(challenger);
    }
    Ok(projected)
}

pub(crate) fn candidate_identity(
    challenger: &CohortForwardOneBlockerChallenger,
) -> Result<String, String> {
    let journal = challenger
        .portfolio_journal
        .as_ref()
        .ok_or_else(|| "forward challenger candidate identity is unavailable".to_string())?;
    if journal.candidate_strategy_id.trim().is_empty() {
        return Err("forward challenger candidate identity is empty".into());
    }
    Ok(journal.candidate_strategy_id.clone())
}
