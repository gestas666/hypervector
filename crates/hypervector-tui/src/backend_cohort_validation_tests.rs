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

fn asset(symbol: &str) -> CohortAssetConfig {
    CohortAssetConfig {
        symbol: symbol.into(),
        sides: vec!["long".into(), "short".into()],
        leverage: 5.0,
        venue_max_leverage: 25.0,
        margin_fraction: 0.03,
        max_notional_usd: 25.0,
        entry_slippage_cap_fraction: None,
        market_slippage_cap_fraction: None,
        stop_bps: 60.0,
        maximum_hold_seconds: 172_800,
    }
}

fn provider(symbols: &[String]) -> CohortProvider {
    CohortProvider {
        strategy_id: "range_onset_bidirectional_v1".into(),
        symbols: symbols.to_vec(),
        sides: vec!["long".into(), "short".into()],
        priority: 20,
        timeframe: "1m".into(),
        maximum_entry_delay_seconds: 60,
        execution_symbols: Some(symbols.to_vec()),
        execution_side_overrides: BTreeMap::new(),
        entry_context_overrides: BTreeMap::new(),
        sizing_overrides: BTreeMap::new(),
        source_profile: None,
        execution: None,
    }
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
fn accepts_one_sided_provider_without_losing_bidirectional_asset() {
    let symbols = vec!["ETH".into()];
    let assets = vec![asset("ETH")];
    let mut one_sided = provider(&symbols);
    one_sided.sides = vec!["long".into()];
    one_sided.execution_side_overrides = BTreeMap::from([("ETH".into(), vec!["long".into()])]);
    one_sided.entry_context_overrides =
        BTreeMap::from([("ETH".into(), "dual_mtf_not_opposed".into())]);
    let policy = CohortPositionPolicy {
        max_positions_per_symbol: 1,
        maximum_concurrent_positions: 1,
    };

    validate_identity(&symbols, &assets, &[one_sided], &policy).expect("valid direction scope");
}

#[test]
fn rejects_position_capacity_below_enabled_asset_count() {
    let symbols: Vec<String> = vec!["BTC".into(), "ETH".into()];
    let assets = symbols
        .iter()
        .map(|symbol| asset(symbol))
        .collect::<Vec<_>>();
    let providers = vec![provider(&symbols)];
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
    let assets = symbols
        .iter()
        .map(|symbol| asset(symbol))
        .collect::<Vec<_>>();
    let providers = vec![provider(&symbols)];
    let policy = CohortPositionPolicy {
        max_positions_per_symbol: 1,
        maximum_concurrent_positions: 3,
    };

    validate_identity(&symbols, &assets, &providers, &policy)
        .expect("unused capacity may reserve a future asset slot");
}

#[test]
fn accepts_visible_observe_only_assets_outside_execution_capacity() {
    let symbols: Vec<String> = vec!["BTC".into(), "ETH".into()];
    let assets = symbols
        .iter()
        .map(|symbol| asset(symbol))
        .collect::<Vec<_>>();
    let mut observe_only = provider(&symbols);
    observe_only.execution_symbols = Some(vec!["BTC".into()]);
    let policy = CohortPositionPolicy {
        max_positions_per_symbol: 1,
        maximum_concurrent_positions: 1,
    };

    validate_identity(&symbols, &assets, &[observe_only], &policy)
        .expect("observe-only assets do not consume execution slots");
}
