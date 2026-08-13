use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

#[test]
fn checkpoint_projects_exact_side_specialist_directions() {
    let parsed = parse_cohort_checkpoint(&checkpoint().to_string()).expect("valid checkpoint");
    let generation = parsed.configuration_generation.expect("generation");
    let directions = generation
        .current_provider_execution_directions
        .expect("directions");

    assert_eq!(
        directions["hulk_expansion_short_robust_v3|BTC"],
        vec!["short"]
    );
    assert_eq!(
        directions["liquidity_sweep_long_1h_stop60_v1|BTC"],
        vec!["long"]
    );
}

#[test]
fn checkpoint_rejects_direction_identity_outside_staged_scopes() {
    let mut value = checkpoint();
    value["configuration_generation"]["current_provider_execution_directions"]["unknown_provider|BTC"] =
        json!(["long"]);

    let error = parse_cohort_checkpoint(&value.to_string()).expect_err("must reject mismatch");

    assert!(error.contains("configuration-generation evidence is invalid"));
}

fn checkpoint() -> Value {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-11T22:30:00+00:00",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": false,
            "runtime_profile_fingerprint": "runtime-profile",
            "current_profile_fingerprint": "v43-profile",
            "source_path": "configs/v43.toml",
            "source_modified_at_utc": "2026-08-11T22:00:00+00:00",
            "current_provider_execution_scopes": {
                "hulk_expansion_short_robust_v3": ["BTC"],
                "liquidity_sweep_long_1h_stop60_v1": ["BTC"]
            },
            "current_provider_execution_directions": {
                "hulk_expansion_short_robust_v3|BTC": ["short"],
                "liquidity_sweep_long_1h_stop60_v1|BTC": ["long"]
            },
            "restart_state": "wait_for_flat_and_no_orders",
            "blocking_assets": ["ETH"],
            "execution_authority": "none",
            "automatic_restart": false
        },
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"ETH": "OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 0},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0},
            "learning": {"evidence_state": "none"}
        }
    })
}
