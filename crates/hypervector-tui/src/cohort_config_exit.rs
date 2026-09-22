//! Pending provider exit-policy formatting for the cohort config screen.

use crate::app::App;
use crate::backend_cohort_configuration::CohortPendingExitPolicy;
use crate::cohort_widgets::provider_alias;
use std::collections::BTreeMap;

/// Return the selected pending provider and its exact exit contract.
pub(crate) fn pending_provider_exit_label(app: &App) -> Option<(String, String)> {
    let generation = app
        .backend
        .cohort_checkpoint
        .configuration_generation
        .as_ref()?;
    let policies = generation.current_provider_exit_policies.as_ref()?;
    let selected = app
        .backend
        .cohort
        .providers
        .get(app.selected_cohort_provider_index)
        .and_then(|provider| policies.get_key_value(&provider.strategy_id));
    let (strategy, policy) = selected.or_else(|| policies.iter().next())?;
    let directional = directional_profit_locks(
        generation
            .current_provider_directional_exit_policies
            .as_ref(),
        strategy,
        app.selected_cohort_symbol(),
    );
    Some((
        provider_alias(strategy).to_string(),
        format!(
            "{} / RECIPE EXIT {} / {}{}{}",
            hold_contract(policy),
            policy.provider_recipe_exit_policy.to_uppercase(),
            pending_profit_lock(policy),
            directional,
            risk_budget_label(policy),
        ),
    ))
}

fn risk_budget_label(policy: &CohortPendingExitPolicy) -> String {
    policy.stop_risk_budget.as_ref().map_or_else(String::new, |risk| {
        format!(" / EST STOP LOSS ${:.2} INCL {:.0}bps COST ALLOWANCE",
                risk.maximum_loss_usd, risk.cost_buffer_bps)
    })
}

fn directional_profit_locks(
    policies: Option<&BTreeMap<String, CohortPendingExitPolicy>>,
    strategy: &str,
    symbol: Option<&str>,
) -> String {
    let (Some(policies), Some(symbol)) = (policies, symbol) else {
        return String::new();
    };
    let labels = ["long", "short"]
        .into_iter()
        .filter_map(|side| {
            policies
                .get(&format!("{strategy}|{symbol}|{side}"))
                .map(|policy| format!("{} {side}", pending_profit_lock(policy)))
        })
        .collect::<Vec<_>>();
    if labels.is_empty() {
        String::new()
    } else {
        format!(" / {symbol} {}", labels.join(" / "))
    }
}

fn hold_contract(policy: &CohortPendingExitPolicy) -> String {
    let soft = duration_label(policy.maximum_hold_seconds);
    if policy.maximum_hold_policy == "fixed" {
        return format!("FIXED {soft}");
    }
    let hard = policy
        .hard_maximum_hold_seconds
        .map_or_else(|| "N/A".into(), duration_label);
    let evidence = policy
        .maximum_hold_evidence_maximum_age_seconds
        .map_or_else(|| "N/A".into(), duration_label);
    format!("REGIME EXTEND {soft} → HARD {hard} / EVIDENCE ≤{evidence}")
}

fn pending_profit_lock(policy: &CohortPendingExitPolicy) -> String {
    if policy.adaptive_exit_policy == "regime_book_profit_retention_v1" {
        return "ADAPTIVE REGIME/BOOK PROFIT RETENTION".into();
    }
    profit_lock_label(
        &policy.profit_lock_policy,
        policy.profit_lock_activation_bps,
        policy.profit_lock_floor_bps,
        policy.profit_lock_giveback_bps,
    )
}

fn profit_lock_label(
    policy: &str,
    activation: Option<f64>,
    floor: Option<f64>,
    giveback: Option<f64>,
) -> String {
    if policy == "none" {
        return "PROFIT LOCK OFF".into();
    }
    if policy == "btc_hulk_delayed_component_floor_v1" {
        return "PROFIT LOCK DELAYED COMPONENT FLOOR".into();
    }
    if policy == "btc_hulk_delayed_component_exit_v2" {
        return "PROFIT LOCK FLOOR / REVERSAL CONTAINMENT".into();
    }
    match (activation, floor, giveback) {
        (Some(activation), Some(floor), Some(giveback)) => {
            format!("PROFIT LOCK {activation:.0}/{floor:.0}/{giveback:.0}bps")
        }
        _ => "PROFIT LOCK INVALID".into(),
    }
}

fn duration_label(seconds: u64) -> String {
    if seconds.is_multiple_of(3_600) {
        format!("{}H", seconds / 3_600)
    } else {
        format!("{seconds}S")
    }
}

#[cfg(test)]
mod tests {
    use super::{directional_profit_locks, hold_contract, profit_lock_label, risk_budget_label};
    use crate::backend_cohort_configuration::CohortPendingExitPolicy;
    use std::collections::BTreeMap;

    #[test]
    fn risk_budget_projection_is_explicit_optional_and_validated() {
        let mut raw = serde_json::json!({
            "maximum_hold_seconds": 3600,
            "maximum_hold_policy": "fixed",
            "hard_maximum_hold_seconds": null,
            "stop_risk_budget": {"maximum_loss_usd": 10.0, "cost_buffer_bps": 20.0}
        });
        let policy: CohortPendingExitPolicy = serde_json::from_value(raw.clone()).unwrap();
        assert!(policy.stop_risk_budget.as_ref().unwrap().valid());
        assert_eq!(risk_budget_label(&policy),
            " / EST STOP LOSS $10.00 INCL 20bps COST ALLOWANCE");
        raw["stop_risk_budget"]["maximum_loss_usd"] = serde_json::json!(0.0);
        let invalid: CohortPendingExitPolicy = serde_json::from_value(raw.clone()).unwrap();
        assert!(!invalid.stop_risk_budget.as_ref().unwrap().valid());
        raw["stop_risk_budget"]["typo"] = serde_json::json!(20.0);
        assert!(serde_json::from_value::<CohortPendingExitPolicy>(raw.clone()).is_err());
        raw.as_object_mut().unwrap().remove("stop_risk_budget");
        let legacy: CohortPendingExitPolicy = serde_json::from_value(raw).unwrap();
        assert_eq!(risk_budget_label(&legacy), "");
    }

    #[test]
    fn profit_lock_labels_are_explicit() {
        assert_eq!(
            profit_lock_label("none", None, None, None),
            "PROFIT LOCK OFF"
        );
        assert_eq!(
            profit_lock_label("completed_bar_trailing", Some(25.0), Some(8.0), Some(6.0)),
            "PROFIT LOCK 25/8/6bps",
        );
        assert_eq!(
            profit_lock_label("completed_bar_trailing", Some(25.0), None, Some(6.0)),
            "PROFIT LOCK INVALID",
        );
        assert_eq!(
            profit_lock_label("btc_hulk_delayed_component_floor_v1", None, None, None,),
            "PROFIT LOCK DELAYED COMPONENT FLOOR",
        );
        assert_eq!(
            profit_lock_label("btc_hulk_delayed_component_exit_v2", None, None, None,),
            "PROFIT LOCK FLOOR / REVERSAL CONTAINMENT",
        );
    }

    #[test]
    fn directional_labels_preserve_symbol_and_side() {
        let policy = CohortPendingExitPolicy {
            stop_risk_budget: None,
            maximum_hold_seconds: 28_800,
            maximum_hold_policy: "fixed".into(),
            hard_maximum_hold_seconds: None,
            maximum_hold_evidence_maximum_age_seconds: None,
            provider_recipe_exit_policy: "ignore".into(),
            adaptive_exit_policy: "none".into(),
            profit_lock_policy: "completed_bar_trailing".into(),
            profit_lock_activation_bps: Some(30.0),
            profit_lock_floor_bps: Some(12.0),
            profit_lock_giveback_bps: Some(7.0),
        };
        let policies = BTreeMap::from([("provider|HYPE|long".into(), policy)]);

        assert_eq!(
            directional_profit_locks(Some(&policies), "provider", Some("HYPE")),
            " / HYPE PROFIT LOCK 30/12/7bps long",
        );
        assert!(directional_profit_locks(Some(&policies), "provider", Some("BTC")).is_empty());
    }

    #[test]
    fn extended_hold_label_exposes_evidence_freshness() {
        let policy = CohortPendingExitPolicy {
            stop_risk_budget: None,
            maximum_hold_seconds: 28_800,
            maximum_hold_policy: "extend_while_regime_supported".into(),
            hard_maximum_hold_seconds: Some(86_400),
            maximum_hold_evidence_maximum_age_seconds: Some(60),
            provider_recipe_exit_policy: "ignore".into(),
            adaptive_exit_policy: "none".into(),
            profit_lock_policy: "none".into(),
            profit_lock_activation_bps: None,
            profit_lock_floor_bps: None,
            profit_lock_giveback_bps: None,
        };

        assert_eq!(
            hold_contract(&policy),
            "REGIME EXTEND 8H → HARD 24H / EVIDENCE ≤60S"
        );
    }
}
