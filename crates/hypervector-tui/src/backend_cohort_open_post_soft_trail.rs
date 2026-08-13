//! Strict projection of frozen post-soft trail state for open lifecycles.

use std::collections::BTreeMap;

use serde::Deserialize;

const MODE: &str = "cohort_open_post_soft_trail_challenger_v1";
const POLICIES: [u16; 3] = [20, 30, 40];

/// One frozen giveback policy evaluated on completed backend candles.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenPostSoftTrailPolicy {
    pub status: String,
    pub trigger_timestamp_ms: Option<u64>,
    pub trigger_reference_price: Option<f64>,
    pub best_completed_price: Option<f64>,
    pub active_trail_price: Option<f64>,
}

/// Execution-incapable open-extension trail evidence.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortOpenPostSoftTrail {
    pub status: String,
    pub soft_deadline_timestamp_ms: u64,
    pub as_of_timestamp_ms: u64,
    pub completed_post_soft_bars: usize,
    pub policies: BTreeMap<u16, CohortOpenPostSoftTrailPolicy>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawOpenPostSoftTrail {
    schema_version: u16,
    mode: String,
    contract: RawContract,
    status: String,
    soft_deadline_timestamp_ms: u64,
    as_of_timestamp_ms: u64,
    baseline_timestamp_ms: Option<u64>,
    baseline_price: Option<f64>,
    completed_post_soft_bars: usize,
    policies: BTreeMap<String, RawPolicy>,
}

#[derive(Debug, Deserialize)]
struct RawContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_strategy_changes: bool,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct RawPolicy {
    giveback_bps: f64,
    status: String,
    trigger_timestamp_ms: Option<u64>,
    trigger_reference_price: Option<f64>,
    #[serde(default)]
    best_completed_price_before_trigger: Option<f64>,
    #[serde(default)]
    best_completed_price: Option<f64>,
    active_trail_price: Option<f64>,
}

pub(crate) fn project(
    raw: Option<RawOpenPostSoftTrail>,
) -> Result<Option<CohortOpenPostSoftTrail>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_envelope(&value)?;
    let status = value.status.clone();
    let soft_deadline = value.soft_deadline_timestamp_ms;
    let as_of = value.as_of_timestamp_ms;
    let policies = value
        .policies
        .into_iter()
        .map(|(key, policy)| project_policy(&key, policy, &status, soft_deadline, as_of))
        .collect::<Result<BTreeMap<_, _>, _>>()?;
    Ok(Some(CohortOpenPostSoftTrail {
        status: value.status,
        soft_deadline_timestamp_ms: value.soft_deadline_timestamp_ms,
        as_of_timestamp_ms: value.as_of_timestamp_ms,
        completed_post_soft_bars: value.completed_post_soft_bars,
        policies,
    }))
}

fn validate_envelope(raw: &RawOpenPostSoftTrail) -> Result<(), String> {
    if raw.schema_version != 1 || raw.mode != MODE {
        return Err("open post-soft trail identity is invalid".into());
    }
    let contract = &raw.contract;
    if !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_strategy_changes
        || contract.performance_gate
        || contract.balance_gate
    {
        return Err("open post-soft trail grants authority or changes strategy".into());
    }
    if !matches!(
        raw.status.as_str(),
        "pending_soft_deadline"
            | "unavailable_boundary_close"
            | "awaiting_completed_bar"
            | "observed"
    ) {
        return Err("open post-soft trail status is invalid".into());
    }
    validate_timing(raw)?;
    let expected = POLICIES.map(|value| format!("{value}bps"));
    if raw.policies.len() != expected.len()
        || expected.iter().any(|key| !raw.policies.contains_key(key))
    {
        return Err("open post-soft trail policy set is incomplete".into());
    }
    Ok(())
}

fn validate_timing(raw: &RawOpenPostSoftTrail) -> Result<(), String> {
    let before_soft = raw.as_of_timestamp_ms < raw.soft_deadline_timestamp_ms;
    if (raw.status == "pending_soft_deadline") != before_soft {
        return Err("open post-soft trail timing disagrees with status".into());
    }
    let has_baseline = raw.baseline_timestamp_ms.is_some() && positive(raw.baseline_price);
    match raw.status.as_str() {
        "observed" if has_baseline && raw.completed_post_soft_bars > 0 => Ok(()),
        "awaiting_completed_bar" if has_baseline && raw.completed_post_soft_bars == 0 => Ok(()),
        "pending_soft_deadline" | "unavailable_boundary_close"
            if raw.baseline_timestamp_ms.is_none()
                && raw.baseline_price.is_none()
                && raw.completed_post_soft_bars == 0 =>
        {
            Ok(())
        }
        _ => Err("open post-soft trail baseline evidence is inconsistent".into()),
    }
}

fn project_policy(
    key: &str,
    raw: RawPolicy,
    envelope_status: &str,
    soft_deadline_ms: u64,
    as_of_ms: u64,
) -> Result<(u16, CohortOpenPostSoftTrailPolicy), String> {
    let giveback = policy_key(key)?;
    if !raw.giveback_bps.is_finite() || (raw.giveback_bps - f64::from(giveback)).abs() > 1e-9 {
        return Err("open post-soft trail policy identity is inconsistent".into());
    }
    validate_policy_shape(&raw, envelope_status, soft_deadline_ms, as_of_ms, giveback)?;
    let best = raw
        .best_completed_price_before_trigger
        .or(raw.best_completed_price);
    Ok((
        giveback,
        CohortOpenPostSoftTrailPolicy {
            status: raw.status,
            trigger_timestamp_ms: raw.trigger_timestamp_ms,
            trigger_reference_price: raw.trigger_reference_price,
            best_completed_price: best,
            active_trail_price: raw.active_trail_price,
        },
    ))
}

fn validate_policy_shape(
    raw: &RawPolicy,
    envelope_status: &str,
    soft_deadline_ms: u64,
    as_of_ms: u64,
    _giveback: u16,
) -> Result<(), String> {
    let best = raw
        .best_completed_price_before_trigger
        .or(raw.best_completed_price);
    let complete_prices =
        positive(raw.trigger_reference_price) && positive(best) && positive(raw.active_trail_price);
    match raw.status.as_str() {
        "triggered"
            if envelope_status == "observed"
                && raw
                    .trigger_timestamp_ms
                    .is_some_and(|time| soft_deadline_ms <= time && time <= as_of_ms)
                && complete_prices =>
        {
            Ok(())
        }
        "armed_not_triggered"
            if envelope_status == "observed"
                && raw.trigger_timestamp_ms.is_none()
                && raw.trigger_reference_price.is_none()
                && positive(best)
                && positive(raw.active_trail_price) =>
        {
            Ok(())
        }
        status
            if status == envelope_status
                && envelope_status != "observed"
                && raw.trigger_timestamp_ms.is_none()
                && raw.trigger_reference_price.is_none()
                && best.is_none()
                && raw.active_trail_price.is_none() =>
        {
            Ok(())
        }
        _ => Err("open post-soft trail policy evidence is inconsistent".into()),
    }
}

fn policy_key(value: &str) -> Result<u16, String> {
    let number = value
        .strip_suffix("bps")
        .ok_or_else(|| "open post-soft trail policy key is invalid".to_string())?
        .parse::<u16>()
        .map_err(|_| "open post-soft trail policy key is invalid".to_string())?;
    if !POLICIES.contains(&number) {
        return Err("open post-soft trail policy key is invalid".into());
    }
    Ok(number)
}

fn positive(value: Option<f64>) -> bool {
    value.is_some_and(|number| number.is_finite() && number > 0.0)
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::{RawOpenPostSoftTrail, project};

    #[test]
    fn projects_exact_report_only_open_trail_state() {
        let raw =
            serde_json::from_value::<RawOpenPostSoftTrail>(fixture()).expect("raw open trail");

        let evidence = project(Some(raw)).expect("valid trail").expect("present");

        assert_eq!(evidence.status, "observed");
        assert_eq!(evidence.policies[&20].status, "triggered");
        assert_eq!(evidence.policies[&40].status, "armed_not_triggered");
    }

    #[test]
    fn rejects_open_trail_that_claims_execution_authority() {
        let mut value = fixture();
        value["contract"]["execution_authority"] = json!("hyperliquid_mainnet");
        let raw = serde_json::from_value::<RawOpenPostSoftTrail>(value).expect("raw open trail");

        let error = project(Some(raw)).expect_err("authority must fail");

        assert!(error.contains("grants authority"));
    }

    fn fixture() -> Value {
        json!({
            "schema_version": 1,
            "mode": "cohort_open_post_soft_trail_challenger_v1",
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_strategy_changes": false,
                "performance_gate": false,
                "balance_gate": false
            },
            "status": "observed",
            "soft_deadline_timestamp_ms": 180000,
            "as_of_timestamp_ms": 310000,
            "baseline_timestamp_ms": 120000,
            "baseline_price": 110.0,
            "completed_post_soft_bars": 2,
            "policies": {
                "20bps": triggered_policy(20.0),
                "30bps": triggered_policy(30.0),
                "40bps": {
                    "giveback_bps": 40.0,
                    "status": "armed_not_triggered",
                    "trigger_timestamp_ms": null,
                    "trigger_reference_price": null,
                    "best_completed_price": 112.0,
                    "active_trail_price": 111.552
                }
            }
        })
    }

    fn triggered_policy(giveback: f64) -> Value {
        json!({
            "giveback_bps": giveback,
            "status": "triggered",
            "trigger_timestamp_ms": 240000,
            "trigger_reference_price": 111.6,
            "best_completed_price_before_trigger": 112.0,
            "active_trail_price": 111.776
        })
    }
}
