#[test]
fn parses_ready_lifecycle_and_learning_evidence() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-02T04:00:00+00:00",
        "venue_portfolio": {
            "status": "observed",
            "portfolio_value_usd": 507.08,
            "execution_collateral_value_usd": 504.11,
            "non_usdc_spot_value_usd": 2.97,
            "vault_equity_usd": 0.0,
            "valued_spot_assets": [
                {"symbol":"USDC","token_index":0,"total":504.11,"price_usd":1.0,"value_usd":504.11,"market":"USDC_PAR"},
                {"symbol":"AAPL","token_index":413,"total":0.00972,"price_usd":305.5555555556,"value_usd":2.97,"market":"@268"}
            ],
            "observed_at_utc": "2026-08-04T09:00:00+00:00",
            "valuation_source": "spot_midpoints_plus_vault_equity",
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "execution_collateral_unchanged": true
            }
        },
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC":"FLAT","ETH":"OPEN","SOL":"FLAT","HYPE":"FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "risk_utilization": {
                "schema_version": 1,
                "mode": "cohort_runtime_risk_utilization_v1",
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "performance_gate": false,
                    "balance_gate": false,
                    "automatic_sizing_change": false
                },
                "account_value_usd": 500.0,
                "summary": {
                    "configured_assets": 1,
                    "cap_bound_assets": 1,
                    "configured_maximum_positions": 1,
                    "provider_symbols": 1,
                    "provider_symbol_overrides": 0,
                    "maximum_simultaneous_effective_margin_fraction": 0.01
                },
                "by_asset": {
                    "HYPE": {
                        "configured_leverage": 5.0,
                        "configured_margin_fraction": 0.03,
                        "configured_max_notional_usd": 25.0,
                        "uncapped_notional_usd": 75.0,
                        "planned_notional_usd": 25.0,
                        "planned_margin_usd": 5.0,
                        "effective_margin_fraction": 0.01,
                        "notional_fraction_of_equity": 0.05,
                        "cap_utilization_ratio": 0.3333333333333333,
                        "cap_binding": true
                    }
                },
                "by_provider_symbol": {
                    "hype_breakout_onset_bidirectional_v1|HYPE": {
                        "configured_leverage": 5.0,
                        "configured_margin_fraction": 0.03,
                        "configured_max_notional_usd": 25.0,
                        "uncapped_notional_usd": 75.0,
                        "planned_notional_usd": 25.0,
                        "planned_margin_usd": 5.0,
                        "effective_margin_fraction": 0.01,
                        "notional_fraction_of_equity": 0.05,
                        "cap_utilization_ratio": 0.3333333333333333,
                        "cap_binding": true,
                        "sizing_source": "asset_default"
                    }
                }
            },
            "allocation_challenger": {
                "schema_version": 1,
                "mode": "cohort_selective_allocation_challenger_v1",
                "status": "candidate_not_active",
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "runtime_strategy_changed": false,
                    "automatic_sizing_change": false,
                    "automatic_promotion": false,
                    "performance_gate": false,
                    "balance_gate": false
                },
                "target_provider_symbol": "hype_breakout_onset_bidirectional_v1|HYPE",
                "account_value_usd": 500.0,
                "current": {
                    "configured_leverage": 5.0,
                    "configured_margin_fraction": 0.03,
                    "configured_max_notional_usd": 25.0,
                    "uncapped_notional_usd": 75.0,
                    "planned_notional_usd": 25.0,
                    "planned_margin_usd": 5.0,
                    "effective_margin_fraction": 0.01,
                    "cap_binding": true
                },
                "candidate": {
                    "configured_leverage": 5.0,
                    "configured_margin_fraction": 0.03,
                    "configured_max_notional_usd": 75.0,
                    "uncapped_notional_usd": 75.0,
                    "planned_notional_usd": 75.0,
                    "planned_margin_usd": 15.0,
                    "effective_margin_fraction": 0.03,
                    "cap_binding": false,
                    "effective_change": true
                },
                "portfolio": {
                    "current_maximum_margin_fraction": 0.01,
                    "candidate_maximum_margin_fraction": 0.03,
                    "change_percentage_points": 2.0
                },
                "required_profile_changes": {
                    "asset": "HYPE",
                    "candidate_asset_ceiling_usd": 75.0,
                    "candidate_target_cap_usd": 75.0,
                    "pinned_provider_symbols": [
                        "hulk_expansion_bidirectional_tuned_v2|HYPE",
                        "range_onset_bidirectional_v1|HYPE"
                    ],
                    "restart_required": true
                },
                "execution_sample": {
                    "status": "resolved_live_sample",
                    "closed_trades": 4,
                    "net_pnl_usd": 1.004659,
                    "profit_factor": 5.486747
                },
                "profit_forecast": null,
                "limitations": ["descriptive live sample only"]
            },
            "readiness": {"evaluations": 8},
            "execution": {"closed_trades": 2, "net_pnl_usd": 1.25},
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid checkpoint");

    assert!(parsed.configured);
    assert!(parsed.available);
    assert_eq!(
        parsed.lifecycle_state.as_deref(),
        Some("running_consistent")
    );
    assert_eq!(parsed.cohort_heartbeat_status.as_deref(), Some("running"));
    assert_eq!(parsed.asset_states["ETH"], "OPEN");
    assert_eq!(parsed.coverage_complete, Some(true));
    assert_eq!(parsed.readiness_evaluations, Some(8));
    assert_eq!(parsed.closed_trades, Some(2));
    assert_eq!(parsed.net_pnl_usd, Some(1.25));
    let portfolio_value = parsed.venue_portfolio.expect("venue portfolio");
    assert_eq!(portfolio_value.portfolio_value_usd, 507.08);
    assert_eq!(portfolio_value.execution_collateral_value_usd, 504.11);
    assert_eq!(portfolio_value.non_usdc_spot_value_usd, 2.97);
    assert_eq!(portfolio_value.valued_spot_assets.len(), 2);
    let risk = parsed.risk_utilization.expect("risk utilization");
    assert_eq!(risk.cap_bound_assets, 1);
    assert_eq!(risk.configured_assets, 1);
    assert_eq!(risk.configured_maximum_positions, 1);
    assert_eq!(risk.maximum_effective_margin_fraction, 0.01);
    assert_eq!(risk.provider_symbols, 1);
    assert_eq!(risk.provider_symbol_overrides, 0);
    assert_eq!(
        risk.by_provider_symbol["hype_breakout_onset_bidirectional_v1|HYPE"].sizing_source,
        "asset_default"
    );
    assert!(risk.by_asset["HYPE"].cap_binding);
    assert_eq!(risk.by_asset["HYPE"].effective_margin_fraction, 0.01);
    let allocation = parsed.allocation_challenger.expect("allocation challenger");
    assert_eq!(allocation.current.planned_notional_usd, 25.0);
    assert_eq!(allocation.candidate.planned_notional_usd, 75.0);
    assert_eq!(allocation.execution_sample.closed_trades, Some(4));
    assert_eq!(
        parsed.evidence_state.as_deref(),
        Some("descriptive_trade_evidence")
    );
}

#[test]
fn rejects_venue_portfolio_with_execution_authority_or_bad_reconciliation() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["venue_portfolio"] = serde_json::json!({
        "status": "observed",
        "portfolio_value_usd": 507.08,
        "execution_collateral_value_usd": 504.11,
        "non_usdc_spot_value_usd": 2.97,
        "vault_equity_usd": 0.0,
        "valued_spot_assets": [],
        "observed_at_utc": "2026-08-04T09:00:00+00:00",
        "valuation_source": "spot_midpoints_plus_vault_equity",
        "contract": {
            "report_only": true,
            "execution_authority": "hyperliquid_mainnet",
            "execution_collateral_unchanged": true
        }
    });

    let error =
        parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject authority");
    assert!(error.contains("venue portfolio contract"));

    checkpoint["venue_portfolio"]["contract"]["execution_authority"] = "none".into();
    checkpoint["venue_portfolio"]["portfolio_value_usd"] = 600.0.into();
    let error = parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reconcile");
    assert!(error.contains("venue portfolio total"));
}

fn minimal_checkpoint() -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-04T09:00:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC": "FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "no_closed_trade_evidence"}
        }
    })
}

#[test]
fn parses_v79_poststart_acceptance_for_operator_visibility() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["poststart_acceptance"] = valid_v79_poststart_acceptance();

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("V79 checkpoint");
    let acceptance = parsed.poststart_acceptance.expect("V79 acceptance");
    assert!(acceptance.accepted);
    assert_eq!(acceptance.expected_routes, 9);
    assert_eq!(acceptance.evaluated_routes, 9);
    assert_eq!(acceptance.routes_with_metrics, 9);
    assert_eq!(acceptance.open_positions, 1);
    assert_eq!(acceptance.fills, 2);
    assert_eq!(acceptance.costed_fills, 2);
    assert_eq!(acceptance.closed_trades, 1);
}

#[test]
fn parses_v80_poststart_acceptance_with_exact_version_label() {
    let mut checkpoint = minimal_checkpoint();
    let mut verdict = valid_v79_poststart_acceptance();
    verdict["schema_version"] = "v80_poststart_acceptance_v1".into();
    checkpoint["poststart_acceptance"] = verdict;

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("V80 checkpoint");
    let acceptance = parsed.poststart_acceptance.expect("V80 acceptance");

    assert_eq!(acceptance.version, "V80");
    assert!(acceptance.accepted);
}

#[test]
fn parses_v85_poststart_acceptance_with_exact_version_label() {
    let mut checkpoint = minimal_checkpoint();
    let mut verdict = valid_v79_poststart_acceptance();
    verdict["schema_version"] = "v85_poststart_acceptance_v1".into();
    checkpoint["poststart_acceptance"] = verdict;

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("V85 checkpoint");
    let acceptance = parsed.poststart_acceptance.expect("V85 acceptance");

    assert_eq!(acceptance.version, "V85");
    assert!(acceptance.accepted);
}

#[test]
fn parses_v86_poststart_acceptance_with_exact_version_label() {
    let mut checkpoint = minimal_checkpoint();
    let mut verdict = valid_v79_poststart_acceptance();
    verdict["schema_version"] = "v86_poststart_acceptance_v1".into();
    checkpoint["poststart_acceptance"] = verdict;

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("V86 checkpoint");
    let acceptance = parsed.poststart_acceptance.expect("V86 acceptance");

    assert_eq!(acceptance.version, "V86");
    assert!(acceptance.accepted);
}

#[test]
fn rejects_v79_acceptance_with_failed_position_protection() {
    let mut checkpoint = minimal_checkpoint();
    let mut acceptance = valid_v79_poststart_acceptance();
    acceptance["checks"]["position_protection"]["passed"] = false.into();
    acceptance["checks"]["position_protection"]["reasons"] =
        serde_json::json!(["open_entry_fill_invalid:BTC"]);
    checkpoint["poststart_acceptance"] = acceptance;

    let error = parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject");
    assert!(error.contains("post-start acceptance"), "{error}");
}

#[test]
fn parses_coherent_v79_position_protection_failure() {
    let mut checkpoint = minimal_checkpoint();
    let mut acceptance = rejected_v79_position_protection();
    acceptance["reasons"] = serde_json::json!(["open_entry_fill_invalid:BTC"]);
    checkpoint["poststart_acceptance"] = acceptance;

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("V79 rejection");
    let result = parsed.poststart_acceptance.expect("V79 acceptance");
    assert!(!result.accepted);
    assert_eq!(result.reasons, ["open_entry_fill_invalid:BTC"]);
    assert_eq!(result.open_positions, 1);
}

#[test]
fn rejects_v79_global_reasons_that_disagree_with_checks() {
    let mut checkpoint = minimal_checkpoint();
    let mut acceptance = rejected_v79_position_protection();
    acceptance["reasons"] = serde_json::json!(["provider_monitoring_incomplete"]);
    checkpoint["poststart_acceptance"] = acceptance;

    let error = parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject");
    assert!(error.contains("post-start acceptance"), "{error}");
}

#[test]
fn rejects_inconsistent_v79_poststart_acceptance() {
    let mut checkpoint = minimal_checkpoint();
    let mut acceptance = valid_v79_poststart_acceptance();
    acceptance["checks"]["closed_lifecycle_integrity"]["passed"] = false.into();
    acceptance["checks"]["closed_lifecycle_integrity"]["reasons"] =
        serde_json::json!(["closed_lifecycle_invalid:BTC:10"]);
    checkpoint["poststart_acceptance"] = acceptance;

    let error = parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject");
    assert!(error.contains("post-start acceptance"), "{error}");
}

fn valid_v79_poststart_acceptance() -> serde_json::Value {
    serde_json::json!({
        "schema_version": "v79_poststart_acceptance_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "automatic_pause": false,
            "automatic_retuning": false,
            "performance_gate": false
        },
        "accepted": true,
        "decision": "accepted",
        "reasons": [],
        "checks": {
            "checkpoint_contract": {"passed": true, "reasons": []},
            "runtime_identity": {"passed": true, "reasons": []},
            "runtime_freshness": {"passed": true, "reasons": []},
            "runtime_execution_contracts": {"passed": true, "reasons": []},
            "provider_monitoring": {
                "passed": true,
                "reasons": [],
                "expected_routes": 9,
                "evaluated_routes": 9,
                "routes_with_metrics": 9
            },
            "position_protection": {
                "passed": true,
                "reasons": [],
                "open_positions": 1
            },
            "execution_attribution": {
                "passed": true,
                "reasons": [],
                "fills": 2,
                "costed_fills": 2
            },
            "closed_lifecycle_integrity": {
                "passed": true,
                "reasons": [],
                "closed_trades": 1
            },
            "accounting_epoch": {"passed": true, "reasons": []}
        }
    })
}

fn rejected_v79_position_protection() -> serde_json::Value {
    let mut acceptance = valid_v79_poststart_acceptance();
    acceptance["accepted"] = false.into();
    acceptance["decision"] = "rejected".into();
    acceptance["checks"]["position_protection"]["passed"] = false.into();
    acceptance["checks"]["position_protection"]["reasons"] =
        serde_json::json!(["open_entry_fill_invalid:BTC"]);
    acceptance
}

#[test]
fn accepts_unused_position_capacity_above_the_configured_asset_count() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["lifecycle"]["asset_states"] = serde_json::json!({
        "BTC": "FLAT",
        "ETH": "FLAT"
    });
    checkpoint["audit"]["risk_utilization"] = serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_runtime_risk_utilization_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "performance_gate": false,
            "balance_gate": false,
            "automatic_sizing_change": false
        },
        "account_value_usd": 500.0,
        "summary": {
            "configured_assets": 2,
            "cap_bound_assets": 2,
            "configured_maximum_positions": 3,
            "maximum_simultaneous_effective_margin_fraction": 0.02
        },
        "by_asset": {
            "BTC": risk_asset(),
            "ETH": risk_asset()
        }
    });

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect("unused portfolio capacity is valid");
    let risk = parsed.risk_utilization.expect("risk utilization");

    assert_eq!(risk.configured_assets, 2);
    assert_eq!(risk.configured_maximum_positions, 3);
    assert_eq!(risk.maximum_effective_margin_fraction, 0.02);
}

#[test]
fn excludes_observe_only_assets_from_live_risk_capacity() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["lifecycle"]["asset_states"] = serde_json::json!({
        "BTC": "FLAT",
        "ETH": "FLAT",
        "ZEC": "FLAT"
    });
    checkpoint["audit"]["risk_utilization"] = serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_runtime_risk_utilization_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "performance_gate": false,
            "balance_gate": false,
            "automatic_sizing_change": false
        },
        "account_value_usd": 500.0,
        "summary": {
            "configured_assets": 3,
            "executable_assets": 1,
            "cap_bound_assets": 3,
            "configured_maximum_positions": 1,
            "provider_symbols": 1,
            "provider_symbol_overrides": 0,
            "provider_direction_overrides": 0,
            "maximum_simultaneous_effective_margin_fraction": 0.01
        },
        "by_asset": {
            "BTC": risk_asset(),
            "ETH": risk_asset(),
            "ZEC": risk_asset()
        },
        "by_provider_symbol": {
            "btc_short|BTC": {
                "configured_leverage": 5.0,
                "configured_margin_fraction": 0.03,
                "configured_max_notional_usd": 25.0,
                "uncapped_notional_usd": 75.0,
                "planned_notional_usd": 25.0,
                "planned_margin_usd": 5.0,
                "effective_margin_fraction": 0.01,
                "notional_fraction_of_equity": 0.05,
                "cap_utilization_ratio": 1.0 / 3.0,
                "cap_binding": true,
                "sizing_source": "asset_default"
            }
        },
        "by_provider_symbol_side": {}
    });

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect("observe-only assets do not consume execution slots");
    let risk = parsed.risk_utilization.expect("risk utilization");

    assert_eq!(risk.configured_assets, 3);
    assert_eq!(risk.configured_maximum_positions, 1);
    assert_eq!(risk.maximum_effective_margin_fraction, 0.01);
}

fn risk_asset() -> serde_json::Value {
    serde_json::json!({
        "configured_leverage": 5.0,
        "configured_margin_fraction": 0.03,
        "configured_max_notional_usd": 25.0,
        "uncapped_notional_usd": 75.0,
        "planned_notional_usd": 25.0,
        "planned_margin_usd": 5.0,
        "effective_margin_fraction": 0.01,
        "notional_fraction_of_equity": 0.05,
        "cap_utilization_ratio": 1.0 / 3.0,
        "cap_binding": true
    })
}
