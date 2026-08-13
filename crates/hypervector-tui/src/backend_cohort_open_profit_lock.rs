//! Strict projection of report-only profit-lock state for an open lifecycle.

use std::collections::BTreeMap;

use serde::Deserialize;

pub use crate::backend_cohort_open_profit_lock_economics::CohortOpenProfitLockEconomics;
use crate::backend_cohort_open_profit_lock_economics::{
    RawOpenProfitLockEconomics, project as project_economics,
};

const MODE_V1: &str = "cohort_open_profit_lock_challenger_v1";
const MODE_V2: &str = "cohort_open_profit_lock_challenger_v2";
const POLICY_ORIGIN: &str = "existing_predeclared_hype_profit_research_v1";
const MINUTE_MS: u64 = 60_000;
const POLICIES: [(&str, f64, f64, f64); 3] = [
    ("a25_floor15_trail10", 25.0, 15.0, 10.0),
    ("a40_floor15_trail20", 40.0, 15.0, 20.0),
    ("a60_floor15_trail30", 60.0, 15.0, 30.0),
];

/// One frozen activation, floor, and peak-giveback observation.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenProfitLockPolicy {
    pub status: String,
    pub activation_bps: f64,
    pub floor_bps: f64,
    pub trailing_giveback_bps: f64,
    pub activation_timestamp_ms: Option<u64>,
    pub trigger_timestamp_ms: Option<u64>,
    pub trigger_reference_price: Option<f64>,
    pub stop_price_before_trigger: Option<f64>,
    pub best_completed_price_before_trigger: Option<f64>,
    pub best_completed_price: Option<f64>,
    pub active_stop_price: Option<f64>,
    pub counterfactual_economics: Option<CohortOpenProfitLockEconomics>,
}

/// Execution-incapable profit-lock evidence for one currently open trade.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenProfitLock {
    pub status: String,
    pub entry_timestamp_ms: u64,
    pub as_of_timestamp_ms: u64,
    pub completed_bars_expected: usize,
    pub completed_bars_observed: usize,
    pub policies: BTreeMap<String, CohortOpenProfitLockPolicy>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenProfitLock {
    schema_version: u16,
    mode: String,
    contract: RawContract,
    policy_origin: String,
    status: String,
    entry_timestamp_ms: u64,
    as_of_timestamp_ms: u64,
    completed_bars_expected: usize,
    completed_bars_observed: usize,
    policies: BTreeMap<String, RawPolicy>,
}

#[derive(Debug, Deserialize)]
struct RawContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    automatic_promotion: bool,
}

#[derive(Debug, Deserialize)]
struct RawPolicy {
    policy_id: String,
    activation_bps: f64,
    floor_bps: f64,
    trailing_giveback_bps: f64,
    status: String,
    activation_timestamp_ms: Option<u64>,
    trigger_timestamp_ms: Option<u64>,
    trigger_reference_price: Option<f64>,
    stop_price_before_trigger: Option<f64>,
    best_completed_price_before_trigger: Option<f64>,
    best_completed_price: Option<f64>,
    active_stop_price: Option<f64>,
    counterfactual_economics: Option<RawOpenProfitLockEconomics>,
}

pub(crate) fn project(
    raw: Option<RawOpenProfitLock>,
) -> Result<Option<CohortOpenProfitLock>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_envelope(&value)?;
    let status = value.status.clone();
    let entry_timestamp_ms = value.entry_timestamp_ms;
    let as_of_timestamp_ms = value.as_of_timestamp_ms;
    let policies = value
        .policies
        .into_iter()
        .map(|(key, policy)| {
            project_policy(
                &key,
                policy,
                &status,
                entry_timestamp_ms,
                as_of_timestamp_ms,
                value.schema_version,
            )
        })
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    Ok(Some(CohortOpenProfitLock {
        status: value.status,
        entry_timestamp_ms: value.entry_timestamp_ms,
        as_of_timestamp_ms: value.as_of_timestamp_ms,
        completed_bars_expected: value.completed_bars_expected,
        completed_bars_observed: value.completed_bars_observed,
        policies,
    }))
}

fn validate_envelope(raw: &RawOpenProfitLock) -> Result<(), String> {
    let identity_valid = matches!(
        (raw.schema_version, raw.mode.as_str()),
        (1, MODE_V1) | (2, MODE_V2)
    );
    if !identity_valid || raw.policy_origin != POLICY_ORIGIN {
        return Err("open profit-lock identity is invalid".into());
    }
    let contract = &raw.contract;
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
        || contract.automatic_promotion
    {
        return Err("open profit-lock grants authority or changes strategy".into());
    }
    if raw.as_of_timestamp_ms < raw.entry_timestamp_ms
        || raw.completed_bars_observed > raw.completed_bars_expected
        || !coverage_matches_status(raw)
    {
        return Err("open profit-lock coverage is inconsistent".into());
    }
    if raw.policies.len() != POLICIES.len()
        || POLICIES
            .iter()
            .any(|(key, _, _, _)| !raw.policies.contains_key(*key))
    {
        return Err("open profit-lock policy set is incomplete".into());
    }
    Ok(())
}

fn coverage_matches_status(raw: &RawOpenProfitLock) -> bool {
    match raw.status.as_str() {
        "observed" => {
            raw.completed_bars_expected > 0
                && raw.completed_bars_observed == raw.completed_bars_expected
        }
        "awaiting_completed_bar" => {
            raw.completed_bars_expected == 0 && raw.completed_bars_observed == 0
        }
        "insufficient_candle_coverage" => raw.completed_bars_observed < raw.completed_bars_expected,
        _ => false,
    }
}

fn project_policy(
    key: &str,
    raw: RawPolicy,
    envelope_status: &str,
    entry_timestamp_ms: u64,
    as_of_timestamp_ms: u64,
    schema_version: u16,
) -> Result<(String, CohortOpenProfitLockPolicy), String> {
    let declaration = POLICIES
        .iter()
        .find(|(policy_id, _, _, _)| *policy_id == key)
        .ok_or_else(|| "open profit-lock policy identity is invalid".to_string())?;
    if raw.policy_id != key
        || !approximately(raw.activation_bps, declaration.1)
        || !approximately(raw.floor_bps, declaration.2)
        || !approximately(raw.trailing_giveback_bps, declaration.3)
    {
        return Err("open profit-lock policy identity is inconsistent".into());
    }
    validate_policy_shape(
        &raw,
        envelope_status,
        entry_timestamp_ms,
        as_of_timestamp_ms,
    )?;
    let economics = project_economics(
        schema_version,
        &raw.status,
        raw.trigger_reference_price,
        raw.active_stop_price,
        raw.counterfactual_economics,
    )?;
    Ok((
        key.to_string(),
        CohortOpenProfitLockPolicy {
            status: raw.status,
            activation_bps: raw.activation_bps,
            floor_bps: raw.floor_bps,
            trailing_giveback_bps: raw.trailing_giveback_bps,
            activation_timestamp_ms: raw.activation_timestamp_ms,
            trigger_timestamp_ms: raw.trigger_timestamp_ms,
            trigger_reference_price: raw.trigger_reference_price,
            stop_price_before_trigger: raw.stop_price_before_trigger,
            best_completed_price_before_trigger: raw.best_completed_price_before_trigger,
            best_completed_price: raw.best_completed_price,
            active_stop_price: raw.active_stop_price,
            counterfactual_economics: economics,
        },
    ))
}

fn validate_policy_shape(
    raw: &RawPolicy,
    envelope_status: &str,
    entry_timestamp_ms: u64,
    as_of_timestamp_ms: u64,
) -> Result<(), String> {
    if envelope_status == "insufficient_candle_coverage" {
        return if raw.status == "withheld_incomplete_candle_coverage"
            && all_observations_absent(raw)
        {
            Ok(())
        } else {
            Err("open profit-lock withheld policy is inconsistent".into())
        };
    }
    match raw.status.as_str() {
        "triggered_before_current_boundary"
            if triggered_shape(raw, entry_timestamp_ms, as_of_timestamp_ms) =>
        {
            Ok(())
        }
        "armed_not_triggered" if armed_shape(raw, entry_timestamp_ms, as_of_timestamp_ms) => Ok(()),
        "not_activated" if inactive_shape(raw) => Ok(()),
        _ => Err("open profit-lock policy evidence is inconsistent".into()),
    }
}

fn triggered_shape(raw: &RawPolicy, entry_timestamp_ms: u64, as_of_timestamp_ms: u64) -> bool {
    let timing = match (raw.activation_timestamp_ms, raw.trigger_timestamp_ms) {
        (Some(activation), Some(trigger)) => {
            activation >= entry_timestamp_ms
                && trigger > activation
                && trigger <= as_of_timestamp_ms
                && minute_aligned(activation)
                && minute_aligned(trigger)
        }
        _ => false,
    };
    timing
        && positive(raw.trigger_reference_price)
        && positive(raw.stop_price_before_trigger)
        && positive(raw.best_completed_price_before_trigger)
        && raw.best_completed_price.is_none()
        && raw.active_stop_price.is_none()
}

fn armed_shape(raw: &RawPolicy, entry_timestamp_ms: u64, as_of_timestamp_ms: u64) -> bool {
    raw.activation_timestamp_ms.is_some_and(|timestamp| {
        timestamp >= entry_timestamp_ms
            && timestamp <= as_of_timestamp_ms
            && minute_aligned(timestamp)
    }) && raw.trigger_timestamp_ms.is_none()
        && raw.trigger_reference_price.is_none()
        && raw.stop_price_before_trigger.is_none()
        && raw.best_completed_price_before_trigger.is_none()
        && positive(raw.best_completed_price)
        && positive(raw.active_stop_price)
}

fn inactive_shape(raw: &RawPolicy) -> bool {
    raw.activation_timestamp_ms.is_none()
        && raw.trigger_timestamp_ms.is_none()
        && raw.trigger_reference_price.is_none()
        && raw.stop_price_before_trigger.is_none()
        && raw.best_completed_price_before_trigger.is_none()
        && positive(raw.best_completed_price)
        && raw.active_stop_price.is_none()
}

fn all_observations_absent(raw: &RawPolicy) -> bool {
    raw.activation_timestamp_ms.is_none()
        && raw.trigger_timestamp_ms.is_none()
        && raw.trigger_reference_price.is_none()
        && raw.stop_price_before_trigger.is_none()
        && raw.best_completed_price_before_trigger.is_none()
        && raw.best_completed_price.is_none()
        && raw.active_stop_price.is_none()
}

fn minute_aligned(timestamp_ms: u64) -> bool {
    timestamp_ms.is_multiple_of(MINUTE_MS)
}

fn positive(value: Option<f64>) -> bool {
    value.is_some_and(|number| number.is_finite() && number > 0.0)
}

fn approximately(left: f64, right: f64) -> bool {
    left.is_finite() && (left - right).abs() <= 1e-9
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{RawOpenProfitLock, project};

    #[test]
    fn projects_an_exact_report_only_policy_set() {
        let evidence = project(Some(raw(fixture())))
            .expect("valid open lock")
            .expect("present open lock");

        assert_eq!(evidence.status, "observed");
        assert_eq!(evidence.completed_bars_expected, 2);
        assert_eq!(evidence.policies.len(), 3);
    }

    #[test]
    fn rejects_execution_authority() {
        let mut value = fixture();
        value["contract"]["execution_authority"] = json!("hyperliquid_mainnet");

        let error = project(Some(raw(value))).expect_err("authority must fail");

        assert!(error.contains("grants authority"));
    }

    #[test]
    fn rejects_complete_status_with_missing_bars() {
        let mut value = fixture();
        value["completed_bars_observed"] = json!(1);

        let error = project(Some(raw(value))).expect_err("coverage gap must fail");

        assert!(error.contains("coverage is inconsistent"));
    }

    #[test]
    fn rejects_trigger_claim_without_trigger_evidence() {
        let mut value = fixture();
        value["policies"]["a25_floor15_trail10"]["status"] =
            json!("triggered_before_current_boundary");

        let error = project(Some(raw(value))).expect_err("empty trigger must fail");

        assert!(error.contains("policy evidence is inconsistent"));
    }

    #[test]
    fn projects_v2_counterfactual_economics() {
        let evidence = project(Some(raw(v2_fixture())))
            .expect("valid v2 open lock")
            .expect("present v2 open lock");

        let policy = &evidence.policies["a25_floor15_trail10"];
        let economics = policy
            .counterfactual_economics
            .as_ref()
            .expect("trigger economics");
        assert_eq!(economics.status, "estimated_trigger_exit");
        assert_eq!(economics.estimated_net_pnl_excluding_funding_usd, 0.12);
        assert_eq!(
            economics.estimated_minus_current_exit_net_excluding_funding_usd,
            -0.08
        );
    }

    #[test]
    fn rejects_v2_economics_claiming_funding_inclusion() {
        let mut value = v2_fixture();
        value["policies"]["a25_floor15_trail10"]["counterfactual_economics"]["funding_included"] =
            json!(true);

        let error = project(Some(raw(value))).expect_err("funding claim must fail");

        assert!(error.contains("counterfactual economics"));
    }

    fn raw(value: Value) -> RawOpenProfitLock {
        serde_json::from_value(value).expect("raw open profit-lock fixture")
    }

    fn fixture() -> Value {
        json!({
            "schema_version": 1,
            "mode": "cohort_open_profit_lock_challenger_v1",
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_strategy_changes": false,
                "automatic_promotion": false
            },
            "policy_origin": "existing_predeclared_hype_profit_research_v1",
            "status": "observed",
            "entry_timestamp_ms": 10_000,
            "as_of_timestamp_ms": 180_000,
            "completed_bars_expected": 2,
            "completed_bars_observed": 2,
            "policies": {
                "a25_floor15_trail10": policy("a25_floor15_trail10", 25.0, 10.0),
                "a40_floor15_trail20": policy("a40_floor15_trail20", 40.0, 20.0),
                "a60_floor15_trail30": policy("a60_floor15_trail30", 60.0, 30.0)
            }
        })
    }

    fn v2_fixture() -> Value {
        let mut value = fixture();
        value["schema_version"] = json!(2);
        value["mode"] = json!("cohort_open_profit_lock_challenger_v2");
        let policy = &mut value["policies"]["a25_floor15_trail10"];
        policy["status"] = json!("triggered_before_current_boundary");
        policy["activation_timestamp_ms"] = json!(60_000);
        policy["trigger_timestamp_ms"] = json!(120_000);
        policy["trigger_reference_price"] = json!(100.2);
        policy["stop_price_before_trigger"] = json!(100.2);
        policy["best_completed_price_before_trigger"] = json!(100.3);
        policy["best_completed_price"] = Value::Null;
        policy["counterfactual_economics"] = estimated_economics();
        for key in ["a40_floor15_trail20", "a60_floor15_trail30"] {
            value["policies"][key]["counterfactual_economics"] = json!({
                "status": "unavailable",
                "reason": "policy_state_not_activated"
            });
        }
        value
    }

    fn estimated_economics() -> Value {
        json!({
            "status": "estimated_trigger_exit",
            "reference_price": 100.2,
            "gross_return_bps": 20.0,
            "gross_pnl_usd": 0.2,
            "estimated_entry_fee_usd": 0.04,
            "estimated_exit_fee_usd": 0.04,
            "estimated_net_pnl_excluding_funding_usd": 0.12,
            "estimated_current_exit_net_excluding_funding_usd": 0.2,
            "estimated_minus_current_exit_net_excluding_funding_usd": -0.08,
            "funding_included": false,
            "additional_slippage_included": false,
            "method": "measured_entry_fee_rate_causal_reference_price"
        })
    }

    fn policy(policy_id: &str, activation_bps: f64, trailing_giveback_bps: f64) -> Value {
        json!({
            "policy_id": policy_id,
            "activation_bps": activation_bps,
            "floor_bps": 15.0,
            "trailing_giveback_bps": trailing_giveback_bps,
            "status": "not_activated",
            "activation_timestamp_ms": null,
            "trigger_timestamp_ms": null,
            "trigger_reference_price": null,
            "stop_price_before_trigger": null,
            "best_completed_price_before_trigger": null,
            "best_completed_price": 100.0,
            "active_stop_price": null
        })
    }
}
