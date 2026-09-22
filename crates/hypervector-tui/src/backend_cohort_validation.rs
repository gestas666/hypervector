//! Structural validation for authoritative cohort ledger projections.

use serde_json::Value;
use std::collections::BTreeSet;
use std::path::Path;

use super::{
    CohortAssetConfig, CohortAssetSnapshot, CohortPositionPolicy, CohortPrestartBackupEvidence,
    CohortProvider, CohortRoutingPolicy, CohortRuntimeConfig, parse_extra,
};
use crate::backend_cohort_provider::validate_specialized_providers;
use crate::backend_cohort_strategy_evidence::{CohortStrategyEvidence, project_strategy_evidence};
use crate::backend_telemetry::LedgerRow;

pub(super) struct CohortIdentityProjection {
    pub enabled_symbols: Vec<String>,
    pub asset_configs: Vec<CohortAssetConfig>,
    pub providers: Vec<CohortProvider>,
    pub strategy_evidence: Vec<CohortStrategyEvidence>,
    pub maximum_concurrent_positions: usize,
    pub config_source_path: Option<String>,
    pub prestart_backup: Option<CohortPrestartBackupEvidence>,
    pub runtime: Option<CohortRuntimeConfig>,
    pub routing_policy: Option<CohortRoutingPolicy>,
}

pub(super) fn project_identity(identity: &LedgerRow) -> Result<CohortIdentityProjection, String> {
    let enabled_symbols: Vec<String> = parse_extra(identity, "enabled_symbols")?;
    let asset_configs: Vec<CohortAssetConfig> = parse_extra(identity, "assets")?;
    let providers: Vec<CohortProvider> = parse_extra(identity, "providers")?;
    let config_source_path = identity
        .extra
        .get("config_source_path")
        .and_then(Value::as_str)
        .map(str::to_string);
    let prestart_backup = parse_prestart_backup(identity)?;
    let runtime = parse_runtime(identity)?;
    let routing_policy = parse_routing_policy(identity)?;
    let position_policy: CohortPositionPolicy = identity
        .position_policy
        .clone()
        .ok_or_else(|| "cohort identity is missing position_policy".to_string())
        .and_then(|value| {
            serde_json::from_value(value)
                .map_err(|error| format!("invalid cohort position_policy: {error}"))
        })?;
    validate_identity(
        &enabled_symbols,
        &asset_configs,
        &providers,
        &position_policy,
    )?;
    let strategy_evidence = project_strategy_evidence(identity, &providers)?;
    Ok(CohortIdentityProjection {
        enabled_symbols,
        asset_configs,
        providers,
        strategy_evidence,
        maximum_concurrent_positions: position_policy.maximum_concurrent_positions,
        config_source_path,
        prestart_backup,
        runtime,
        routing_policy,
    })
}

fn parse_prestart_backup(
    identity: &LedgerRow,
) -> Result<Option<CohortPrestartBackupEvidence>, String> {
    let Some(raw) = identity.extra.get("prestart_backup") else {
        return Ok(None);
    };
    let evidence: CohortPrestartBackupEvidence = serde_json::from_value(raw.clone())
        .map_err(|error| format!("invalid cohort prestart_backup: {error}"))?;
    let paths_valid = !evidence.bundle_path.trim().is_empty()
        && !evidence.manifest_path.trim().is_empty()
        && Path::new(&evidence.manifest_path).parent() == Some(Path::new(&evidence.bundle_path));
    let identity_valid = evidence.status == "verified"
        && evidence.implementation_file_count > 0
        && sha256_valid(&evidence.manifest_sha256)
        && sha256_valid(&evidence.implementation_sha256);
    if !paths_valid || !identity_valid {
        return Err("cohort prestart backup evidence is invalid".into());
    }
    Ok(Some(evidence))
}

fn sha256_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn parse_routing_policy(identity: &LedgerRow) -> Result<Option<CohortRoutingPolicy>, String> {
    let Some(raw) = identity.extra.get("routing_policy") else {
        return Ok(None);
    };
    let policy: CohortRoutingPolicy = serde_json::from_value(raw.clone())
        .map_err(|error| format!("invalid cohort routing_policy: {error}"))?;
    let expected_weights = [("state_1m", 1.0), ("state_5m", 3.0), ("context_15m", 2.0)];
    let weights_valid = expected_weights.iter().all(|(field, expected)| {
        policy
            .state_weights
            .get(*field)
            .is_some_and(|value| value.is_finite() && value == expected)
    });
    if policy.mode != "same_symbol_conflict_preference_v1"
        || policy.alignment_basis != "canonical_1m_5m_15m_1_3_2_v1"
        || policy.state_weights.len() != expected_weights.len()
        || !weights_valid
        || !policy.standalone_intents_ungated
        || policy.forced_regime_exit
        || policy.fallback != "provider_priority_then_decision_time"
    {
        return Err("cohort routing policy contract is unsupported".into());
    }
    Ok(Some(policy))
}

fn parse_runtime(identity: &LedgerRow) -> Result<Option<CohortRuntimeConfig>, String> {
    let runtime: Option<CohortRuntimeConfig> = identity
        .runtime
        .clone()
        .or_else(|| identity.extra.get("runtime").cloned())
        .map(serde_json::from_value)
        .transpose()
        .map_err(|error| format!("invalid cohort runtime: {error}"))?;
    if runtime.as_ref().is_some_and(|value| {
        !value.poll_seconds.is_finite()
            || !(0.0..=60.0).contains(&value.poll_seconds)
            || value.poll_seconds == 0.0
            || value.lookback_days < 3
    }) {
        return Err("cohort runtime settings are structurally invalid".into());
    }
    Ok(runtime)
}

pub(super) fn validate_identity(
    symbols: &[String],
    assets: &[CohortAssetConfig],
    providers: &[CohortProvider],
    position_policy: &CohortPositionPolicy,
) -> Result<(), String> {
    let asset_symbols: Vec<&str> = assets.iter().map(|asset| asset.symbol.as_str()).collect();
    let enabled: Vec<&str> = symbols.iter().map(String::as_str).collect();
    if enabled != asset_symbols || symbols.is_empty() || providers.is_empty() {
        return Err("cohort identity symbols, assets, and providers disagree".into());
    }
    if assets.iter().any(|asset| asset.sides != ["long", "short"]) {
        return Err("cohort assets must declare long and short".into());
    }
    if assets.iter().any(|asset| {
        [
            asset.entry_slippage_cap_fraction,
            asset.market_slippage_cap_fraction,
        ]
        .into_iter()
        .flatten()
        .any(|cap| !cap.is_finite() || !(0.0..=0.05).contains(&cap))
    }) {
        return Err("cohort asset IOC price protection is invalid".into());
    }
    if providers
        .iter()
        .any(|provider| !provider_sides_valid(&provider.sides))
    {
        return Err("cohort provider sides are invalid".into());
    }
    if providers.iter().any(|provider| {
        provider.execution_symbols.as_ref().is_some_and(|symbols| {
            symbols
                .iter()
                .any(|symbol| !provider.symbols.contains(symbol))
                || has_duplicates(symbols)
        })
    }) {
        return Err("cohort provider execution scope is invalid".into());
    }
    if providers.iter().any(invalid_direction_scope) {
        return Err("cohort provider direction scope is invalid".into());
    }
    if providers.iter().any(invalid_entry_context_scope) {
        return Err("cohort provider entry context scope is invalid".into());
    }
    if providers
        .iter()
        .any(|provider| invalid_sizing_scope(provider, assets))
    {
        return Err("cohort provider sizing scope is invalid".into());
    }
    if providers.iter().any(|provider| {
        provider.execution.as_ref().is_some_and(|execution| {
            !recipe_exit_policy_valid(&execution.provider_recipe_exit_policy)
                || !matches!(
                    execution.adaptive_exit_policy.as_str(),
                    "none" | "regime_book_profit_retention_v1"
                )
                || !super::profit_lock_contract_valid(
                    Some(&provider.strategy_id),
                    &execution.profit_lock_policy,
                    execution.profit_lock_activation_bps,
                    execution.profit_lock_floor_bps,
                    execution.profit_lock_giveback_bps,
                )
        })
    }) {
        return Err("cohort provider recipe-exit policy is invalid".into());
    }
    validate_specialized_providers(providers)?;
    if position_policy.max_positions_per_symbol != 1
        || position_policy.maximum_concurrent_positions < executable_asset_count(providers)
    {
        return Err("cohort identity has an invalid position policy".into());
    }
    Ok(())
}

fn executable_asset_count(providers: &[CohortProvider]) -> usize {
    providers
        .iter()
        .flat_map(|provider| {
            provider
                .execution_symbols
                .as_ref()
                .unwrap_or(&provider.symbols)
        })
        .collect::<BTreeSet<_>>()
        .len()
}

fn provider_sides_valid(sides: &[String]) -> bool {
    matches!(sides, [side] if side == "long" || side == "short")
        || matches!(sides, [long, short] if long == "long" && short == "short")
}

/// Mirror the backend's own direction scope, which narrows only executed sides.
///
/// The backend derives executable directions from `execution_symbols` alone, so a
/// side override on a symbol the provider declares but does not execute is inert
/// there. This projection must accept exactly what the execution authority
/// accepts: refusing an inert override would blank the whole cockpit for a live
/// cohort the backend is running normally.
fn invalid_direction_scope(provider: &CohortProvider) -> bool {
    provider
        .execution_side_overrides
        .iter()
        .any(|(symbol, sides)| {
            !provider.symbols.contains(symbol)
                || sides.is_empty()
                || sides.iter().any(|side| side != "long" && side != "short")
                || has_duplicates(sides)
        })
}

fn invalid_entry_context_scope(provider: &CohortProvider) -> bool {
    provider
        .entry_context_overrides
        .iter()
        .any(|(symbol, policy)| {
            provider.strategy_id != "range_onset_bidirectional_v1"
                || provider
                    .execution_symbols
                    .as_ref()
                    .is_none_or(|symbols| !symbols.contains(symbol))
                || policy != "dual_mtf_not_opposed"
        })
}

fn invalid_sizing_scope(provider: &CohortProvider, assets: &[CohortAssetConfig]) -> bool {
    provider.sizing_overrides.iter().any(|(symbol, sizing)| {
        let execution_enabled = provider
            .execution_symbols
            .as_ref()
            .is_some_and(|symbols| symbols.contains(symbol));
        let asset = assets.iter().find(|asset| asset.symbol == *symbol);
        !execution_enabled
            || asset.is_none_or(|asset| {
                !sizing.margin_fraction.is_finite()
                    || !(0.0..=1.0).contains(&sizing.margin_fraction)
                    || sizing.margin_fraction == 0.0
                    || !sizing.max_notional_usd.is_finite()
                    || sizing.max_notional_usd <= 0.0
                    || sizing.max_notional_usd > asset.max_notional_usd
            })
    })
}

pub(super) fn validate_snapshot(
    symbols: &[String],
    assets: &[CohortAssetSnapshot],
) -> Result<(), String> {
    let observed: Vec<&str> = assets.iter().map(|asset| asset.symbol.as_str()).collect();
    let expected: Vec<&str> = symbols.iter().map(String::as_str).collect();
    if observed != expected {
        return Err("cohort snapshot symbols differ from configured symbols".into());
    }
    if assets
        .iter()
        .any(|asset| asset.direction_capability != ["long", "short"])
    {
        return Err("cohort snapshot lost bidirectional capability".into());
    }
    if assets.iter().any(|asset| {
        (asset.target_oid.is_none() != asset.target_price.is_none())
            || (asset.position_side.is_none()
                && (asset.stop_oid.is_some() || asset.target_oid.is_some()))
    }) {
        return Err("cohort snapshot bracket identity is inconsistent".into());
    }
    if assets.iter().any(|asset| {
        asset.execution_plan.as_ref().is_some_and(|plan| {
            !recipe_exit_policy_valid(&plan.provider_recipe_exit_policy)
                || !matches!(
                    plan.adaptive_exit_policy.as_str(),
                    "none" | "regime_book_profit_retention_v1"
                )
                || !super::profit_lock_contract_valid(
                    Some(&plan.strategy_id),
                    &plan.profit_lock_policy,
                    plan.profit_lock_activation_bps,
                    plan.profit_lock_floor_bps,
                    plan.profit_lock_giveback_bps,
                )
        })
    }) {
        return Err("cohort snapshot exit policy is invalid".into());
    }
    Ok(())
}

fn recipe_exit_policy_valid(policy: &str) -> bool {
    matches!(policy, "ignore" | "honor")
}

fn has_duplicates(values: &[String]) -> bool {
    values
        .iter()
        .enumerate()
        .any(|(index, value)| values[..index].contains(value))
}

pub(super) fn validate_regime_preference(
    score: Option<f64>,
    stance: Option<&str>,
    decision_time_ms: Option<u64>,
    basis: Option<&str>,
) -> Result<(), String> {
    let present = [
        score.is_some(),
        stance.is_some(),
        decision_time_ms.is_some(),
        basis.is_some(),
    ];
    if present.iter().all(|value| !value) {
        return Ok(());
    }
    if !present.iter().all(|value| *value) {
        return Err("cohort regime routing preference is incomplete".into());
    }
    if score.is_none_or(|value| !value.is_finite() || !(-1.0..=1.0).contains(&value)) {
        return Err("cohort regime routing score is invalid".into());
    }
    if !matches!(
        stance,
        Some("directionally_supported" | "directionally_opposed" | "mixed_or_transition")
    ) {
        return Err("cohort regime routing stance is invalid".into());
    }
    if basis.is_none_or(|value| value.trim().is_empty()) {
        return Err("cohort regime routing basis is invalid".into());
    }
    Ok(())
}

#[cfg(test)]
#[path = "backend_cohort_validation_tests.rs"]
mod direction_scope_tests;
