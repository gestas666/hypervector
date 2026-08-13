//! Structural validation for authoritative cohort ledger projections.

use serde_json::Value;
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
    if assets.iter().any(|asset| asset.sides != ["long", "short"])
        || providers
            .iter()
            .any(|provider| provider.sides != ["long", "short"])
    {
        return Err("cohort identity must declare long and short everywhere".into());
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
                || !super::profit_lock_contract_valid(
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
        || position_policy.maximum_concurrent_positions < symbols.len()
    {
        return Err("cohort identity has an invalid position policy".into());
    }
    Ok(())
}

fn invalid_direction_scope(provider: &CohortProvider) -> bool {
    provider
        .execution_side_overrides
        .iter()
        .any(|(symbol, sides)| {
            provider
                .execution_symbols
                .as_ref()
                .is_none_or(|symbols| !symbols.contains(symbol))
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
        asset
            .execution_plan
            .as_ref()
            .is_some_and(|plan| !recipe_exit_policy_valid(&plan.provider_recipe_exit_policy))
    }) {
        return Err("cohort snapshot recipe-exit policy is invalid".into());
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
mod direction_scope_tests {
    use std::collections::BTreeMap;

    use serde_json::json;

    use super::{parse_prestart_backup, recipe_exit_policy_valid, validate_identity};
    use crate::backend_cohort::{CohortAssetConfig, CohortPositionPolicy, CohortProvider};
    use crate::backend_telemetry::LedgerRow;

    fn backup_row(manifest_hash: &str) -> LedgerRow {
        serde_json::from_value(json!({
            "prestart_backup": {
                "status": "verified",
                "bundle_path": "data/backups/prestart_test",
                "manifest_path": "data/backups/prestart_test/manifest.json",
                "manifest_sha256": manifest_hash,
                "strategy_changed": true,
                "implementation_file_count": 1156,
                "implementation_sha256": "b".repeat(64)
            }
        }))
        .expect("ledger row")
    }

    #[test]
    fn validates_exact_prestart_backup_identity() {
        let parsed = parse_prestart_backup(&backup_row(&"a".repeat(64)))
            .expect("valid backup")
            .expect("backup present");

        assert_eq!(parsed.implementation_file_count, 1_156);
        assert!(parsed.strategy_changed);
    }

    #[test]
    fn rejects_malformed_prestart_backup_hash() {
        let error =
            parse_prestart_backup(&backup_row("not-a-sha")).expect_err("malformed hash must fail");

        assert!(error.contains("backup evidence is invalid"));
    }

    #[test]
    fn accepts_only_explicit_recipe_exit_policies() {
        assert!(recipe_exit_policy_valid("ignore"));
        assert!(recipe_exit_policy_valid("honor"));
        assert!(!recipe_exit_policy_valid("sometimes"));
    }

    #[test]
    fn accepts_one_sided_execution_without_losing_bidirectional_observation() {
        let symbols = vec!["ETH".into()];
        let assets = vec![CohortAssetConfig {
            symbol: "ETH".into(),
            sides: vec!["long".into(), "short".into()],
            leverage: 5.0,
            venue_max_leverage: 25.0,
            margin_fraction: 0.03,
            max_notional_usd: 25.0,
            stop_bps: 60.0,
            maximum_hold_seconds: 172_800,
        }];
        let providers = vec![CohortProvider {
            strategy_id: "range_onset_bidirectional_v1".into(),
            symbols: symbols.clone(),
            sides: vec!["long".into(), "short".into()],
            priority: 20,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols.clone()),
            execution_side_overrides: BTreeMap::from([("ETH".into(), vec!["long".into()])]),
            entry_context_overrides: BTreeMap::from([(
                "ETH".into(),
                "dual_mtf_not_opposed".into(),
            )]),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        }];
        let policy = CohortPositionPolicy {
            max_positions_per_symbol: 1,
            maximum_concurrent_positions: 1,
        };

        validate_identity(&symbols, &assets, &providers, &policy).expect("valid direction scope");
    }

    #[test]
    fn rejects_position_capacity_below_enabled_asset_count() {
        let symbols: Vec<String> = vec!["BTC".into(), "ETH".into()];
        let assets: Vec<CohortAssetConfig> = symbols
            .iter()
            .map(|symbol| CohortAssetConfig {
                symbol: symbol.clone(),
                sides: vec!["long".into(), "short".into()],
                leverage: 5.0,
                venue_max_leverage: 25.0,
                margin_fraction: 0.03,
                max_notional_usd: 25.0,
                stop_bps: 60.0,
                maximum_hold_seconds: 172_800,
            })
            .collect();
        let providers = vec![CohortProvider {
            strategy_id: "range_onset_bidirectional_v1".into(),
            symbols: symbols.clone(),
            sides: vec!["long".into(), "short".into()],
            priority: 20,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols.clone()),
            execution_side_overrides: BTreeMap::new(),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        }];
        let policy = CohortPositionPolicy {
            max_positions_per_symbol: 1,
            maximum_concurrent_positions: 1,
        };

        let error = validate_identity(&symbols, &assets, &providers, &policy)
            .expect_err("each enabled asset must own one position slot");

        assert!(error.contains("invalid position policy"));
    }

    #[test]
    fn accepts_position_capacity_above_enabled_asset_count() {
        let symbols: Vec<String> = vec!["BTC".into(), "ETH".into()];
        let assets: Vec<CohortAssetConfig> = symbols
            .iter()
            .map(|symbol| CohortAssetConfig {
                symbol: symbol.clone(),
                sides: vec!["long".into(), "short".into()],
                leverage: 5.0,
                venue_max_leverage: 25.0,
                margin_fraction: 0.03,
                max_notional_usd: 25.0,
                stop_bps: 60.0,
                maximum_hold_seconds: 172_800,
            })
            .collect();
        let providers = vec![CohortProvider {
            strategy_id: "range_onset_bidirectional_v1".into(),
            symbols: symbols.clone(),
            sides: vec!["long".into(), "short".into()],
            priority: 20,
            timeframe: "1m".into(),
            maximum_entry_delay_seconds: 60,
            execution_symbols: Some(symbols.clone()),
            execution_side_overrides: BTreeMap::new(),
            entry_context_overrides: BTreeMap::new(),
            sizing_overrides: BTreeMap::new(),
            source_profile: None,
            execution: None,
        }];
        let policy = CohortPositionPolicy {
            max_positions_per_symbol: 1,
            maximum_concurrent_positions: 3,
        };

        validate_identity(&symbols, &assets, &providers, &policy)
            .expect("unused capacity may reserve a future asset slot");
    }
}
