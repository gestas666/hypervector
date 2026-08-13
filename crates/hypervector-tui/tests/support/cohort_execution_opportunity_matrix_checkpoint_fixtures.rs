fn checkpoint(contract: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-04T17:00:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"HYPE": "FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "execution_opportunity_matrix": {
                "schema_version": 1,
                "mode": "cohort_execution_opportunity_matrix",
                "contract": contract,
                "hypotheses": 1,
                "comparisons": 3,
                "scope": {
                    "observed_hypotheses": 3,
                    "executable_hypotheses": 1,
                    "excluded_non_executable_hypotheses": [
                        {
                            "strategy_id": "range_onset_bidirectional_v1",
                            "symbol": "HYPE",
                            "blocker": "awaiting_hourly_sma_cross"
                        },
                        {
                            "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
                            "symbol": "HYPE",
                            "blocker": "squeeze_not_armed"
                        }
                    ]
                },
                "results": [
                    comparison("aligned", 8),
                    comparison("opposed", 7),
                    comparison("all", 9)
                ],
                "forward_challenger": forward_challenger(),
                "limitations": ["comparisons are not additive"]
            },
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    })
}

fn forward_challenger() -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_forward_one_blocker_challenger",
        "state": "awaiting_executable_resolution",
        "generated_at_utc": "2026-08-04T17:22:26+00:00",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "live_strategy_changed": false,
            "automatic_promotion": false,
            "portfolio_pnl_claimed": false,
            "direction_scope": ["long", "short"],
            "cutoff_time_ms": 1_785_862_320_000_u64,
            "cutoff_utc": "2026-08-04T16:52:00+00:00",
            "execution": {
                "strategy_id": "hype_breakout_onset_bidirectional_v1",
                "symbol": "HYPE",
                "blocker": "5m_not_breakout",
                "horizon_minutes": 60,
                "minimum_entry_spacing_minutes": 75,
                "notional_usd": 25.0,
                "taker_fee_rate": 0.000432,
                "stop_proxy_bps": 80.0,
                "opi_cohort": "all",
                "minimum_available_time_ms": 1_785_862_320_000_u64,
                "execution_authority": "none"
            }
        },
        "coverage": {
            "exact_candidates": 31,
            "selected_non_overlapping": 1,
            "resolved_executions": 0
        },
        "summary": {
            "resolved": 0,
            "wins": 0,
            "losses": 0,
            "total_net_return_bps": 0.0,
            "mean_net_return_bps": null,
            "profit_factor": null,
            "largest_abs_contribution_fraction": null,
            "stop_proxy_crosses": 0,
            "long_resolved": 0,
            "short_resolved": 0
        },
        "latest_executions": [],
        "portfolio_journal": portfolio_journal(false),
        "falsifiers": ["PF <= 1"],
        "limitations": ["report only"]
    })
}

fn resolved_forward_challenger() -> serde_json::Value {
    let mut value = forward_challenger();
    value["state"] = "descriptive_resolved_forward_evidence".into();
    value["coverage"]["exact_candidates"] = 61.into();
    value["coverage"]["selected_non_overlapping"] = 2.into();
    value["coverage"]["resolved_executions"] = 1.into();
    value["summary"] = serde_json::json!({
        "resolved": 1,
        "wins": 1,
        "losses": 0,
        "total_net_return_bps": 19.966,
        "mean_net_return_bps": 19.966,
        "profit_factor": null,
        "largest_abs_contribution_fraction": 1.0,
        "stop_proxy_crosses": 0,
        "long_resolved": 1,
        "short_resolved": 0
    });
    value["latest_executions"] = serde_json::json!([{
        "source_run_id": "bidirectional-live-a",
        "side": "long",
        "available_time_ms": 1_785_862_327_798_u64,
        "entry_time_ms": 1_785_862_339_333_u64,
        "exit_time_ms": 1_785_865_945_137_u64,
        "entry_price": 55.317,
        "exit_price": 55.476,
        "exit_reason": "fixed_horizon",
        "gross_return_bps": 28.743,
        "fee_bps": 8.652,
        "funding_bps": -0.125,
        "net_return_bps": 19.966,
        "mfe_bps": 75.384,
        "mae_bps": -23.682,
        "crossed_stop_proxy": false
    }]);
    value["entry_context_summary"] = serde_json::json!({
        "mode": "untuned_five_minute_regime_context",
        "execution_authority": "none",
        "performance_gate": false,
        "coverage": {
            "resolved": 1,
            "state_5m_observed": 1,
            "state_5m_missing": 0
        },
        "by_directional_stance": {
            "aligned": regime_bucket(0, 0, 0, 0.0),
            "opposed": regime_bucket(0, 0, 0, 0.0),
            "neutral": regime_bucket(1, 1, 0, 19.966),
            "unavailable": regime_bucket(0, 0, 0, 0.0)
        },
        "by_state_5m": {
            "RANGE": regime_bucket(1, 1, 0, 19.966)
        }
    });
    value["context_15m_summary"] = serde_json::json!({
        "mode": "untuned_fifteen_minute_regime_context",
        "execution_authority": "none",
        "performance_gate": false,
        "coverage": {
            "resolved": 1,
            "context_15m_observed": 1,
            "context_15m_missing": 0
        },
        "by_directional_stance": {
            "aligned": regime_bucket(1, 1, 0, 19.966),
            "opposed": regime_bucket(0, 0, 0, 0.0),
            "neutral": regime_bucket(0, 0, 0, 0.0),
            "unavailable": regime_bucket(0, 0, 0, 0.0)
        },
        "by_state_15m": {
            "TREND_UP": regime_bucket(1, 1, 0, 19.966)
        }
    });
    value["portfolio_journal"] = portfolio_journal(true);
    value
}

fn regime_bucket(
    resolved: usize,
    wins: usize,
    losses: usize,
    total_net_return_bps: f64,
) -> serde_json::Value {
    serde_json::json!({
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "total_net_return_bps": total_net_return_bps,
        "mean_net_return_bps": (resolved > 0).then_some(total_net_return_bps / resolved as f64),
        "profit_factor": null,
        "largest_abs_contribution_fraction": (resolved > 0).then_some(1.0),
        "stop_proxy_crosses": 0,
        "long_resolved": resolved,
        "short_resolved": 0
    })
}

fn target20_resolved_forward_challenger() -> serde_json::Value {
    let mut value = resolved_forward_challenger();
    value["contract"]["execution"]["target_proxy_bps"] = 20.0.into();
    value["payoff_geometry"] = serde_json::json!({
        "scope": "binary_target_stop_benchmark_before_funding",
        "execution_authority": "none",
        "performance_gate": false,
        "target_proxy_bps": 20.0,
        "stop_proxy_bps": 80.0,
        "estimated_round_trip_fee_bps": 8.64,
        "estimated_target_net_bps": 11.36,
        "estimated_stop_net_bps": -88.64,
        "break_even_target_rate_pct": 88.64,
        "fixed_horizon_changes_realized_distribution": true
    });
    value["latest_executions"][0]["exit_reason"] = "target_proxy".into();
    value["portfolio_journal"]["contract"]["candidate_strategy_id"] =
        "hype_breakout_relaxed_target20_60m_bidirectional_v3".into();
    value
}

fn portfolio_journal(resolved: bool) -> serde_json::Value {
    let first = portfolio_attempt(true);
    let attempts = if resolved {
        vec![first, portfolio_attempt(false)]
    } else {
        vec![portfolio_attempt(false)]
    };
    serde_json::json!({
        "schema_version": 1,
        "mode": "candidate_portfolio_compatibility_journal",
        "state": "resolved_observations",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "source_strategy_id": "hype_breakout_onset_bidirectional_v1",
            "candidate_strategy_id": "hype_breakout_relaxed_60m_bidirectional_v2",
            "symbol": "HYPE",
            "position_policy": "flat_entry_only",
            "maximum_positions": 4,
            "portfolio_pnl_claimed": false,
            "simulated_outcomes_are_non_additive": true
        },
        "summary": {
            "attempts": attempts.len(),
            "deployable": attempts.len(),
            "existing_symbol_position": 0,
            "portfolio_capacity": 0,
            "same_cycle_symbol_action": 0,
            "portfolio_state_unavailable": 0,
            "resolved": usize::from(resolved),
            "pending": attempts.len() - usize::from(resolved)
        },
        "latest_attempts": attempts,
        "limitations": ["report only"]
    })
}

fn portfolio_attempt(resolved: bool) -> serde_json::Value {
    serde_json::json!({
        "source_run_id": "bidirectional-live-a",
        "side": "long",
        "decision_time_ms": 1_785_862_320_000_u64,
        "available_time_ms": 1_785_862_327_798_u64,
        "routing_sequence": 100,
        "snapshot_sequence": 99,
        "portfolio_classification": "deployable_flat_entry",
        "open_position_count": 1,
        "available_position_slots": 3,
        "symbol_state": "FLAT",
        "symbol_position_side": null,
        "symbol_position_strategy_id": null,
        "same_cycle_symbol_actions": [],
        "same_cycle_symbol_withheld": [],
        "outcome_status": if resolved { "resolved" } else { "pending_or_unresolved" },
        "net_return_bps": if resolved { Some(19.966) } else { None },
        "simulated_net_pnl_usd": if resolved { Some(0.0499) } else { None },
        "current_estimated_net_return_bps": if resolved { None } else { Some(31.0) },
        "mfe_bps": if resolved { None } else { Some(45.0) },
        "mae_bps": if resolved { None } else { Some(-2.0) },
        "remaining_ms": if resolved { None } else { Some(2_700_000_u64) },
        "current_exit_top_level_capacity": if resolved { None } else { Some(true) }
        ,"entry_features": {
            "primary_regime": "TREND_DOWN",
            "state_1m": "RANGE",
            "state_5m": "TREND_DOWN",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "breakout_volume_ratio": 0.14,
            "current_bbwp_percentile": 4.6,
            "regime_strength": 0.23
        }
    })
}

fn matrix_contract() -> serde_json::Value {
    serde_json::json!({
        "report_only": true,
        "execution_authority": "none",
        "live_strategy_changed": false,
        "portfolio_pnl_claimed": false,
        "thresholds_fitted": false,
        "horizon_minutes": 60,
        "opi_cohorts": ["aligned", "opposed", "all"],
        "comparisons_are_not_additive": true
    })
}

fn comparison(cohort: &str, resolved: usize) -> serde_json::Value {
    serde_json::json!({
        "strategy_id": "hype_breakout_onset_bidirectional_v1",
        "symbol": "HYPE",
        "blocker": "5m_not_breakout",
        "opi_cohort": cohort,
        "resolved": resolved,
        "wins": resolved - 3,
        "losses": 3,
        "total_net_return_bps": 149.98,
        "mean_net_return_bps": 149.98 / resolved as f64,
        "first_entry_time_ms": 1,
        "last_exit_time_ms": 2,
        "profit_factor": 1.93,
        "largest_abs_contribution_fraction": 0.232,
        "stop_proxy_crosses": 1,
        "long": side(resolved, resolved - 3, 3, 149.98),
        "short": side(0, 0, 0, 0.0),
        "coverage": {"resolved_executions": resolved}
    })
}

fn side(resolved: usize, wins: usize, losses: usize, total: f64) -> serde_json::Value {
    serde_json::json!({
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "total_net_return_bps": total,
        "mean_net_return_bps": if resolved == 0 { None } else { Some(total / resolved as f64) },
        "profit_factor": if resolved == 0 { None } else { Some(1.93) },
        "stop_proxy_crosses": if resolved == 0 { 0 } else { 1 }
    })
}
