#[test]
fn parses_stale_runtime_configuration_without_execution_authority() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-03T15:26:00+00:00",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": false,
            "runtime_profile_fingerprint": "runtime-profile",
            "current_profile_fingerprint": "current-profile",
            "source_path": "configs/multi_asset_bidirectional_canary.toml",
            "source_modified_at_utc": "2026-08-03T11:16:04+00:00",
            "current_provider_execution_scopes": {
                "range_onset_bidirectional_v1": ["SOL"],
                "hip3_breakout_pressure_sp500_spcx_bidirectional_v1": [
                    "xyz:SP500",
                    "xyz:SPCX"
                ]
            },
            "current_asset_sizing": {
                "BTC": {
                    "leverage": 5.0,
                    "margin_fraction": 0.03,
                    "max_notional_usd": 25.0
                },
                "HYPE": {
                    "leverage": 5.0,
                    "margin_fraction": 0.03,
                    "max_notional_usd": 75.0
                }
            },
            "current_entry_context_overrides": {
                "range_onset_bidirectional_v1|ETH": "dual_mtf_not_opposed"
            },
            "current_provider_sizing_overrides": {
                "range_onset_bidirectional_v1|SOL": {
                    "margin_fraction": 0.10,
                    "max_notional_usd": 20.0
                }
            },
            "current_provider_directional_sizing_overrides": {
                "hype_breakout_onset_bidirectional_v1|HYPE|long": {
                    "margin_fraction": 0.03,
                    "max_notional_usd": 75.0
                },
                "hype_breakout_onset_bidirectional_v1|HYPE|short": {
                    "margin_fraction": 0.03,
                    "max_notional_usd": 25.0
                }
            },
            "current_provider_exit_policies": {
                "hype_breakout_onset_bidirectional_v1": {
                    "maximum_hold_seconds": 28800,
                    "maximum_hold_policy": "fixed",
                    "hard_maximum_hold_seconds": null
                }
            },
            "restart_state": "wait_for_flat_and_no_orders",
            "blocking_assets": ["BTC"],
            "execution_authority": "none",
            "automatic_restart": false
        },
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC":"OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 8},
            "execution": {"closed_trades": 2, "net_pnl_usd": 1.25},
            "learning": {"evidence_state": "descriptive_trade_evidence"}
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid checkpoint");
    let generation = parsed.configuration_generation.expect("generation");

    assert!(!generation.matches_runtime);
    assert_eq!(generation.state, "stale_runtime_configuration");
    assert_eq!(generation.runtime_profile_fingerprint, "runtime-profile");
    assert_eq!(generation.current_profile_fingerprint, "current-profile");
    assert_eq!(
        generation.source_path,
        "configs/multi_asset_bidirectional_canary.toml"
    );
    assert_eq!(generation.restart_state, "wait_for_flat_and_no_orders");
    assert_eq!(generation.blocking_assets, vec!["BTC"]);
    assert_eq!(
        generation
            .current_provider_execution_scopes
            .as_ref()
            .unwrap()["range_onset_bidirectional_v1"],
        vec!["SOL"]
    );
    let hype = &generation.current_asset_sizing.as_ref().unwrap()["HYPE"];
    assert_eq!(hype.leverage, 5.0);
    assert_eq!(hype.margin_fraction, 0.03);
    assert_eq!(hype.max_notional_usd, 75.0);
    assert_eq!(
        generation.current_entry_context_overrides.as_ref().unwrap()["range_onset_bidirectional_v1|ETH"],
        "dual_mtf_not_opposed"
    );
    let sizing = &generation
        .current_provider_sizing_overrides
        .as_ref()
        .unwrap()["range_onset_bidirectional_v1|SOL"];
    assert_eq!(sizing.margin_fraction, 0.10);
    assert_eq!(sizing.max_notional_usd, 20.0);
    let directional = generation
        .current_provider_directional_sizing_overrides
        .as_ref()
        .unwrap();
    assert_eq!(
        directional["hype_breakout_onset_bidirectional_v1|HYPE|long"].max_notional_usd,
        75.0
    );
    assert_eq!(
        directional["hype_breakout_onset_bidirectional_v1|HYPE|short"].max_notional_usd,
        25.0
    );
    let exit = &generation.current_provider_exit_policies.as_ref().unwrap()["hype_breakout_onset_bidirectional_v1"];
    assert_eq!(exit.maximum_hold_seconds, 28_800);
    assert_eq!(exit.maximum_hold_policy, "fixed");
    assert_eq!(exit.hard_maximum_hold_seconds, None);
    assert_eq!(exit.provider_recipe_exit_policy, "ignore");
    assert_eq!(generation.execution_authority, "none");
    assert!(!generation.automatic_restart);
}

#[test]
fn rejects_malformed_pending_provider_sizing_evidence() {
    let checkpoint = serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-03T15:26:00+00:00",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": false,
            "runtime_profile_fingerprint": "runtime-profile",
            "current_profile_fingerprint": "current-profile",
            "source_path": "configs/multi_asset_bidirectional_canary.toml",
            "source_modified_at_utc": "2026-08-03T11:16:04+00:00",
            "current_provider_sizing_overrides": {
                "range_onset_bidirectional_v1|SOL": {
                    "margin_fraction": 0.0,
                    "max_notional_usd": 20.0
                }
            },
            "restart_state": "candidate_flat_no_orders",
            "blocking_assets": [],
            "execution_authority": "none",
            "automatic_restart": false
        },
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"SOL":"FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "no_closed_trade_evidence"}
        }
    });

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("zero provider margin must fail closed");

    assert!(error.contains("configuration-generation evidence is invalid"));
}

#[test]
fn rejects_an_explicit_empty_staged_provider_roster() {
    let checkpoint = serde_json::json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-03T15:26:00+00:00",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": false,
            "runtime_profile_fingerprint": "runtime-profile",
            "current_profile_fingerprint": "current-profile",
            "source_path": "configs/staged.toml",
            "source_modified_at_utc": "2026-08-03T11:16:04+00:00",
            "current_provider_execution_scopes": {},
            "restart_state": "candidate_flat_no_orders",
            "blocking_assets": [],
            "execution_authority": "none",
            "automatic_restart": false
        },
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"SOL":"FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "no_closed_trade_evidence"}
        }
    });

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("an explicit staged profile must retain provider membership");

    assert!(error.contains("configuration-generation evidence is invalid"));
}
