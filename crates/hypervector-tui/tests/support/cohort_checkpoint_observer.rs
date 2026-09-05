#[test]
fn parses_observer_setup_evidence_without_execution_outcomes() {
    let checkpoint = r#"{
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
                "evaluations": 18,
                "by_provider_symbol": {
                    "hulk|BTC": {
                        "count": 9,
                        "eligible": 1,
                        "latest_fraction": 0.8333333333333334,
                        "latest_side": "long",
                        "latest_reason": "no_trigger",
                        "latest_blockers": ["squeeze_not_armed"]
                    },
                    "range|SOL": {
                        "count": 4,
                        "eligible": 0,
                        "latest_fraction": 0.3333333333333333,
                        "latest_side": "short",
                        "latest_reason": "regime_not_admitted",
                        "latest_blockers": ["5m_regime_not_admitted"]
                    },
                    "hype|HYPE": {
                        "count": 5,
                        "eligible": 0,
                        "latest_fraction": 0.3333333333333333,
                        "latest_side": "short",
                        "latest_reason": "5m_not_breakout",
                        "latest_blockers": ["5m_not_breakout"]
                    }
                }
            },
            "signals": {"strategy_intents": 1},
            "signal_outcomes": {
                "evaluations": 14,
                "eligible_evaluations": 1,
                "coverage": {"complete": true},
                "by_provider_symbol": {
                    "hulk|BTC": {
                        "evaluations": 9,
                        "eligible_evaluations": 1,
                        "horizons": {
                            "5": {
                                "resolved": 9,
                                "non_overlapping_resolved": 3,
                                "censored": 0,
                                "missing_data": 0,
                                "mean_directional_close_return_bps": 4.25,
                                "positive_directional_rate": 0.6666666666666666
                            },
                            "15": {
                                "resolved": 4,
                                "non_overlapping_resolved": 1,
                                "censored": 5,
                                "missing_data": 0,
                                "mean_directional_close_return_bps": -2.0,
                                "positive_directional_rate": 0.25
                            },
                            "30": {"resolved": 0, "non_overlapping_resolved": 0},
                            "60": {"resolved": 0, "non_overlapping_resolved": 0}
                        },
                        "by_evidence_class": {
                            "eligible_signal": {
                                "evaluations": 1,
                                "horizons": {
                                    "5": {
                                        "resolved": 1,
                                        "non_overlapping_resolved": 1,
                                        "censored": 0,
                                        "missing_data": 0,
                                        "mean_directional_close_return_bps": 12.0,
                                        "positive_directional_rate": 1.0
                                    }
                                }
                            },
                            "readiness_annotation": {
                                "evaluations": 8,
                                "horizons": {
                                    "5": {
                                        "resolved": 8,
                                        "non_overlapping_resolved": 2,
                                        "censored": 0,
                                        "missing_data": 0,
                                        "mean_directional_close_return_bps": 3.28125,
                                        "positive_directional_rate": 0.625
                                    }
                                }
                            }
                        }
                    },
                    "range|SOL": {
                        "evaluations": 4,
                        "eligible_evaluations": 0,
                        "horizons": {
                            "5": {
                                "resolved": 4,
                                "non_overlapping_resolved": 2,
                                "censored": 0,
                                "missing_data": 0,
                                "mean_directional_close_return_bps": 1.5,
                                "positive_directional_rate": 0.75
                            },
                            "15": {"resolved": 0, "non_overlapping_resolved": 0},
                            "30": {"resolved": 0, "non_overlapping_resolved": 0},
                            "60": {"resolved": 0, "non_overlapping_resolved": 0}
                        }
                    }
                }
            },
            "learning": {
                "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes"
            }
        }
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid observer checkpoint");

    assert_eq!(parsed.analysis_mode.as_deref(), Some("forward_observer"));
    assert_eq!(
        parsed.lifecycle_state.as_deref(),
        Some("setup_process_observation")
    );
    assert!(parsed.asset_states.is_empty());
    assert_eq!(parsed.coverage_complete, Some(true));
    assert_eq!(parsed.readiness_evaluations, Some(18));
    assert_eq!(parsed.strategy_intents, Some(1));
    assert_eq!(parsed.forward_evaluations, Some(14));
    assert_eq!(parsed.eligible_signals, Some(1));
    assert_eq!(parsed.five_minute_paths_resolved, Some(13));
    assert_eq!(parsed.five_minute_paths_independent, Some(5));
    assert_eq!(parsed.forward_path_coverage_complete, Some(true));
    assert_eq!(parsed.observer_provider_journal.len(), 3);
    let hulk = parsed
        .observer_provider_journal
        .iter()
        .find(|row| row.strategy_id == "hulk" && row.symbol == "BTC")
        .expect("Hulk journal row");
    assert_eq!(hulk.latest_side.as_deref(), Some("long"));
    assert_eq!(hulk.readiness_fraction, Some(0.8333333333333334));
    assert_eq!(hulk.latest_reason.as_deref(), Some("no_trigger"));
    assert_eq!(hulk.latest_blockers, ["squeeze_not_armed"]);
    assert_eq!(hulk.readiness_evaluations, 9);
    assert_eq!(hulk.eligible_signals, 1);
    let five = &hulk.paths[&5];
    assert_eq!(five.resolved, 9);
    assert_eq!(five.independent, 3);
    assert_eq!(five.mean_directional_return_bps, Some(4.25));
    assert_eq!(five.positive_directional_rate, Some(2.0 / 3.0));
    let fired_five = &hulk.eligible_paths[&5];
    assert_eq!(fired_five.resolved, 1);
    assert_eq!(fired_five.independent, 1);
    assert_eq!(fired_five.mean_directional_return_bps, Some(12.0));
    let setup_five = &hulk.readiness_paths[&5];
    assert_eq!(setup_five.resolved, 8);
    assert_eq!(setup_five.independent, 2);
    assert_eq!(setup_five.mean_directional_return_bps, Some(3.28125));
    assert!(
        parsed
            .observer_provider_journal
            .iter()
            .find(|row| row.strategy_id == "hype" && row.symbol == "HYPE")
            .expect("readiness-only HYPE row")
            .paths
            .is_empty()
    );
    assert_eq!(parsed.closed_trades, None);
    assert_eq!(parsed.net_pnl_usd, None);
    assert_eq!(
        parsed.evidence_state.as_deref(),
        Some("setup_and_signal_paths_only_no_execution_outcomes")
    );
}

const INVALID_OBSERVER_PATH_CHECKPOINT: &str = r#"{
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
            "runtime": {"poll_cycles": 1},
            "readiness": {
                "evaluations": 1,
                "by_provider_symbol": {
                    "hulk|BTC": {
                        "count": 1,
                        "eligible": 0,
                        "latest_fraction": 0.5,
                        "latest_side": "long",
                        "latest_reason": "no_trigger",
                        "latest_blockers": []
                    }
                }
            },
            "signals": {"strategy_intents": 0},
            "signal_outcomes": {
                "evaluations": 1,
                "eligible_evaluations": 0,
                "coverage": {"complete": true},
                "by_provider_symbol": {
                    "hulk|BTC": {
                        "evaluations": 1,
                        "eligible_evaluations": 0,
                        "horizons": {
                            "5": {
                                "resolved": 1,
                                "non_overlapping_resolved": 1,
                                "mean_directional_close_return_bps": 2.0,
                                "positive_directional_rate": 1.5
                            }
                        }
                    }
                }
            },
            "learning": {
                "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes"
            }
        }
    }"#;

#[test]
fn rejects_invalid_observer_path_statistics() {
    let error =
        parse_cohort_checkpoint(INVALID_OBSERVER_PATH_CHECKPOINT).expect_err("invalid rate");

    assert!(error.contains("positive rate"), "{error}");
}

#[test]
fn rejects_incomplete_observer_path_statistics() {
    let checkpoint = INVALID_OBSERVER_PATH_CHECKPOINT.replace(
        "\"positive_directional_rate\": 1.5",
        "\"positive_directional_rate\": null",
    );

    let error = parse_cohort_checkpoint(&checkpoint).expect_err("incomplete statistics");

    assert!(error.contains("disagree with resolved count"), "{error}");
}

#[test]
fn parses_explicit_unavailable_checkpoint_without_success_shape() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-02T04:00:00+00:00",
        "status": {"state":"unavailable","technical_issue":"asset ledgers not ready"}
    }"#;

    let parsed = parse_cohort_checkpoint(checkpoint).expect("valid unavailable status");

    assert!(parsed.configured);
    assert!(!parsed.available);
    assert_eq!(parsed.issue.as_deref(), Some("asset ledgers not ready"));
    assert_eq!(parsed.coverage_complete, None);
    assert_eq!(parsed.closed_trades, None);
}

#[test]
fn rejects_a_ready_shape_without_audit_evidence() {
    let checkpoint = r#"{
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": "2026-08-02T04:00:00+00:00",
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC":"FLAT"}
        }
    }"#;

    let error = parse_cohort_checkpoint(checkpoint).expect_err("audit must be required");

    assert!(error.contains("audit"), "{error}");
}

#[test]
fn stale_observer_retains_diagnostics_and_explicit_no_execution_semantics() {
    let checkpoint = INVALID_OBSERVER_PATH_CHECKPOINT
        .replace("setup_process_observation", "stale_source")
        .replace("\"positive_directional_rate\": 1.5", "\"positive_directional_rate\": 0.5");
    let parsed = parse_cohort_checkpoint(&checkpoint).expect("valid stale observer");
    assert!(parsed.available);
    assert!(parsed.stale);
    assert_eq!(parsed.analysis_mode.as_deref(), Some("forward_observer"));
    assert_eq!(parsed.lifecycle_state.as_deref(), Some("stale_source"));
    assert_eq!(parsed.readiness_evaluations, Some(1));
    assert_eq!(parsed.closed_trades, None);
    assert_eq!(parsed.net_pnl_usd, None);
}

#[test]
fn unknown_observer_state_remains_invalid() {
    let checkpoint = INVALID_OBSERVER_PATH_CHECKPOINT
        .replace("setup_process_observation", "invented_ready")
        .replace("\"positive_directional_rate\": 1.5", "\"positive_directional_rate\": 0.5");
    assert!(parse_cohort_checkpoint(&checkpoint).is_err());
}
