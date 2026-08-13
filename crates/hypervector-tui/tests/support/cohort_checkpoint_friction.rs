#[test]
fn parses_report_only_provider_friction_parity() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-03T10:51:41+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC":"OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {
                "closed_trades": 0,
                "net_pnl_usd": 0.0,
                "friction_parity": {
                    "contract": {
                        "report_only": true,
                        "performance_gate": false,
                        "automatic_pause": false,
                        "automatic_retuning": false,
                        "execution_authority": "none"
                    },
                    "summary": {
                        "provider_symbols": 1,
                        "runtime_shape_aligned": 0,
                        "contract_mismatch": 1,
                        "unsupported_contract": 0,
                        "runtime_contract_missing": 0,
                        "provider_symbols_with_entry_fills": 1
                    },
                    "by_provider_symbol": {
                        "hypervelocity_source_follow_bidirectional_5m_v1|BTC": {
                            "parity_state": "contract_mismatch",
                            "mismatches": ["entry_liquidity","stop_bps","maximum_hold_seconds","target_policy"],
                            "modeled_contract": {
                                "entry_liquidity": "maker",
                                "entry_fee_bps": 1.5,
                                "entry_slippage_bps": 0.0,
                                "stop_bps": null,
                                "maximum_hold_seconds": 86400,
                                "target_policy": "maker_target_26.6667bps",
                                "evidence_source": "configs/source.toml"
                            },
                            "runtime_contract": {
                                "entry_liquidity": "taker",
                                "entry_order": "market_ioc",
                                "stop_bps": 80.0,
                                "maximum_hold_seconds": 28800,
                                "target_policy": "none",
                                "implementation_source": "src/live/adapter.py"
                            },
                            "observed_entry": {
                                "status": "observed",
                                "fills": 1,
                                "fee_rate_bps": {"count":1,"minimum":4.32,"median":4.32,"maximum":4.32,"mean":4.32},
                                "slippage_bps": {"count":1,"minimum":1.59,"median":1.59,"maximum":1.59,"mean":1.59},
                                "acknowledgement_latency_ms": {"count":1,"minimum":1223.0,"median":1223.0,"maximum":1223.0,"mean":1223.0},
                                "fee_mean_minus_modeled_bps": 2.82,
                                "slippage_mean_minus_modeled_bps": 1.59
                            },
                            "strategy_edge_identifiable": false,
                            "execution_effect": "report_only"
                        }
                    }
                }
            },
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid friction parity");
    let parity = parsed.friction_parity.expect("friction parity");

    assert_eq!(parity.provider_symbols, 1);
    assert_eq!(parity.contract_mismatch, 1);
    assert_eq!(parity.runtime_shape_aligned, 0);
    let row = &parity.by_provider_symbol["hypervelocity_source_follow_bidirectional_5m_v1|BTC"];
    assert_eq!(row.parity_state, "contract_mismatch");
    assert_eq!(row.modeled_entry_liquidity.as_deref(), Some("maker"));
    assert_eq!(row.runtime_entry_liquidity.as_deref(), Some("taker"));
    assert_eq!(row.entry_fills, 1);
    assert_eq!(row.observed_fee_mean_bps, Some(4.32));
    assert_eq!(row.fee_mean_minus_modeled_bps, Some(2.82));
}

#[test]
fn parses_report_only_regime_conflict_counterfactual() {
    let checkpoint = r#"{
        "schema_version":1,
        "mode":"multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc":"2026-08-03T13:00:00+00:00",
        "lifecycle":{"state":"running_consistent","cohort_heartbeat_status":"running","asset_states":{"BTC":"FLAT"}},
        "audit":{
            "coverage":{"complete":true,"technical_gaps":[]},
            "readiness":{"evaluations":2},
            "regime_conflict_journal":{
                "schema_version":1,
                "mode":"regime_conflict_counterfactual_journal",
                "state":"active",
                "contract":{"report_only":true,"counterfactual_only":true,"fills_assumed":false,"pnl_claimed":false,"execution_authority":"none","runtime_strategy_changed":false,"automatic_strategy_changes":false},
                "conflicts":3,
                "conflicts_changing_static_choice":2,
                "directionally_comparable_conflicts":1,
                "same_direction_provider_only":1,
                "horizons":{"5":{"resolved":1,"non_overlapping_resolved":1,"censored":0,"missing_data":0,"regime_preference_wins":1,"static_priority_wins":0,"ties":0,"mean_regime_advantage_bps":12.5}},
                "evidence_state":"descriptive_regime_conflict_evidence"
            },
            "execution":{"closed_trades":0,"net_pnl_usd":0.0},
            "learning":{"evidence_state":"no_closed_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid regime conflict evidence");
    let evidence = parsed.regime_conflicts.expect("regime conflict journal");
    assert_eq!(evidence.state, "active");
    assert_eq!(evidence.conflicts, 3);
    assert_eq!(evidence.changed_static_choice, 2);
    let five = evidence.five_minute.expect("5m conflict path");
    assert_eq!(five.resolved, 1);
    assert_eq!(five.regime_wins, 1);
    assert_eq!(five.static_wins, 0);
    assert_eq!(five.mean_advantage_bps, Some(12.5));
}
