use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

#[test]
fn projects_report_only_hulk_entry_quality_annotation() {
    let parsed = parse_cohort_checkpoint(&checkpoint().to_string()).expect("valid annotation");
    let evidence = parsed
        .hulk_entry_quality
        .expect("Hulk entry-quality evidence");

    assert_eq!(evidence.closed_trades, 2);
    assert_eq!(evidence.attributable_closed_trades, 2);
    assert_eq!(evidence.closed_by_quality["neither"].trades, 2);
    assert_eq!(evidence.closed_by_quality["neither"].net_pnl_usd, 0.343_915);
    assert_eq!(evidence.open_observations.len(), 1);
    assert_eq!(evidence.open_observations[0].symbol, "SOL");
    assert_eq!(evidence.open_observations[0].quality, "neither");
}

#[test]
fn rejects_hulk_annotation_that_grants_execution_authority() {
    let mut document = checkpoint();
    document["audit"]["hulk_entry_quality_challenger"]["contract"]["execution_authority"] =
        json!("hyperliquid_mainnet");

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("execution-capable annotation must fail closed");

    assert!(error.contains("Hulk entry-quality contract"), "{error}");
}

#[test]
fn rejects_hulk_annotation_with_inconsistent_category_counts() {
    let mut document = checkpoint();
    document["audit"]["hulk_entry_quality_challenger"]["closed_by_quality"]["neither"]["trades"] =
        json!(3);

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("inconsistent attribution must fail closed");

    assert!(error.contains("Hulk entry-quality"), "{error}");
}

fn checkpoint() -> Value {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-08T00:30:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"SOL": "OPEN", "xyz:GOLD": "OPEN"}
        },
        "audit": {
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 10},
            "execution": {"closed_trades": 1, "open_lifecycles": 2, "net_pnl_usd": -0.65},
            "learning": {"evidence_state": "descriptive_trade_evidence"},
            "hulk_entry_quality_challenger": hulk_annotation()
        }
    })
}

fn hulk_annotation() -> Value {
    let zero = summary(0, 0, 0, 0, 0.0, None, None);
    let neither = summary(2, 2, 0, 0, 0.343_915, Some(3.470_776_713_864_958), None);
    json!({
        "schema_version": 1,
        "mode": "cohort_hulk_entry_quality_mechanism_v1",
        "scope": "all_live_history_mixed_profiles",
        "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
        "current_stage": "annotation_only",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "execution_gate": false,
            "position_sizing_authority": false,
            "runtime_strategy_changed": false,
            "automatic_strategy_changes": false
        },
        "feature_contract": {
            "source": "entry_decision_readiness_metrics",
            "money_flow_alignment": "direction_sign_equals_position_side",
            "symmetric_long_short": true,
            "volume_support_minimum_ratio": 1.0,
            "volume_threshold_origin": "untuned_relative_volume_baseline"
        },
        "closed_trades": 2,
        "attributable_closed_trades": 2,
        "closed_by_quality": {
            "flow_and_volume": zero,
            "one_of_two": summary(0, 0, 0, 0, 0.0, None, None),
            "neither": neither,
            "unavailable": summary(0, 0, 0, 0, 0.0, None, None)
        },
        "by_side": {
            "long": {
                "closed_trades": 2,
                "closed_by_quality": {
                    "flow_and_volume": summary(0, 0, 0, 0, 0.0, None, None),
                    "one_of_two": summary(0, 0, 0, 0, 0.0, None, None),
                    "neither": summary(2, 2, 0, 0, 0.343_915, Some(3.470_776_713_864_958), None),
                    "unavailable": summary(0, 0, 0, 0, 0.0, None, None)
                }
            },
            "short": {
                "closed_trades": 0,
                "closed_by_quality": {
                    "flow_and_volume": summary(0, 0, 0, 0, 0.0, None, None),
                    "one_of_two": summary(0, 0, 0, 0, 0.0, None, None),
                    "neither": summary(0, 0, 0, 0, 0.0, None, None),
                    "unavailable": summary(0, 0, 0, 0, 0.0, None, None)
                }
            }
        },
        "open_trades": 1,
        "open_observations": [{
            "symbol": "SOL",
            "side": "long",
            "quality": "neither",
            "status": "unresolved",
            "flow_direction": -1,
            "volume_ratio": 0.090_442_280_452_784_21,
            "marked_net_pnl_usd": -0.003_39
        }],
        "predeclared_variants": {
            "annotation": {"entry": "unchanged", "execution": "active_stage"},
            "control": {"entry": "unchanged", "size_multiplier": 1.0},
            "hard_gate": {"execution": "disabled", "requires": "flow_and_volume"},
            "scaled": {
                "execution": "disabled",
                "flow_and_volume": 1.0,
                "one_of_two": 0.5,
                "neither": 0.25
            }
        },
        "limitations": ["small live categories do not establish a durable sizing or gating edge"]
    })
}

fn summary(
    trades: usize,
    wins: usize,
    losses: usize,
    breakeven: usize,
    net_pnl_usd: f64,
    mean_net_return_on_margin_pct: Option<f64>,
    normalized_profit_factor: Option<f64>,
) -> Value {
    json!({
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "net_pnl_usd": net_pnl_usd,
        "mean_net_return_on_margin_pct": mean_net_return_on_margin_pct,
        "normalized_profit_factor": normalized_profit_factor
    })
}
