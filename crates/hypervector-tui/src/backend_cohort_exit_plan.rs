//! Strict projection of an open lifecycle's authoritative timer contract.

use serde::Deserialize;

use crate::backend_cohort::profit_lock_contract_valid;

/// Backend-authored maximum-hold deadline for one open lifecycle.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenExitPlan {
    pub maximum_hold_seconds: u64,
    pub maximum_hold_policy: String,
    pub provider_recipe_exit_policy: String,
    pub profit_lock_policy: String,
    pub profit_lock_activation_bps: Option<f64>,
    pub profit_lock_floor_bps: Option<f64>,
    pub profit_lock_giveback_bps: Option<f64>,
    pub hard_maximum_hold_seconds: Option<u64>,
    pub soft_deadline_timestamp_ms: u64,
    pub hard_deadline_timestamp_ms: Option<u64>,
    pub deadline_timestamp_ms: u64,
    pub remaining_time_ms: u64,
    pub expired: bool,
    pub extension_active: bool,
    pub regime_context: String,
    pub source: String,
    pub controller: String,
    pub opposite_intent_exit_scope: String,
    pub opposite_intent_arbitration: String,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenExitPlan {
    maximum_hold_seconds: u64,
    #[serde(default = "fixed_policy")]
    maximum_hold_policy: String,
    #[serde(default)]
    hard_maximum_hold_seconds: Option<u64>,
    #[serde(default = "ignored_provider_recipe_exit_policy")]
    provider_recipe_exit_policy: String,
    #[serde(default = "disabled_profit_lock_policy")]
    profit_lock_policy: String,
    #[serde(default)]
    profit_lock_activation_bps: Option<f64>,
    #[serde(default)]
    profit_lock_floor_bps: Option<f64>,
    #[serde(default)]
    profit_lock_giveback_bps: Option<f64>,
    #[serde(default)]
    soft_deadline_timestamp_ms: Option<u64>,
    #[serde(default)]
    hard_deadline_timestamp_ms: Option<u64>,
    deadline_timestamp_ms: u64,
    remaining_time_ms: u64,
    expired: bool,
    #[serde(default)]
    extension_active: bool,
    #[serde(default = "unavailable_context")]
    regime_context: String,
    source: String,
    controller: String,
    #[serde(default = "unavailable_context")]
    opposite_intent_exit_scope: String,
    #[serde(default = "unavailable_context")]
    opposite_intent_arbitration: String,
}

pub(crate) fn project_open_exit_plan(raw: RawOpenExitPlan) -> Result<CohortOpenExitPlan, String> {
    let soft_deadline = raw
        .soft_deadline_timestamp_ms
        .unwrap_or(raw.deadline_timestamp_ms);
    let allowed_hold_ms = raw
        .hard_maximum_hold_seconds
        .unwrap_or(raw.maximum_hold_seconds)
        .checked_mul(1_000)
        .ok_or_else(|| "open exit-plan maximum hold overflows milliseconds".to_string())?;
    if raw.maximum_hold_seconds == 0
        || raw.deadline_timestamp_ms == 0
        || soft_deadline == 0
        || raw.remaining_time_ms > allowed_hold_ms
        || raw.expired != (raw.remaining_time_ms == 0)
        || !valid_extension(&raw, soft_deadline)
        || !matches!(
            raw.source.as_str(),
            "bound_execution_plan" | "asset_runtime_default"
        )
        || raw.controller != "cohort_maximum_hold"
        || !matches!(raw.provider_recipe_exit_policy.as_str(), "ignore" | "honor")
        || !profit_lock_contract_valid(
            &raw.profit_lock_policy,
            raw.profit_lock_activation_bps,
            raw.profit_lock_floor_bps,
            raw.profit_lock_giveback_bps,
        )
        || !valid_opposite_exit_contract(&raw)
    {
        return Err("open exit-plan identity is invalid".into());
    }
    Ok(CohortOpenExitPlan {
        maximum_hold_seconds: raw.maximum_hold_seconds,
        maximum_hold_policy: raw.maximum_hold_policy,
        provider_recipe_exit_policy: raw.provider_recipe_exit_policy,
        profit_lock_policy: raw.profit_lock_policy,
        profit_lock_activation_bps: raw.profit_lock_activation_bps,
        profit_lock_floor_bps: raw.profit_lock_floor_bps,
        profit_lock_giveback_bps: raw.profit_lock_giveback_bps,
        hard_maximum_hold_seconds: raw.hard_maximum_hold_seconds,
        soft_deadline_timestamp_ms: soft_deadline,
        hard_deadline_timestamp_ms: raw.hard_deadline_timestamp_ms,
        deadline_timestamp_ms: raw.deadline_timestamp_ms,
        remaining_time_ms: raw.remaining_time_ms,
        expired: raw.expired,
        extension_active: raw.extension_active,
        regime_context: raw.regime_context,
        source: raw.source,
        controller: raw.controller,
        opposite_intent_exit_scope: raw.opposite_intent_exit_scope,
        opposite_intent_arbitration: raw.opposite_intent_arbitration,
    })
}

fn valid_opposite_exit_contract(raw: &RawOpenExitPlan) -> bool {
    let unavailable = raw.opposite_intent_exit_scope == "unavailable"
        && raw.opposite_intent_arbitration == "unavailable";
    let current = raw.opposite_intent_exit_scope
        == "selected_opposite_from_any_executable_provider_same_symbol"
        && raw.opposite_intent_arbitration == "regime_then_priority";
    unavailable || current
}

fn valid_extension(raw: &RawOpenExitPlan, soft_deadline: u64) -> bool {
    if raw.maximum_hold_policy == "fixed" {
        return raw.hard_maximum_hold_seconds.is_none()
            && raw.hard_deadline_timestamp_ms.is_none()
            && !raw.extension_active
            && raw.deadline_timestamp_ms == soft_deadline;
    }
    let (Some(hard_seconds), Some(hard_deadline)) = (
        raw.hard_maximum_hold_seconds,
        raw.hard_deadline_timestamp_ms,
    ) else {
        return false;
    };
    hard_seconds > raw.maximum_hold_seconds
        && hard_deadline > soft_deadline
        && (!raw.extension_active || raw.deadline_timestamp_ms == hard_deadline)
        && matches!(
            raw.regime_context.as_str(),
            "still_directionally_supported"
                | "mixed_or_transition"
                | "directionally_opposed"
                | "unavailable"
        )
}

fn fixed_policy() -> String {
    "fixed".into()
}

fn unavailable_context() -> String {
    "unavailable".into()
}

fn ignored_provider_recipe_exit_policy() -> String {
    "ignore".into()
}

fn disabled_profit_lock_policy() -> String {
    "none".into()
}

#[cfg(test)]
mod tests {
    use super::{RawOpenExitPlan, project_open_exit_plan};
    use serde_json::json;

    #[test]
    fn projects_bound_completed_bar_profit_lock() {
        let raw: RawOpenExitPlan = serde_json::from_value(json!({
            "maximum_hold_seconds": 28800,
            "maximum_hold_policy": "fixed",
            "provider_recipe_exit_policy": "ignore",
            "profit_lock_policy": "completed_bar_trailing",
            "profit_lock_activation_bps": 25.0,
            "profit_lock_floor_bps": 15.0,
            "profit_lock_giveback_bps": 10.0,
            "deadline_timestamp_ms": 1786636800000_u64,
            "remaining_time_ms": 1000,
            "expired": false,
            "source": "bound_execution_plan",
            "controller": "cohort_maximum_hold"
        }))
        .expect("raw exit plan");

        let plan = project_open_exit_plan(raw).expect("valid exit plan");

        assert_eq!(plan.profit_lock_policy, "completed_bar_trailing");
        assert_eq!(plan.profit_lock_activation_bps, Some(25.0));
        assert_eq!(plan.profit_lock_floor_bps, Some(15.0));
        assert_eq!(plan.profit_lock_giveback_bps, Some(10.0));
    }
}
