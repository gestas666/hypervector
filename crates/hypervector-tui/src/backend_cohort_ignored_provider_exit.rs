//! Strict projection of lifecycle-bound provider exits ignored by live policy.

use serde::Deserialize;

use crate::backend_cohort_open_path::{CohortOpenPath, RawOpenPath, project_open_path};

/// First ignored provider exit signal retained for one open lifecycle.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortIgnoredProviderExitSignal {
    pub decision_time_ms: u64,
    pub reference_price: f64,
    pub entry_directional_return_bps: f64,
    pub exit_reason: String,
    pub decision_action: Option<String>,
}

/// Point-in-time path evidence after an ignored provider exit signal.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortIgnoredProviderExit {
    pub status: String,
    pub provider_recipe_exit_policy: String,
    pub ignored_signal_count: u64,
    pub first_signal: Option<CohortIgnoredProviderExitSignal>,
    pub path_since_first_signal: Option<CohortOpenPath>,
}

/// Authoritative realized close paired with one ignored provider signal path.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortIgnoredProviderActualExit {
    pub venue_timestamp_ms: u64,
    pub price: f64,
    pub net_pnl_usd: f64,
    pub fees_usd: f64,
    pub funding_usd: f64,
    pub exit_reason: Option<String>,
    pub exit_controller_strategy_id: String,
}

/// Durable ignored provider-exit evidence after a lifecycle has closed.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortClosedIgnoredProviderExit {
    pub status: String,
    pub provider_recipe_exit_policy: Option<String>,
    pub ignored_signal_count: u64,
    pub first_signal: Option<CohortIgnoredProviderExitSignal>,
    pub path_from_first_signal_to_actual_exit: Option<CohortOpenPath>,
    pub gross_continuation_from_signal_bps: Option<f64>,
    pub counterfactual_signal_exit_net_pnl_usd: Option<f64>,
    pub actual_exit: CohortIgnoredProviderActualExit,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawIgnoredProviderExit {
    schema_version: u64,
    mode: String,
    status: String,
    provider_recipe_exit_policy: String,
    ignored_signal_count: u64,
    contract: RawObserverContract,
    first_signal: Option<RawIgnoredProviderExitSignal>,
    path_since_first_signal: Option<RawOpenPath>,
}

#[derive(Debug, Deserialize)]
struct RawObserverContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_promotion: bool,
}

#[derive(Debug, Deserialize)]
struct RawIgnoredProviderExitSignal {
    decision_time_ms: u64,
    reference_price: f64,
    entry_directional_return_bps: f64,
    exit_reason: String,
    #[serde(default)]
    decision_action: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct RawClosedIgnoredProviderExit {
    schema_version: u64,
    mode: String,
    status: String,
    provider_recipe_exit_policy: Option<String>,
    ignored_signal_count: u64,
    contract: RawClosedObserverContract,
    first_signal: Option<RawIgnoredProviderExitSignal>,
    path_from_first_signal_to_actual_exit: Option<RawOpenPath>,
    gross_continuation_from_signal_bps: Option<f64>,
    counterfactual_signal_exit_net_pnl_usd: Option<f64>,
    actual_exit: RawIgnoredProviderActualExit,
}

#[derive(Debug, Deserialize)]
struct RawClosedObserverContract {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
    automatic_promotion: bool,
    actual_exit_is_authoritative: bool,
}

#[derive(Debug, Deserialize)]
struct RawIgnoredProviderActualExit {
    venue_timestamp_ms: u64,
    price: f64,
    net_pnl_usd: f64,
    fees_usd: f64,
    funding_usd: f64,
    exit_reason: Option<String>,
    exit_controller_strategy_id: String,
}

pub(crate) fn project(
    raw: Option<RawIgnoredProviderExit>,
) -> Result<Option<CohortIgnoredProviderExit>, String> {
    raw.map(project_value).transpose()
}

pub(crate) fn project_closed(
    raw: Option<RawClosedIgnoredProviderExit>,
) -> Result<Option<CohortClosedIgnoredProviderExit>, String> {
    raw.map(project_closed_value).transpose()
}

fn project_value(raw: RawIgnoredProviderExit) -> Result<CohortIgnoredProviderExit, String> {
    validate_header(&raw)?;
    validate_shape(&raw)?;
    let signal = raw.first_signal.map(project_signal).transpose()?;
    let path = raw
        .path_since_first_signal
        .map(project_open_path)
        .transpose()?;
    Ok(CohortIgnoredProviderExit {
        status: raw.status,
        provider_recipe_exit_policy: raw.provider_recipe_exit_policy,
        ignored_signal_count: raw.ignored_signal_count,
        first_signal: signal,
        path_since_first_signal: path,
    })
}

fn project_closed_value(
    raw: RawClosedIgnoredProviderExit,
) -> Result<CohortClosedIgnoredProviderExit, String> {
    validate_closed_header(&raw)?;
    validate_closed_shape(&raw)?;
    let signal = raw.first_signal.map(project_signal).transpose()?;
    let path = raw
        .path_from_first_signal_to_actual_exit
        .map(project_open_path)
        .transpose()?;
    validate_continuation(raw.gross_continuation_from_signal_bps, path.as_ref())?;
    Ok(CohortClosedIgnoredProviderExit {
        status: raw.status,
        provider_recipe_exit_policy: raw.provider_recipe_exit_policy,
        ignored_signal_count: raw.ignored_signal_count,
        first_signal: signal,
        path_from_first_signal_to_actual_exit: path,
        gross_continuation_from_signal_bps: raw.gross_continuation_from_signal_bps,
        counterfactual_signal_exit_net_pnl_usd: raw.counterfactual_signal_exit_net_pnl_usd,
        actual_exit: project_actual_exit(raw.actual_exit)?,
    })
}

fn validate_header(raw: &RawIgnoredProviderExit) -> Result<(), String> {
    if raw.schema_version != 1
        || raw.mode != "ignored_provider_recipe_exit_observer_v1"
        || !raw.contract.report_only
        || raw.contract.execution_authority != "none"
        || raw.contract.runtime_strategy_changed
        || raw.contract.automatic_promotion
    {
        return Err("ignored provider exit observer contract is invalid".into());
    }
    Ok(())
}

fn validate_closed_header(raw: &RawClosedIgnoredProviderExit) -> Result<(), String> {
    let contract = &raw.contract;
    if raw.schema_version != 1
        || raw.mode != "closed_ignored_provider_recipe_exit_outcome_v1"
        || !contract.report_only
        || contract.execution_authority != "none"
        || contract.runtime_strategy_changed
        || contract.automatic_promotion
        || !contract.actual_exit_is_authoritative
        || raw.counterfactual_signal_exit_net_pnl_usd.is_some()
    {
        return Err("closed ignored provider exit contract is invalid".into());
    }
    Ok(())
}

fn validate_shape(raw: &RawIgnoredProviderExit) -> Result<(), String> {
    let populated = raw.first_signal.is_some() && raw.path_since_first_signal.is_some();
    let empty = raw.first_signal.is_none() && raw.path_since_first_signal.is_none();
    match raw.status.as_str() {
        "observed"
            if raw.provider_recipe_exit_policy == "ignore"
                && raw.ignored_signal_count > 0
                && populated =>
        {
            Ok(())
        }
        "no_ignored_exit_observed"
            if raw.provider_recipe_exit_policy == "ignore"
                && raw.ignored_signal_count == 0
                && empty =>
        {
            Ok(())
        }
        "not_applicable_policy_honors"
            if raw.provider_recipe_exit_policy == "honor"
                && raw.ignored_signal_count == 0
                && empty =>
        {
            Ok(())
        }
        _ => Err("ignored provider exit observer identity is invalid".into()),
    }
}

fn validate_closed_shape(raw: &RawClosedIgnoredProviderExit) -> Result<(), String> {
    let populated = raw.first_signal.is_some()
        && raw.path_from_first_signal_to_actual_exit.is_some()
        && raw
            .gross_continuation_from_signal_bps
            .is_some_and(f64::is_finite);
    let empty = raw.first_signal.is_none()
        && raw.path_from_first_signal_to_actual_exit.is_none()
        && raw.gross_continuation_from_signal_bps.is_none();
    match raw.status.as_str() {
        "observed"
            if raw.provider_recipe_exit_policy.as_deref() == Some("ignore")
                && raw.ignored_signal_count > 0
                && populated =>
        {
            Ok(())
        }
        "no_ignored_exit_observed"
            if raw.provider_recipe_exit_policy.as_deref() == Some("ignore")
                && raw.ignored_signal_count == 0
                && empty =>
        {
            Ok(())
        }
        "not_applicable_policy_honors"
            if raw.provider_recipe_exit_policy.as_deref() == Some("honor")
                && raw.ignored_signal_count == 0
                && empty =>
        {
            Ok(())
        }
        "unavailable_bound_policy"
            if raw.provider_recipe_exit_policy.is_none()
                && raw.ignored_signal_count == 0
                && empty =>
        {
            Ok(())
        }
        _ => Err("closed ignored provider exit identity is invalid".into()),
    }
}

fn project_signal(
    raw: RawIgnoredProviderExitSignal,
) -> Result<CohortIgnoredProviderExitSignal, String> {
    if raw.decision_time_ms == 0
        || !raw.reference_price.is_finite()
        || raw.reference_price <= 0.0
        || !raw.entry_directional_return_bps.is_finite()
        || raw.exit_reason.trim().is_empty()
        || raw
            .decision_action
            .as_ref()
            .is_some_and(|value| value.trim().is_empty())
    {
        return Err("ignored provider exit signal is invalid".into());
    }
    Ok(CohortIgnoredProviderExitSignal {
        decision_time_ms: raw.decision_time_ms,
        reference_price: raw.reference_price,
        entry_directional_return_bps: raw.entry_directional_return_bps,
        exit_reason: raw.exit_reason,
        decision_action: raw.decision_action,
    })
}

fn project_actual_exit(
    raw: RawIgnoredProviderActualExit,
) -> Result<CohortIgnoredProviderActualExit, String> {
    if raw.venue_timestamp_ms == 0
        || !raw.price.is_finite()
        || raw.price <= 0.0
        || !raw.net_pnl_usd.is_finite()
        || !raw.fees_usd.is_finite()
        || raw.fees_usd < 0.0
        || !raw.funding_usd.is_finite()
        || raw
            .exit_reason
            .as_ref()
            .is_some_and(|value| value.trim().is_empty())
        || raw.exit_controller_strategy_id.trim().is_empty()
    {
        return Err("closed ignored provider actual exit is invalid".into());
    }
    Ok(CohortIgnoredProviderActualExit {
        venue_timestamp_ms: raw.venue_timestamp_ms,
        price: raw.price,
        net_pnl_usd: raw.net_pnl_usd,
        fees_usd: raw.fees_usd,
        funding_usd: raw.funding_usd,
        exit_reason: raw.exit_reason,
        exit_controller_strategy_id: raw.exit_controller_strategy_id,
    })
}

fn validate_continuation(
    continuation: Option<f64>,
    path: Option<&CohortOpenPath>,
) -> Result<(), String> {
    let path_value = path.and_then(|value| value.current_directional_return_bps);
    if continuation != path_value {
        return Err("closed ignored provider continuation disagrees with path".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::*;

    #[test]
    fn observed_signal_requires_both_signal_and_path() {
        let mut value = observed_value();
        value["path_since_first_signal"] = Value::Null;
        let raw = serde_json::from_value(value).expect("raw observer");

        let error = project(Some(raw)).expect_err("partial observer accepted");

        assert!(error.contains("identity"), "{error}");
    }

    #[test]
    fn execution_authority_is_rejected() {
        let mut value = observed_value();
        value["contract"]["execution_authority"] = json!("hyperliquid_mainnet");
        let raw = serde_json::from_value(value).expect("raw observer");

        let error = project(Some(raw)).expect_err("execution authority accepted");

        assert!(error.contains("contract"), "{error}");
    }

    #[test]
    fn closed_observer_projects_authoritative_exit_without_counterfactual_net() {
        let raw = serde_json::from_value(closed_observed_value()).expect("closed raw observer");

        let projected = project_closed(Some(raw))
            .expect("valid closed observer")
            .expect("closed observer");

        assert_eq!(projected.status, "observed");
        assert_eq!(projected.actual_exit.net_pnl_usd, 0.23);
        assert_eq!(projected.gross_continuation_from_signal_bps, Some(0.0));
        assert_eq!(projected.counterfactual_signal_exit_net_pnl_usd, None);
    }

    #[test]
    fn closed_observer_rejects_claimed_counterfactual_net() {
        let mut value = closed_observed_value();
        value["counterfactual_signal_exit_net_pnl_usd"] = json!(0.5);
        let raw = serde_json::from_value(value).expect("closed raw observer");

        let error = project_closed(Some(raw)).expect_err("counterfactual net accepted");

        assert!(error.contains("contract"), "{error}");
    }

    #[test]
    fn closed_observer_rejects_continuation_that_disagrees_with_path() {
        let mut value = closed_observed_value();
        value["gross_continuation_from_signal_bps"] = json!(1.0);
        let raw = serde_json::from_value(value).expect("closed raw observer");

        let error = project_closed(Some(raw)).expect_err("inconsistent continuation accepted");

        assert!(error.contains("disagrees"), "{error}");
    }

    fn observed_value() -> Value {
        json!({
            "schema_version": 1,
            "mode": "ignored_provider_recipe_exit_observer_v1",
            "status": "observed",
            "provider_recipe_exit_policy": "ignore",
            "ignored_signal_count": 1,
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_promotion": false
            },
            "first_signal": {
                "decision_time_ms": 1,
                "reference_price": 100.0,
                "entry_directional_return_bps": -1.0,
                "exit_reason": "flip",
                "decision_action": "close_long"
            },
            "path_since_first_signal": {
                "status": "unavailable",
                "completed_bars": 0,
                "first_timestamp_ms": null,
                "last_timestamp_ms": null,
                "highest_price": null,
                "lowest_price": null,
                "current_directional_return_bps": 0.0,
                "maximum_favorable_excursion_bps": null,
                "maximum_adverse_excursion_bps": null,
                "peak_giveback_bps": null
            }
        })
    }

    fn closed_observed_value() -> Value {
        let open = observed_value();
        json!({
            "schema_version": 1,
            "mode": "closed_ignored_provider_recipe_exit_outcome_v1",
            "status": "observed",
            "provider_recipe_exit_policy": "ignore",
            "ignored_signal_count": 1,
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "runtime_strategy_changed": false,
                "automatic_promotion": false,
                "actual_exit_is_authoritative": true
            },
            "first_signal": open["first_signal"].clone(),
            "path_from_first_signal_to_actual_exit": open["path_since_first_signal"].clone(),
            "gross_continuation_from_signal_bps": 0.0,
            "counterfactual_signal_exit_net_pnl_usd": null,
            "actual_exit": {
                "venue_timestamp_ms": 2,
                "price": 101.0,
                "net_pnl_usd": 0.23,
                "fees_usd": 0.02,
                "funding_usd": -0.001,
                "exit_reason": "maximum_hold_seconds",
                "exit_controller_strategy_id": "cohort_maximum_hold"
            }
        })
    }
}
