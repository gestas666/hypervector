use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;

#[test]
fn parses_provider_structural_execution_contract() {
    let checkpoint = r#"{
        "schema_version":1,
        "mode":"multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc":"2026-08-03T18:18:34+00:00",
        "lifecycle":{"state":"running_consistent","cohort_heartbeat_status":"running","asset_states":{"BTC":"OPEN"}},
        "audit":{
            "coverage":{"complete":true,"technical_gaps":[]},
            "readiness":{"evaluations":1},
            "execution":{
                "closed_trades":0,
                "net_pnl_usd":0.0,
                "friction_parity":{
                    "contract":{"report_only":true,"performance_gate":false,"automatic_pause":false,"automatic_retuning":false,"execution_authority":"none"},
                    "summary":{"provider_symbols":1,"runtime_shape_aligned":1,"contract_mismatch":0,"unsupported_contract":0,"runtime_contract_missing":0,"provider_symbols_with_entry_fills":0},
                    "by_provider_symbol":{
                        "hulk_expansion_bidirectional_tuned_v2|BTC":{
                            "parity_state":"runtime_shape_aligned",
                            "mismatches":[],
                            "modeled_contract":{
                                "entry_liquidity":"taker","entry_fee_bps":4.5,"entry_slippage_bps":2.0,
                                "stop_policy":"structural_clamped_bps","stop_bps":null,"minimum_stop_bps":20.0,"maximum_stop_bps":75.0,
                                "maximum_hold_seconds":86400,"maximum_hold_policy":"fixed","hard_maximum_hold_seconds":null,
                                "target_policy":"reward_risk","target_liquidity":"maker","target_bps":null,"target_r_multiple":3.0,
                                "evidence_source":"docs/reviews/hulk.md"
                            },
                            "runtime_contract":{
                                "entry_liquidity":"taker","entry_order":"market_ioc",
                                "stop_policy":"structural_clamped_bps","stop_bps":null,"minimum_stop_bps":20.0,"maximum_stop_bps":75.0,
                                "maximum_hold_seconds":86400,"maximum_hold_policy":"fixed","hard_maximum_hold_seconds":null,
                                "provider_recipe_exit_policy":"honor",
                                "target_policy":"reward_risk","target_liquidity":"maker","target_bps":null,"target_r_multiple":3.0,
                                "safety_stop_overlay":false,"implementation_source":"src/live/adapter.py"
                            },
                            "runtime_contract_source":"provider_execution",
                            "observed_entry":{
                                "status":"not_observed","fills":0,
                                "fee_rate_bps":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "slippage_bps":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "acknowledgement_latency_ms":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "fee_mean_minus_modeled_bps":null,"slippage_mean_minus_modeled_bps":null
                            },
                            "strategy_edge_identifiable":false,
                            "execution_effect":"report_only"
                        }
                    }
                }
            },
            "learning":{"evidence_state":"no_closed_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("current provider plan parses");
    let parity = parsed.friction_parity.expect("friction parity");
    let row = &parity.by_provider_symbol["hulk_expansion_bidirectional_tuned_v2|BTC"];

    assert_eq!(
        row.runtime_contract_source.as_deref(),
        Some("provider_execution")
    );
    assert_eq!(
        row.modeled_stop_description.as_deref(),
        Some("STRUCT 20.00-75.00bps")
    );
    assert_eq!(
        row.runtime_stop_description.as_deref(),
        Some("STRUCT 20.00-75.00bps")
    );
    assert_eq!(
        row.runtime_hold_description.as_deref(),
        Some("FIXED 86400s")
    );
    assert_eq!(
        row.runtime_target_description.as_deref(),
        Some("MAKER 3.00R")
    );
    assert_eq!(row.runtime_provider_recipe_exit_policy, "honor");
}

#[test]
fn parses_unbounded_signal_exit_without_inventing_a_hold_limit() {
    let checkpoint = r#"{
        "schema_version":1,
        "mode":"multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc":"2026-08-07T23:00:00+00:00",
        "lifecycle":{"state":"running_consistent","cohort_heartbeat_status":"running","asset_states":{"xyz:SPCX":"FLAT"}},
        "audit":{
            "coverage":{"complete":true,"technical_gaps":[]},
            "readiness":{"evaluations":1},
            "execution":{
                "closed_trades":0,
                "net_pnl_usd":0.0,
                "friction_parity":{
                    "contract":{"report_only":true,"performance_gate":false,"automatic_pause":false,"automatic_retuning":false,"execution_authority":"none"},
                    "summary":{"provider_symbols":1,"runtime_shape_aligned":0,"contract_mismatch":1,"unsupported_contract":0,"runtime_contract_missing":0,"provider_symbols_with_entry_fills":0},
                    "by_provider_symbol":{
                        "hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX":{
                            "parity_state":"contract_mismatch",
                            "mismatches":["stop_policy","maximum_hold_policy"],
                            "modeled_contract":{
                                "entry_liquidity":"taker","entry_fee_bps":0.864,"entry_slippage_bps":2.7516,
                                "stop_policy":"margin_barrier","stop_bps":null,"minimum_stop_bps":null,"maximum_stop_bps":null,
                                "maximum_hold_seconds":null,"maximum_hold_policy":"signal_exit_unbounded","hard_maximum_hold_seconds":null,
                                "target_policy":"none","target_liquidity":null,"target_bps":null,"target_r_multiple":null,
                                "evidence_source":"data/logs/research/hip3_swing_ha_transfer_sp500_spcx_v2.json"
                            },
                            "runtime_contract":{
                                "entry_liquidity":"taker","entry_order":"market_ioc",
                                "stop_policy":"fixed_bps","stop_bps":80.0,"minimum_stop_bps":null,"maximum_stop_bps":null,
                                "maximum_hold_seconds":86400,"maximum_hold_policy":"fixed","hard_maximum_hold_seconds":null,
                                "target_policy":"none","target_liquidity":null,"target_bps":null,"target_r_multiple":null,
                                "safety_stop_overlay":false,"implementation_source":"src/live/adapter.py"
                            },
                            "runtime_contract_source":"provider_execution",
                            "observed_entry":{
                                "status":"not_observed","fills":0,
                                "fee_rate_bps":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "slippage_bps":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "acknowledgement_latency_ms":{"count":0,"minimum":null,"median":null,"maximum":null,"mean":null},
                                "fee_mean_minus_modeled_bps":null,"slippage_mean_minus_modeled_bps":null
                            },
                            "strategy_edge_identifiable":false,
                            "execution_effect":"report_only"
                        }
                    }
                }
            },
            "learning":{"evidence_state":"no_closed_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("unbounded model parses");
    let parity = parsed.friction_parity.expect("friction parity");
    let row = &parity.by_provider_symbol["hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX"];

    assert_eq!(row.modeled_maximum_hold_seconds, None);
    assert_eq!(
        row.modeled_hold_description.as_deref(),
        Some("SIGNAL EXIT / NO TIME CAP")
    );
    assert_eq!(
        row.runtime_hold_description.as_deref(),
        Some("FIXED 86400s")
    );
}
