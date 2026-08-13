use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

#[test]
fn staged_profit_lock_contract_is_projected_without_authority() {
    let parsed = parse_cohort_checkpoint(&checkpoint().to_string()).expect("valid checkpoint");
    let generation = parsed.configuration_generation.expect("generation");
    let policy = &generation.current_provider_exit_policies.expect("policies")["provider"];
    let directional = &generation
        .current_provider_directional_exit_policies
        .expect("directional policies")["provider|HYPE|long"];

    assert_eq!(policy.profit_lock_policy, "completed_bar_trailing");
    assert_eq!(policy.profit_lock_activation_bps, Some(25.0));
    assert_eq!(policy.profit_lock_floor_bps, Some(15.0));
    assert_eq!(policy.profit_lock_giveback_bps, Some(10.0));
    assert_eq!(directional.profit_lock_policy, "completed_bar_trailing");
    assert_eq!(directional.profit_lock_activation_bps, Some(30.0));
    assert_eq!(directional.profit_lock_floor_bps, Some(12.0));
    assert_eq!(directional.profit_lock_giveback_bps, Some(7.0));
    assert_eq!(generation.execution_authority, "none");
    assert!(!generation.automatic_restart);
}

#[test]
fn partial_staged_profit_lock_contract_fails_closed() {
    let mut value = checkpoint();
    value["configuration_generation"]["current_provider_exit_policies"]["provider"]["profit_lock_giveback_bps"] =
        Value::Null;

    let error = parse_cohort_checkpoint(&value.to_string()).expect_err("must reject partial lock");

    assert!(error.contains("configuration-generation evidence is invalid"));
}

fn checkpoint() -> Value {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-13T06:00:00+00:00",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": false,
            "runtime_profile_fingerprint": "runtime-profile",
            "current_profile_fingerprint": "next-profile",
            "source_path": "configs/next.toml",
            "source_modified_at_utc": "2026-08-13T05:59:00+00:00",
            "current_provider_execution_scopes": {"provider": ["HYPE"]},
            "current_provider_execution_directions": {
                "provider|HYPE": ["long", "short"]
            },
            "current_provider_exit_policies": {
                "provider": {
                    "maximum_hold_seconds": 28800,
                    "maximum_hold_policy": "fixed",
                    "hard_maximum_hold_seconds": null,
                    "provider_recipe_exit_policy": "ignore",
                    "profit_lock_policy": "completed_bar_trailing",
                    "profit_lock_activation_bps": 25.0,
                    "profit_lock_floor_bps": 15.0,
                    "profit_lock_giveback_bps": 10.0
                }
            },
            "current_provider_directional_exit_policies": {
                "provider|HYPE|long": {
                    "maximum_hold_seconds": 28800,
                    "maximum_hold_policy": "fixed",
                    "hard_maximum_hold_seconds": null,
                    "provider_recipe_exit_policy": "ignore",
                    "profit_lock_policy": "completed_bar_trailing",
                    "profit_lock_activation_bps": 30.0,
                    "profit_lock_floor_bps": 12.0,
                    "profit_lock_giveback_bps": 7.0
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
            "asset_states": {"BTC": "FLAT"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 0},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "none"}
        }
    })
}
