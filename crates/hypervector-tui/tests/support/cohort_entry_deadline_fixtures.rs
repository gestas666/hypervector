use serde_json::{Value, json};

/// Synthetic 2030 checkpoint carrying a recorded SDK check.
pub fn fixture() -> Value {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2030-01-01T00:01:00+00:00",
        "lifecycle": {"state":"running_consistent", "cohort_heartbeat_status":"running", "asset_states":{"BTC":"FLAT"}},
        "audit": {
            "coverage":{"complete":true,"technical_gaps":[]},
            "readiness":{"evaluations":1},
            "execution":{"closed_trades":0,"net_pnl_usd":0.0},
            "learning":{"evidence_state":"synthetic_fixture"},
            "routing":{"actions":1,"strategy_intents":1,"entry_age_diagnostics":evidence()}
        }
    })
}

fn evidence() -> Value {
    json!({
        "contract":{"report_only":true,"execution_authority":"none","automatic_live_change":false,"automatic_pause":false,"entry_enforcement_changed":false},
        "enter_actions":1,"submitted_entries":1,"sdk_dispatch_checks":1,"stale_entries_withheld":0,
        "by_provider_symbol":{"provider_v1|BTC":{
            "maximum_entry_delay_ms":30000,"enter_actions":1,"submitted_entries":1,
            "sdk_dispatch_checks":1,"sdk_dispatches_over_limit":0,
            "adapter_dispatch_checks":0,"admission_or_legacy_checks":0,
            "stale_entries_withheld":0,"submitted_entries_over_limit":0,
            "maximum_submission_age_ms":29000,"minimum_submission_headroom_ms":1000,
            "maximum_withheld_submission_age_ms":null,"status":"sdk_dispatch_contract_observed"
        }}
    })
}
