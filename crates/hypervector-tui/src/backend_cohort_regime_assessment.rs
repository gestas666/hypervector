//! Strict projection contract for report-only regime assessments.

use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub(crate) struct ReflectionContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawRegimeAssessment {
    pub(crate) contract: ReflectionContract,
    pub(crate) structure_support_score: Option<f64>,
    pub(crate) structure_stance: String,
    pub(crate) component_alignment_score: Option<f64>,
    pub(crate) component_stance: String,
    pub(crate) movement_strength: Option<f64>,
    pub(crate) maximum_hold_context: String,
}

pub(crate) fn validate_contract(contract: &ReflectionContract) -> Result<(), String> {
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
    {
        return Err("trade-reflection contract is not report-only".into());
    }
    Ok(())
}

pub(crate) fn validate_regime_assessment(value: &RawRegimeAssessment) -> Result<(), String> {
    validate_contract(&value.contract)?;
    for score in [
        value.structure_support_score,
        value.component_alignment_score,
    ]
    .into_iter()
    .flatten()
    {
        if !score.is_finite() || !(-1.0..=1.0).contains(&score) {
            return Err("open-trade regime assessment score is invalid".into());
        }
    }
    if value
        .movement_strength
        .is_some_and(|score| !score.is_finite() || !(0.0..=1.0).contains(&score))
        || !valid_structure_stance(&value.structure_stance)
        || !valid_component_stance(&value.component_stance)
        || !valid_maximum_hold_context(&value.maximum_hold_context)
    {
        return Err("open-trade regime assessment identity is invalid".into());
    }
    Ok(())
}

pub(crate) fn validate_optional_regime_assessment(
    value: Option<&RawRegimeAssessment>,
) -> Result<(), String> {
    value.map_or(Ok(()), validate_regime_assessment)
}

fn valid_structure_stance(value: &str) -> bool {
    matches!(
        value,
        "directionally_supported" | "directionally_opposed" | "mixed_or_transition" | "unavailable"
    )
}

fn valid_component_stance(value: &str) -> bool {
    matches!(
        value,
        "aligned_with_position" | "opposing_position" | "mixed_or_transition" | "unavailable"
    )
}

fn valid_maximum_hold_context(value: &str) -> bool {
    matches!(
        value,
        "still_directionally_supported"
            | "directionally_opposed"
            | "mixed_or_transition"
            | "unavailable"
    )
}
