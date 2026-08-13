use hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint;
use serde_json::{Value, json};

#[test]
fn projects_report_only_strategy_scorecard_into_provider_journal() {
    let parsed = parse_cohort_checkpoint(&checkpoint().to_string()).expect("valid scorecard");
    let row = parsed
        .observer_provider_journal
        .first()
        .expect("provider journal row");

    assert_eq!(row.research_state.as_deref(), Some("forward_observer"));
    assert_eq!(row.confidence.as_deref(), Some("low"));
    assert_eq!(
        row.historical_cadence.as_deref(),
        Some("not established; measuring each onset")
    );
    assert_eq!(
        row.forward_assessment.as_deref(),
        Some("descriptive_adverse_paths")
    );
    assert_eq!(
        row.evidence_source.as_deref(),
        Some("docs/reviews/provider.md")
    );
    let long = &row.directional_research["long"];
    let short = &row.directional_research["short"];
    assert_eq!(long.research_state, "historical_candidate");
    assert_eq!(long.confidence, "medium");
    assert_eq!(short.research_state, "contradictory");
}

#[test]
fn projects_live_strategy_scorecard_into_the_same_provider_journal() {
    let parsed = parse_cohort_checkpoint(&live_checkpoint().to_string())
        .expect("valid live scorecard checkpoint");
    let row = parsed
        .observer_provider_journal
        .first()
        .expect("live provider journal row");

    assert_eq!(parsed.analysis_mode.as_deref(), Some("live_execution"));
    assert_eq!(parsed.forward_evaluations, Some(9));
    assert_eq!(parsed.eligible_signals, Some(1));
    assert_eq!(row.strategy_id, "hype");
    assert_eq!(row.symbol, "HYPE");
    assert_eq!(
        row.execution_performance_scope.as_deref(),
        Some("provider_execution_contract_history")
    );
    let performance = row
        .execution_performance
        .as_ref()
        .expect("resolved provider performance");
    assert_eq!(performance.closed_trades, 1);
    assert_eq!(performance.wins, 1);
    assert_eq!(performance.net_pnl_usd, 0.97);
    let long = &row.execution_performance_by_side["long"];
    assert_eq!(long.closed_trades, 1);
    assert_eq!(long.net_pnl_usd, 0.97);
    let repeatability = row
        .repeatability_evidence
        .as_ref()
        .expect("repeatability evidence");
    assert_eq!(repeatability.closed_trades(), 1);
    assert_eq!(repeatability.evidence_state(), "single_trade_only");
    assert_eq!(repeatability.observation_span_hours(), 1.0);
    assert_eq!(repeatability.trades_per_24h_observed(), None);
    assert_eq!(
        repeatability.net_pnl_excluding_largest_winner_usd(),
        Some(0.0)
    );
    assert_eq!(
        row.forward_assessment.as_deref(),
        Some("descriptive_adverse_paths")
    );
}

#[test]
fn accepts_provider_history_when_restarted_run_has_no_closed_trades() {
    let document = restarted_run_checkpoint();

    let parsed = parse_cohort_checkpoint(&document.to_string())
        .expect("provider history is independent of the restarted run");

    assert_eq!(parsed.closed_trades, Some(0));
    assert_eq!(
        parsed.observer_provider_journal[0]
            .execution_performance
            .as_ref()
            .expect("provider history")
            .closed_trades,
        2
    );
}

#[test]
fn rejects_scorecard_that_disagrees_with_provider_contract_history() {
    let mut document = restarted_run_checkpoint();
    document["audit"]["trade_reflections"]["provider_contract_history"]["compatible_trades"] =
        json!(3);

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("provider history count must remain internally consistent");

    assert!(error.contains("provider contract history"), "{error}");
}

#[test]
fn rejects_strategy_scorecard_with_a_performance_gate() {
    let mut document = checkpoint();
    document["audit"]["strategy_scorecard"]["contract"]["performance_gate"] = json!(true);

    let error = parse_cohort_checkpoint(&document.to_string()).expect_err("gate must fail closed");

    assert!(error.contains("report-only contract"), "{error}");
}

#[test]
fn rejects_strategy_scorecard_with_a_balance_gate() {
    let mut document = checkpoint();
    document["audit"]["strategy_scorecard"]["contract"]["balance_gate"] = json!(true);

    let error = parse_cohort_checkpoint(&document.to_string()).expect_err("gate must fail closed");

    assert!(error.contains("report-only contract"), "{error}");
}

#[test]
fn rejects_strategy_scorecard_with_a_trade_count_gate() {
    let mut document = checkpoint();
    document["audit"]["strategy_scorecard"]["contract"]["trade_count_gate"] = json!(true);

    let error = parse_cohort_checkpoint(&document.to_string()).expect_err("gate must fail closed");

    assert!(error.contains("report-only contract"), "{error}");
}

#[test]
fn rejects_live_performance_with_an_unsupported_scope() {
    let mut document = live_checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"]["execution_performance_scope"] =
        json!("all_live_history");

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("all-time history must not masquerade as a current contract sample");

    assert!(error.contains("performance scope"), "{error}");
}

#[test]
fn rejects_repeatability_that_claims_a_profit_forecast() {
    let mut document = live_checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"]["repeatability_evidence"]
        ["profit_forecast"] = json!(100.0);

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("profit forecast must remain absent");

    assert!(error.contains("forecast"), "{error}");
}

#[test]
fn rejects_repeatability_with_success_shaped_cadence() {
    let mut document = live_checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"]["repeatability_evidence"]
        ["trades_per_24h_observed"] = json!(24.0);

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("single-trade cadence must remain unavailable");

    assert!(error.contains("timing or sample state"), "{error}");
}

#[test]
fn rejects_identifiable_execution_without_an_exact_summary() {
    let mut document = live_checkpoint();
    let record = &mut document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"];
    record
        .as_object_mut()
        .expect("scorecard record")
        .remove("execution_performance");

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("missing execution summary must fail closed");

    assert!(error.contains("execution outcome"), "{error}");
}

#[test]
fn rejects_side_performance_that_disagrees_with_pair_total() {
    let mut document = live_checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"]["execution_performance_by_side"]
        ["long"]["net_pnl_usd"] = json!(0.50);

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("side aggregate mismatch must fail closed");

    assert!(error.contains("side execution"), "{error}");
}

#[test]
fn rejects_strategy_scorecard_without_exact_provider_coverage() {
    let mut document = checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"] = json!({});

    let error = parse_cohort_checkpoint(&document.to_string()).expect_err("coverage must be exact");

    assert!(error.contains("coverage"), "{error}");
}

#[test]
fn rejects_directional_research_with_a_mismatched_side() {
    let mut document = checkpoint();
    document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"]["directional_research"]
        ["long"]["side"] = json!("short");

    let error = parse_cohort_checkpoint(&document.to_string())
        .expect_err("direction identity must fail closed");

    assert!(error.contains("directional research"), "{error}");
}

fn checkpoint() -> Value {
    json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_observer_checkpoint",
        "generated_at_utc": "2026-08-02T12:30:00+00:00",
        "observer": {
            "state": "setup_process_observation",
            "run_id": "observer-a",
            "last_observed_at_utc": "2026-08-02T12:29:59+00:00"
        },
        "audit": {
            "technical": {"complete": true, "technical_gaps": []},
            "runtime": {"poll_cycles": 12},
            "readiness": {
                "evaluations": 9,
                "by_provider_symbol": {
                    "hype|HYPE": {
                        "count": 9,
                        "eligible": 1,
                        "latest_fraction": 0.3333333333333333,
                        "latest_side": "short",
                        "latest_reason": "5m_not_breakout",
                        "latest_blockers": ["5m_not_breakout"]
                    }
                }
            },
            "signals": {"strategy_intents": 1},
            "signal_outcomes": {
                "evaluations": 9,
                "eligible_evaluations": 1,
                "coverage": {"complete": true},
                "by_provider_symbol": {
                    "hype|HYPE": {
                        "evaluations": 9,
                        "eligible_evaluations": 1,
                        "horizons": {
                            "5": {
                                "resolved": 1,
                                "non_overlapping_resolved": 1,
                                "mean_directional_close_return_bps": -49.6,
                                "positive_directional_rate": 0.0
                            }
                        }
                    }
                }
            },
            "strategy_scorecard": {
                "contract": {
                    "report_only": true,
                    "performance_gate": false,
                    "balance_gate": false,
                    "automatic_pause": false,
                    "automatic_retuning": false,
                    "execution_authority": "none"
                },
                "by_provider_symbol": {
                    "hype|HYPE": {
                        "strategy_id": "hype",
                        "symbol": "HYPE",
                        "research_state": "forward_observer",
                        "confidence": "low",
                        "historical_cadence": "not established; measuring each onset",
                        "historical_summary": "No stable outcome record is bound.",
                        "evidence_source": "docs/reviews/provider.md",
                        "directional_research": {
                            "long": {
                                "side": "long",
                                "research_state": "historical_candidate",
                                "confidence": "medium",
                                "cadence": "45 trades / 365 days",
                                "summary": "Positive in three chronological segments.",
                                "evidence_source": "data/logs/research/eth.json",
                                "execution_effect": "report_only"
                            },
                            "short": {
                                "side": "short",
                                "research_state": "contradictory",
                                "confidence": "medium",
                                "cadence": "41 trades / 365 days",
                                "summary": "Development and pseudo-holdout were negative.",
                                "evidence_source": "data/logs/research/eth.json",
                                "execution_effect": "report_only"
                            }
                        },
                        "forward_assessment": "descriptive_adverse_paths",
                        "strategy_edge_identifiable": false,
                        "execution_outcomes_identifiable": false,
                        "performance_gate": false,
                        "execution_effect": "report_only"
                    }
                }
            },
            "learning": {
                "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes"
            }
        }
    })
}

fn restarted_run_checkpoint() -> Value {
    let mut document = live_checkpoint();
    document["audit"]["execution"]["closed_trades"] = json!(0);
    document["audit"]["execution"]["net_pnl_usd"] = json!(0.0);
    let record = &mut document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"];
    record["execution_performance"]["closed_trades"] = json!(2);
    record["execution_performance"]["wins"] = json!(2);
    record["execution_performance"]["entry_margin_used_usd"] = json!(10.0);
    record["execution_performance"]["net_pnl_usd"] = json!(1.94);
    record["execution_performance_by_side"]["long"] = record["execution_performance"].clone();
    record
        .as_object_mut()
        .expect("scorecard record")
        .remove("repeatability_evidence");
    document["audit"]["trade_reflections"] = json!({
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false,
            "automatic_strategy_changes": false
        },
        "closed_trades": 0,
        "context_coverage": {"complete": true},
        "trades": [],
        "provider_contract_history": {
            "scope": "provider_execution_contract_history",
            "compatible_trades": 2,
            "performance": {
                "scope": "provider_execution_contract_history",
                "total": {"closed_trades": 2}
            }
        }
    });
    document
}

fn live_checkpoint() -> Value {
    let mut document = checkpoint();
    document["mode"] = json!("multi_asset_bidirectional_live_checkpoint");
    document
        .as_object_mut()
        .expect("checkpoint object")
        .remove("observer");
    document["lifecycle"] = json!({
        "state": "running_consistent",
        "cohort_heartbeat_status": "running",
        "asset_states": {"HYPE": "FLAT"}
    });
    let audit = document["audit"].as_object_mut().expect("audit object");
    audit.remove("technical");
    audit.remove("runtime");
    audit.remove("signals");
    audit.insert(
        "coverage".into(),
        json!({"complete": true, "technical_gaps": []}),
    );
    audit.insert(
        "execution".into(),
        json!({"closed_trades": 1, "net_pnl_usd": 0.97}),
    );
    audit.insert(
        "learning".into(),
        json!({"evidence_state": "descriptive_trade_evidence"}),
    );
    let record = &mut document["audit"]["strategy_scorecard"]["by_provider_symbol"]["hype|HYPE"];
    record["execution_outcomes_identifiable"] = json!(true);
    record["execution_performance_scope"] = json!("provider_execution_contract_history");
    record["execution_performance"] = json!({
        "closed_trades": 1,
        "wins": 1,
        "losses": 0,
        "breakeven": 0,
        "win_rate_pct": 100.0,
        "net_pnl_usd": 0.97,
        "entry_margin_used_usd": 5.0,
        "net_return_on_margin_pct": 19.4,
        "mean_trade_return_on_margin_pct": 19.4,
        "profit_factor": null,
        "fees_usd": 0.02,
        "funding_usd": -0.01
    });
    record["execution_performance_by_side"] = json!({
        "long": record["execution_performance"].clone()
    });
    record["repeatability_evidence"] = json!({
        "strategy_id": "hype",
        "symbol": "HYPE",
        "closed_trades": 1,
        "evidence_state": "single_trade_only",
        "first_entry_timestamp_ms": 1_700_000_000_000_u64,
        "last_exit_timestamp_ms": 1_700_003_600_000_u64,
        "observation_span_hours": 1.0,
        "trades_per_24h_observed": null,
        "net_pnl_usd": 0.97,
        "mean_net_pnl_usd": 0.97,
        "median_net_pnl_usd": 0.97,
        "sample_stddev_net_pnl_usd": null,
        "gross_profit_usd": 0.97,
        "gross_loss_usd": 0.0,
        "profit_factor": null,
        "largest_winner_usd": 0.97,
        "largest_winner_share_of_gross_profit_pct": 100.0,
        "net_pnl_excluding_largest_winner_usd": 0.0,
        "by_side": {
            "long": {
                "closed_trades": 1,
                "evidence_state": "single_trade_only",
                "first_entry_timestamp_ms": 1_700_000_000_000_u64,
                "last_exit_timestamp_ms": 1_700_003_600_000_u64,
                "observation_span_hours": 1.0,
                "trades_per_24h_observed": null,
                "net_pnl_usd": 0.97,
                "mean_net_pnl_usd": 0.97,
                "median_net_pnl_usd": 0.97,
                "sample_stddev_net_pnl_usd": null,
                "gross_profit_usd": 0.97,
                "gross_loss_usd": 0.0,
                "profit_factor": null,
                "largest_winner_usd": 0.97,
                "largest_winner_share_of_gross_profit_pct": 100.0,
                "net_pnl_excluding_largest_winner_usd": 0.0
            }
        },
        "profit_forecast": null
    });
    document
}
