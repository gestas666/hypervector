#[test]
fn parses_exact_eth_candidate_lifecycle_without_execution_authority() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["eligible_policy_forward"] = serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_eligible_policy_forward_report",
        "state": "awaiting_exact_policy_resolution",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "live_strategy_changed": false,
            "automatic_promotion": false,
            "portfolio_pnl_claimed": false,
            "source_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v12",
            "symbol": "ETH",
            "source_run_id": "live-run-eth",
            "cutoff_time_ms": 1_785_982_800_000_u64,
            "stop_bps": 60.0,
            "maximum_hold_minutes": 720,
            "modeled_round_trip_friction_bps": 13.0,
            "funding_included": false,
            "notional_usd": 25.0,
            "one_position_per_coin": true
        },
        "summary": {
            "eligible_signals": 1,
            "selected_non_overlapping": 1,
            "overlapping_excluded": 0,
            "resolved": 0,
            "pending": 1,
            "missing_data": 0,
            "wins": 0,
            "losses": 0,
            "total_estimated_net_before_funding_bps": 0.0,
            "profit_factor_before_funding": null
        },
        "latest_attempts": [{
            "source_run_id": "live-run-eth",
            "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v12",
            "symbol": "ETH",
            "side": "long",
            "decision_time_ms": 1_785_982_800_000_u64,
            "available_time_ms": 1_785_982_817_179_u64,
            "reference_price": 1896.5,
            "status": "exit_pending",
            "entry_time_ms": 1_785_982_817_179_u64,
            "entry_price": 1896.5,
            "deadline_time_ms": 1_786_026_000_000_u64,
            "observed_candles": 53,
            "remaining_ms": 40_020_000,
            "current_gross_return_bps": 3.16,
            "current_estimated_net_before_funding_bps": -9.84,
            "funding_bps": null,
            "mfe_bps": 21.62,
            "mae_bps": -14.76
        }],
        "latest_executions": [],
        "portfolio_journal": {
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "source_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
                "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v12",
                "symbol": "ETH",
                "position_policy": "flat_entry_only",
                "maximum_positions": 4,
                "portfolio_pnl_claimed": false,
                "simulated_outcomes_are_non_additive": true
            },
            "summary": {
                "attempts": 1,
                "deployable": 1,
                "resolved": 0,
                "pending": 1
            },
            "latest_attempts": [{"portfolio_classification": "deployable_flat_entry"}]
        },
        "limitations": ["report only"]
    });

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid checkpoint");

    let evidence = parsed
        .eligible_policy_forward
        .expect("eligible policy forward evidence");
    assert_eq!(evidence.symbol, "ETH");
    assert_eq!(evidence.eligible_signals, 1);
    assert_eq!(evidence.pending, 1);
    assert_eq!(evidence.deployable, 1);
    let attempt = evidence.latest_attempt.expect("pending attempt");
    assert_eq!(attempt.side, "long");
    assert_eq!(
        attempt.current_estimated_net_before_funding_bps,
        Some(-9.84)
    );
    assert_eq!(attempt.remaining_ms, Some(40_020_000));

    checkpoint["audit"]["eligible_policy_forward"]["contract"]["funding_included"] = true.into();
    checkpoint["audit"]["eligible_policy_forward"]["contract"]["funding_source"] =
        "hl_funding_history".into();
    checkpoint["audit"]["eligible_policy_forward"]["latest_attempts"][0]["current_estimated_net_after_funding_bps"] =
        (-10.34).into();
    checkpoint["audit"]["eligible_policy_forward"]["latest_attempts"][0]["funding_bps"] =
        (-0.50).into();

    let funded = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect("officially funded candidate checkpoint");
    let funded_evidence = funded
        .eligible_policy_forward
        .expect("funded eligible-policy evidence");
    assert!(funded_evidence.funding_included);
    assert_eq!(funded_evidence.total_estimated_net_after_funding_bps, None);
    let funded_attempt = funded_evidence.latest_attempt.expect("funded attempt");
    assert_eq!(funded_attempt.funding_bps, Some(-0.50));
    assert_eq!(
        funded_attempt.current_estimated_net_after_funding_bps,
        Some(-10.34)
    );
}

#[test]
fn rejects_exact_eth_candidate_lifecycle_with_execution_authority() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["eligible_policy_forward"] = serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_eligible_policy_forward_report",
        "state": "awaiting_fresh_eligible_signal",
        "contract": {
            "report_only": true,
            "execution_authority": "venue",
            "live_strategy_changed": false,
            "automatic_promotion": false,
            "portfolio_pnl_claimed": false,
            "source_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
            "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v12",
            "symbol": "ETH",
            "source_run_id": "source-run",
            "cutoff_time_ms": 1_000,
            "stop_bps": 60.0,
            "maximum_hold_minutes": 720,
            "modeled_round_trip_friction_bps": 13.0,
            "funding_included": false,
            "notional_usd": 25.0,
            "one_position_per_coin": true
        },
        "summary": {
            "eligible_signals": 0,
            "selected_non_overlapping": 0,
            "overlapping_excluded": 0,
            "resolved": 0,
            "pending": 0,
            "missing_data": 0,
            "wins": 0,
            "losses": 0,
            "total_estimated_net_before_funding_bps": 0.0,
            "profit_factor_before_funding": null
        },
        "latest_attempts": [],
        "portfolio_journal": {
            "contract": {
                "report_only": true,
                "execution_authority": "none",
                "source_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
                "candidate_strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1_v12",
                "symbol": "ETH",
                "position_policy": "flat_entry_only",
                "maximum_positions": 4,
                "portfolio_pnl_claimed": false,
                "simulated_outcomes_are_non_additive": true
            },
            "summary": {"attempts": 0, "deployable": 0, "resolved": 0, "pending": 0},
            "latest_attempts": []
        },
        "limitations": ["report only"]
    });

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("observer evidence with venue authority must fail closed");
    assert!(error.contains("eligible-policy forward evidence is inconsistent"));
}

#[test]
fn rejects_risk_evidence_that_claims_gate_authority() {
    let mut checkpoint = serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-02T04:00:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC": "FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "no_closed_trade_evidence"},
            "risk_utilization": {
                "schema_version": 1,
                "mode": "cohort_runtime_risk_utilization_v1",
                "contract": {
                    "report_only": true,
                    "execution_authority": "none",
                    "performance_gate": true,
                    "balance_gate": false,
                    "automatic_sizing_change": false
                },
                "account_value_usd": 500.0,
                "summary": {
                    "configured_assets": 1,
                    "cap_bound_assets": 1,
                    "configured_maximum_positions": 1,
                    "maximum_simultaneous_effective_margin_fraction": 0.01
                },
                "by_asset": {
                    "BTC": {
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
                    }
                }
            }
        }
    });

    let error = parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject gate");

    assert!(error.contains("risk-utilization evidence is invalid"));

    checkpoint["audit"]["risk_utilization"]["contract"]["performance_gate"] = false.into();
    checkpoint["audit"]["risk_utilization"]["contract"]["balance_gate"] = true.into();
    let error =
        parse_cohort_checkpoint(&checkpoint.to_string()).expect_err("must reject balance gate");

    assert!(error.contains("risk-utilization evidence is invalid"));
}
