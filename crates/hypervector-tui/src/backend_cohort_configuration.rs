//! Validated projection of runtime-versus-disk configuration identity.

use chrono::DateTime;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

use crate::backend_cohort::{CohortProviderSizing, profit_lock_contract_valid};

/// Adaptive exit policy names the backend may bind; mirrors the Python registry.
pub(crate) const ADAPTIVE_EXIT_POLICIES: [&str; 3] = [
    "none",
    "regime_book_profit_retention_v1",
    "regime_flip_floor_retention_v2",
];

/// Whether a serialized adaptive exit policy name is one the cockpit understands.
pub(crate) fn adaptive_exit_policy_valid(policy: &str) -> bool {
    ADAPTIVE_EXIT_POLICIES.contains(&policy)
}

/// Advisory configuration-generation status with no execution authority.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortConfigurationGeneration {
    pub state: String,
    pub matches_runtime: bool,
    pub runtime_profile_fingerprint: String,
    pub current_profile_fingerprint: String,
    pub source_path: String,
    pub source_modified_at_utc: String,
    pub current_provider_execution_scopes: Option<BTreeMap<String, Vec<String>>>,
    pub current_provider_execution_directions: Option<BTreeMap<String, Vec<String>>>,
    pub current_asset_sizing: Option<BTreeMap<String, CohortPendingAssetSizing>>,
    pub current_asset_entry_slippage_caps: Option<BTreeMap<String, f64>>,
    pub current_asset_market_slippage_caps: Option<BTreeMap<String, f64>>,
    pub current_entry_context_overrides: Option<BTreeMap<String, String>>,
    pub current_provider_sizing_overrides: Option<BTreeMap<String, CohortProviderSizing>>,
    pub current_provider_directional_sizing_overrides:
        Option<BTreeMap<String, CohortProviderSizing>>,
    pub current_provider_exit_policies: Option<BTreeMap<String, CohortPendingExitPolicy>>,
    pub current_provider_directional_exit_policies:
        Option<BTreeMap<String, CohortPendingExitPolicy>>,
    pub restart_state: String,
    pub blocking_assets: Vec<String>,
    pub execution_authority: String,
    pub automatic_restart: bool,
}

/// Non-secret sizing values from the selected restart profile.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortPendingAssetSizing {
    pub leverage: f64,
    pub margin_fraction: f64,
    pub max_notional_usd: f64,
}

/// Estimated stop-loss allowance from one provider in the selected profile.
#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CohortStopRiskBudget {
    pub maximum_loss_usd: f64,
    pub cost_buffer_bps: f64,
}

impl CohortStopRiskBudget {
    /// Refuse nonfinite or nonpositive budgets and invalid cost allowances.
    pub fn valid(&self) -> bool {
        self.maximum_loss_usd.is_finite()
            && self.maximum_loss_usd > 0.0
            && self.cost_buffer_bps.is_finite()
            && (0.0..10_000.0).contains(&self.cost_buffer_bps)
    }
}

/// Exit and risk contract from one provider in the selected restart profile.
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct CohortPendingExitPolicy {
    #[serde(default)]
    pub stop_risk_budget: Option<CohortStopRiskBudget>,
    pub maximum_hold_seconds: u64,
    pub maximum_hold_policy: String,
    pub hard_maximum_hold_seconds: Option<u64>,
    #[serde(default)]
    pub maximum_hold_evidence_maximum_age_seconds: Option<u64>,
    #[serde(default = "ignored_provider_recipe_exit_policy")]
    pub provider_recipe_exit_policy: String,
    #[serde(default = "disabled_profit_lock_policy")]
    pub adaptive_exit_policy: String,
    #[serde(default = "disabled_profit_lock_policy")]
    pub profit_lock_policy: String,
    #[serde(default)]
    pub profit_lock_activation_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_floor_bps: Option<f64>,
    #[serde(default)]
    pub profit_lock_giveback_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct ConfigurationGenerationEvidenceRaw {
    state: String,
    matches_runtime: bool,
    runtime_profile_fingerprint: String,
    current_profile_fingerprint: String,
    source_path: String,
    source_modified_at_utc: String,
    #[serde(default)]
    current_provider_execution_scopes: Option<BTreeMap<String, Vec<String>>>,
    #[serde(default)]
    current_provider_execution_directions: Option<BTreeMap<String, Vec<String>>>,
    #[serde(default)]
    current_asset_sizing: Option<BTreeMap<String, CohortPendingAssetSizing>>,
    #[serde(default)]
    current_asset_entry_slippage_caps: Option<BTreeMap<String, f64>>,
    #[serde(default)]
    current_asset_market_slippage_caps: Option<BTreeMap<String, f64>>,
    #[serde(default)]
    current_entry_context_overrides: Option<BTreeMap<String, String>>,
    #[serde(default)]
    current_provider_sizing_overrides: Option<BTreeMap<String, CohortProviderSizing>>,
    #[serde(default)]
    current_provider_directional_sizing_overrides: Option<BTreeMap<String, CohortProviderSizing>>,
    #[serde(default)]
    current_provider_exit_policies: Option<BTreeMap<String, CohortPendingExitPolicy>>,
    #[serde(default)]
    current_provider_directional_exit_policies: Option<BTreeMap<String, CohortPendingExitPolicy>>,
    restart_state: String,
    blocking_assets: Vec<String>,
    execution_authority: String,
    automatic_restart: bool,
}

pub(crate) fn project_configuration_generation(
    raw: Option<ConfigurationGenerationEvidenceRaw>,
) -> Result<Option<CohortConfigurationGeneration>, String> {
    let Some(evidence) = raw else {
        return Ok(None);
    };
    validate(&evidence)?;
    Ok(Some(CohortConfigurationGeneration {
        state: evidence.state,
        matches_runtime: evidence.matches_runtime,
        runtime_profile_fingerprint: evidence.runtime_profile_fingerprint,
        current_profile_fingerprint: evidence.current_profile_fingerprint,
        source_path: evidence.source_path,
        source_modified_at_utc: evidence.source_modified_at_utc,
        current_provider_execution_scopes: evidence.current_provider_execution_scopes,
        current_provider_execution_directions: evidence.current_provider_execution_directions,
        current_asset_sizing: evidence.current_asset_sizing,
        current_asset_entry_slippage_caps: evidence.current_asset_entry_slippage_caps,
        current_asset_market_slippage_caps: evidence.current_asset_market_slippage_caps,
        current_entry_context_overrides: evidence.current_entry_context_overrides,
        current_provider_sizing_overrides: evidence.current_provider_sizing_overrides,
        current_provider_directional_sizing_overrides: evidence
            .current_provider_directional_sizing_overrides,
        current_provider_exit_policies: evidence.current_provider_exit_policies,
        current_provider_directional_exit_policies: evidence
            .current_provider_directional_exit_policies,
        restart_state: evidence.restart_state,
        blocking_assets: evidence.blocking_assets,
        execution_authority: evidence.execution_authority,
        automatic_restart: evidence.automatic_restart,
    }))
}

fn validate(evidence: &ConfigurationGenerationEvidenceRaw) -> Result<(), String> {
    let expected_state = if evidence.matches_runtime {
        "current_runtime_configuration"
    } else {
        "stale_runtime_configuration"
    };
    let timestamps_valid = DateTime::parse_from_rfc3339(&evidence.source_modified_at_utc).is_ok();
    let fields_present = [
        evidence.runtime_profile_fingerprint.as_str(),
        evidence.current_profile_fingerprint.as_str(),
        evidence.source_path.as_str(),
    ]
    .iter()
    .all(|value| !value.trim().is_empty());
    let restart_valid = restart_evidence_valid(evidence);
    if evidence.state != expected_state
        || evidence.execution_authority != "none"
        || evidence.automatic_restart
        || !timestamps_valid
        || !fields_present
        || !restart_valid
        || !provider_execution_scopes_valid(&evidence.current_provider_execution_scopes)
        || !provider_execution_directions_valid(
            &evidence.current_provider_execution_scopes,
            &evidence.current_provider_execution_directions,
        )
        || !asset_sizing_valid(&evidence.current_asset_sizing)
        || !asset_ioc_caps_valid(
            &evidence.current_asset_sizing,
            &evidence.current_asset_entry_slippage_caps,
        )
        || !asset_ioc_caps_valid(
            &evidence.current_asset_sizing,
            &evidence.current_asset_market_slippage_caps,
        )
        || !entry_context_overrides_valid(&evidence.current_entry_context_overrides)
        || !provider_sizing_overrides_valid(&evidence.current_provider_sizing_overrides)
        || !provider_directional_sizing_overrides_valid(
            &evidence.current_provider_directional_sizing_overrides,
        )
        || !provider_exit_policies_valid(&evidence.current_provider_exit_policies)
        || !directional_exit_policies_valid(
            &evidence.current_provider_execution_scopes,
            &evidence.current_provider_execution_directions,
            &evidence.current_provider_directional_exit_policies,
        )
    {
        return Err("checkpoint configuration-generation evidence is invalid".into());
    }
    Ok(())
}

fn directional_exit_policies_valid(
    scopes: &Option<BTreeMap<String, Vec<String>>>,
    directions: &Option<BTreeMap<String, Vec<String>>>,
    policies: &Option<BTreeMap<String, CohortPendingExitPolicy>>,
) -> bool {
    let Some(policies) = policies else {
        return true;
    };
    let (Some(scopes), Some(directions)) = (scopes, directions) else {
        return false;
    };
    policies.iter().all(|(identity, policy)| {
        let parts = identity.split('|').collect::<Vec<_>>();
        if parts.len() != 3 {
            return false;
        }
        let strategy = parts[0];
        if !pending_exit_policy_valid(strategy, policy) {
            return false;
        }
        let symbol = parts[1];
        let side = parts[2];
        let route = format!("{strategy}|{symbol}");
        scopes
            .get(strategy)
            .is_some_and(|symbols| symbols.iter().any(|value| value == symbol))
            && directions
                .get(&route)
                .is_some_and(|sides| sides.iter().any(|value| value == side))
    })
}

fn provider_execution_scopes_valid(scopes: &Option<BTreeMap<String, Vec<String>>>) -> bool {
    scopes.as_ref().is_none_or(|values| {
        !values.is_empty()
            && values.iter().all(|(strategy, symbols)| {
                let identity_valid = !strategy.trim().is_empty() && !strategy.contains('|');
                let unique = symbols.iter().collect::<BTreeSet<_>>().len() == symbols.len();
                let symbols_valid = symbols
                    .iter()
                    .all(|symbol| !symbol.trim().is_empty() && !symbol.contains('|'));
                identity_valid && unique && symbols_valid
            })
    })
}

fn provider_execution_directions_valid(
    scopes: &Option<BTreeMap<String, Vec<String>>>,
    directions: &Option<BTreeMap<String, Vec<String>>>,
) -> bool {
    let Some(values) = directions else {
        return true;
    };
    let Some(scopes) = scopes else {
        return false;
    };
    let expected = scopes
        .iter()
        .flat_map(|(strategy, symbols)| {
            symbols
                .iter()
                .map(move |symbol| format!("{strategy}|{symbol}"))
        })
        .collect::<BTreeSet<_>>();
    if values.keys().cloned().collect::<BTreeSet<_>>() != expected {
        return false;
    }
    values.iter().all(|(key, sides)| {
        key.split('|').count() == 2
            && !sides.is_empty()
            && sides.iter().collect::<BTreeSet<_>>().len() == sides.len()
            && sides
                .iter()
                .all(|side| matches!(side.as_str(), "long" | "short"))
    })
}

fn provider_exit_policies_valid(
    policies: &Option<BTreeMap<String, CohortPendingExitPolicy>>,
) -> bool {
    policies.as_ref().is_none_or(|values| {
        values.iter().all(|(strategy, policy)| {
            !strategy.trim().is_empty()
                && !strategy.contains('|')
                && pending_exit_policy_valid(strategy, policy)
        })
    })
}

fn pending_exit_policy_valid(strategy_id: &str, policy: &CohortPendingExitPolicy) -> bool {
    let evidence_age_valid = policy
        .maximum_hold_evidence_maximum_age_seconds
        .is_none_or(|seconds| seconds > 0);
    let contract_valid = match policy.maximum_hold_policy.as_str() {
        "fixed" => {
            policy.hard_maximum_hold_seconds.is_none()
                && policy.maximum_hold_evidence_maximum_age_seconds.is_none()
        }
        "extend_while_regime_supported" => policy
            .hard_maximum_hold_seconds
            .is_some_and(|hard| hard > policy.maximum_hold_seconds),
        _ => false,
    };
    policy.maximum_hold_seconds > 0
        && policy.stop_risk_budget.as_ref().is_none_or(CohortStopRiskBudget::valid)
        && adaptive_exit_policy_valid(policy.adaptive_exit_policy.as_str())
        && evidence_age_valid
        && contract_valid
        && matches!(
            policy.provider_recipe_exit_policy.as_str(),
            "ignore" | "honor"
        )
        && profit_lock_contract_valid(
            Some(strategy_id),
            &policy.profit_lock_policy,
            policy.profit_lock_activation_bps,
            policy.profit_lock_floor_bps,
            policy.profit_lock_giveback_bps,
        )
}

fn ignored_provider_recipe_exit_policy() -> String {
    "ignore".into()
}

fn disabled_profit_lock_policy() -> String {
    "none".into()
}

fn asset_sizing_valid(sizing: &Option<BTreeMap<String, CohortPendingAssetSizing>>) -> bool {
    sizing.as_ref().is_none_or(|values| {
        values.iter().all(|(symbol, row)| {
            !symbol.trim().is_empty()
                && !symbol.contains('|')
                && row.leverage.is_finite()
                && row.leverage > 0.0
                && row.margin_fraction.is_finite()
                && row.margin_fraction > 0.0
                && row.margin_fraction <= 1.0
                && row.max_notional_usd.is_finite()
                && row.max_notional_usd > 0.0
        })
    })
}

fn asset_ioc_caps_valid(
    sizing: &Option<BTreeMap<String, CohortPendingAssetSizing>>,
    caps: &Option<BTreeMap<String, f64>>,
) -> bool {
    caps.as_ref().is_none_or(|values| {
        !values.is_empty()
            && sizing
                .as_ref()
                .is_some_and(|assets| assets.keys().eq(values.keys()))
            && values
                .values()
                .all(|cap| cap.is_finite() && (0.0..=0.05).contains(cap))
    })
}

fn provider_sizing_overrides_valid(
    overrides: &Option<BTreeMap<String, CohortProviderSizing>>,
) -> bool {
    overrides.as_ref().is_none_or(|values| {
        values
            .iter()
            .all(|(key, sizing)| provider_identity_valid(key) && provider_sizing_valid(sizing))
    })
}

fn provider_directional_sizing_overrides_valid(
    overrides: &Option<BTreeMap<String, CohortProviderSizing>>,
) -> bool {
    overrides.as_ref().is_none_or(|values| {
        let mut sides: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        for (key, sizing) in values {
            let parts = key.split('|').collect::<Vec<_>>();
            if parts.len() != 3
                || parts.iter().any(|part| part.trim().is_empty())
                || !matches!(parts[2], "long" | "short")
                || !provider_sizing_valid(sizing)
            {
                return false;
            }
            sides
                .entry(format!("{}|{}", parts[0], parts[1]))
                .or_default()
                .insert(parts[2].into());
        }
        sides
            .values()
            .all(|directions| directions == &BTreeSet::from(["long".into(), "short".into()]))
    })
}

fn provider_sizing_valid(sizing: &CohortProviderSizing) -> bool {
    sizing.margin_fraction.is_finite()
        && (0.0..=1.0).contains(&sizing.margin_fraction)
        && sizing.margin_fraction > 0.0
        && sizing.max_notional_usd.is_finite()
        && sizing.max_notional_usd > 0.0
}

fn provider_identity_valid(key: &str) -> bool {
    key.split_once('|').is_some_and(|(strategy_id, symbol)| {
        !strategy_id.trim().is_empty() && !symbol.trim().is_empty() && !symbol.contains('|')
    })
}

fn entry_context_overrides_valid(overrides: &Option<BTreeMap<String, String>>) -> bool {
    overrides.as_ref().is_none_or(|values| {
        values.iter().all(|(key, policy)| {
            let Some((strategy_id, symbol)) = key.split_once('|') else {
                return false;
            };
            !strategy_id.trim().is_empty()
                && !symbol.trim().is_empty()
                && !symbol.contains('|')
                && policy == "dual_mtf_not_opposed"
        })
    })
}

fn restart_evidence_valid(evidence: &ConfigurationGenerationEvidenceRaw) -> bool {
    let unique = evidence
        .blocking_assets
        .iter()
        .filter(|value| !value.trim().is_empty())
        .collect::<BTreeSet<_>>();
    if unique.len() != evidence.blocking_assets.len() {
        return false;
    }
    match evidence.restart_state.as_str() {
        "not_required_current_configuration" => {
            evidence.matches_runtime && evidence.blocking_assets.is_empty()
        }
        "candidate_flat_no_orders" => {
            !evidence.matches_runtime && evidence.blocking_assets.is_empty()
        }
        "wait_for_flat_and_no_orders" => {
            !evidence.matches_runtime && !evidence.blocking_assets.is_empty()
        }
        _ => false,
    }
}
