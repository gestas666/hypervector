use hypervector_tui::backend_growth_preflight::parse_growth_preflight;
use serde_json::{Value, json};

fn document() -> Value {
    json!({
        "schema_version": 1,
        "observed_at_utc": "2026-08-10T21:54:48.514123+00:00",
        "identity": {
            "active_profile_id": "multi_asset_bidirectional_all_live_canary_v35",
            "active_profile_fingerprint": "a".repeat(64),
            "candidate_profile_id": "multi_asset_bidirectional_growth_5000_candidate_v37",
            "candidate_profile_fingerprint": "b".repeat(64),
            "candidate_source_path": "configs/growth_v37.toml",
            "candidate_differs_from_active": true,
            "network": "mainnet",
            "margin_mode": "isolated"
        },
        "authority": {
            "execution_authority": "none",
            "execution_client_constructed": false,
            "signing_key_required": false,
            "operation": "multi_asset_read_only_preflight"
        },
        "portfolio": {
            "configured_assets": 2,
            "maximum_positions": 10,
            "unused_capacity_slots": 8,
            "maximum_configured_margin_fraction": 0.06,
            "sizing_reference_equity_usd": 5000.0,
            "sizing_reference_source": "explicit_scenario",
            "open_positions": 1,
            "open_orders": 1,
            "flat_no_orders": false,
            "transition_blocking_assets": ["xyz:GOLD"],
            "ledger_reconciled": true,
            "sizing_technically_ready": false,
            "technically_ready_for_profile_transition": false,
            "readiness_reasons": [
                "venue is not flat with no open orders",
                "planned sizing lacks minimum-lot, visible-depth, or effective fee support"
            ],
            "performance_gate": false,
            "balance_gate": false
        },
        "assets": [
            asset("BTC", "resolved_account_base", Some(4.5), true),
            asset("xyz:GOLD", "unresolved_growth_mode", None, false)
        ],
        "limitations": ["point in time"]
    })
}

fn asset(symbol: &str, fee_status: &str, fee_bps: Option<f64>, ready: bool) -> Value {
    json!({
        "symbol": symbol,
        "venue": {
            "mark_price": 100.0,
            "effective_fee_status": fee_status,
            "effective_taker_fee_rate": fee_bps.map(|value| value / 10000.0),
            "one_way_taker_fee_bps": fee_bps
        },
        "position": {"size_signed": if symbol == "xyz:GOLD" { 0.01 } else { 0.0 }},
        "open_orders": if symbol == "xyz:GOLD" { json!([{"oid": 9}]) } else { json!([]) },
        "protection": {"status": if symbol == "xyz:GOLD" { "protected" } else { "not_applicable_flat" }},
        "ledger_reconciliation": {"matches": true},
        "sizing": {
            "sizing_reference_equity_usd": 5000.0,
            "margin_fraction": 0.03,
            "leverage": 5.0,
            "max_notional_usd": 750.0,
            "planned_margin_usd": 150.0,
            "planned_notional_usd": 750.0,
            "minimum_lot_notional_usd": 1.0,
            "above_minimum_lot": true
        },
        "visible_depth": {
            "buy_complete": true,
            "buy_visible_cost_bps": 0.2,
            "sell_complete": true,
            "sell_visible_cost_bps": 0.3
        },
        "sizing_technically_ready": ready
    })
}

#[test]
fn parses_blocked_growth_candidate_without_converting_it_to_runtime() {
    let parsed = parse_growth_preflight(&document().to_string()).expect("valid preflight");

    assert!(parsed.available);
    assert_eq!(
        parsed.candidate_profile_id.as_deref(),
        Some("multi_asset_bidirectional_growth_5000_candidate_v37")
    );
    assert_eq!(parsed.sizing_reference_equity_usd, Some(5000.0));
    assert_eq!(parsed.maximum_positions, Some(10));
    assert!(!parsed.sizing_technically_ready.unwrap());
    assert!(!parsed.technically_ready_for_profile_transition.unwrap());
    assert_eq!(parsed.transition_blocking_assets, ["xyz:GOLD"]);
    assert_eq!(parsed.assets[0].one_way_taker_fee_bps, Some(4.5));
    assert_eq!(
        parsed.assets[1].effective_fee_status,
        "unresolved_growth_mode"
    );
}

#[test]
fn rejects_execution_authority_and_success_shaped_unresolved_fee() {
    let mut armed = document();
    armed["authority"]["execution_authority"] = json!("hyperliquid_mainnet");
    assert!(
        parse_growth_preflight(&armed.to_string())
            .unwrap_err()
            .contains("authority")
    );

    let mut fake_fee = document();
    fake_fee["assets"][1]["venue"]["one_way_taker_fee_bps"] = json!(4.5);
    assert!(
        parse_growth_preflight(&fake_fee.to_string())
            .unwrap_err()
            .contains("fee")
    );
}

#[test]
fn rejects_portfolio_readiness_that_disagrees_with_asset_evidence() {
    let mut contradictory = document();
    contradictory["portfolio"]["sizing_technically_ready"] = json!(true);

    assert!(
        parse_growth_preflight(&contradictory.to_string())
            .unwrap_err()
            .contains("readiness")
    );
}

#[test]
fn retired_open_gold_remains_visible_as_a_transition_blocker() {
    let mut report = document();
    report["assets"] = json!([asset("BTC", "resolved_account_base", Some(4.5), true)]);
    report["retired_assets"] = json!([{
        "symbol": "xyz:GOLD",
        "position_size_signed": 0.0171,
        "open_order_ids": [9],
        "ledger_position_size_signed": 0.0171,
        "ledger_owned_order_ids": [9],
        "ledger_reconciled": true,
        "flat_no_orders": false
    }]);
    report["portfolio"]["configured_assets"] = json!(1);
    report["portfolio"]["unused_capacity_slots"] = json!(9);
    report["portfolio"]["maximum_configured_margin_fraction"] = json!(0.03);
    report["portfolio"]["sizing_technically_ready"] = json!(true);
    report["portfolio"]["readiness_reasons"] = json!(["venue is not flat with no open orders"]);
    report["profile_change_approval"] = json!({
        "state": "approved_profile_change",
        "approval_required": true,
        "approval_status": "approved_for_live_transition",
        "approval_document": "docs/live-approvals/v63-to-v64.json",
        "retired_execution_scopes": ["provider|xyz:GOLD|long"],
        "replacement_execution_scopes": [],
        "execution_authority": "none"
    });

    let parsed = parse_growth_preflight(&report.to_string()).expect("retired GOLD is valid");

    assert_eq!(parsed.transition_blocking_assets, ["xyz:GOLD"]);
    assert_eq!(parsed.open_positions, Some(1));
    assert_eq!(parsed.open_orders, Some(1));
    assert_eq!(parsed.assets.len(), 1);
    assert_eq!(parsed.assets[0].symbol, "BTC");
    assert_eq!(parsed.retired_assets.len(), 1);
    assert_eq!(parsed.retired_assets[0].symbol, "xyz:GOLD");
    assert!(!parsed.retired_assets[0].flat_no_orders);
    assert!(parsed.retired_assets[0].ledger_reconciled);
    let approval = parsed.profile_change_approval.expect("profile approval");
    assert_eq!(approval.state, "approved_profile_change");
    assert_eq!(approval.retired_execution_scopes.len(), 1);
    assert!(approval.replacement_execution_scopes.is_empty());
}

#[test]
fn rejects_profile_change_approval_that_claims_execution_authority() {
    let mut report = document();
    report["profile_change_approval"] = json!({
        "state": "approved_profile_change",
        "approval_required": true,
        "approval_status": "approved_for_live_transition",
        "approval_document": "docs/live-approvals/change.json",
        "retired_execution_scopes": [],
        "replacement_execution_scopes": [],
        "execution_authority": "hyperliquid_mainnet"
    });

    assert!(
        parse_growth_preflight(&report.to_string())
            .unwrap_err()
            .contains("profile change approval")
    );
}
