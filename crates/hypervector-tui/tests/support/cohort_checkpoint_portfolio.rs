#[test]
fn projects_the_predeclared_asymmetric_portfolio_observer() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["asymmetric_forward_observer"] = asymmetric_observer();

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid observer");
    let observer = parsed
        .asymmetric_forward_observer
        .expect("asymmetric observer");

    assert_eq!(observer.evidence_state, "prospective_resolutions_observed");
    assert_eq!(observer.candidate.closed_trades, 2);
    assert_eq!(observer.candidate.net_pnl_usd, 0.5);
    assert_eq!(observer.excluded_symmetric_sides.closed_trades, 1);
    assert_eq!(observer.excluded_symmetric_sides.net_pnl_usd, -1.0);
    assert_eq!(observer.source_counts.pre_cutoff_in_scope, 3);
}

#[test]
fn rejects_asymmetric_observer_with_execution_authority() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["asymmetric_forward_observer"] = asymmetric_observer();
    checkpoint["audit"]["asymmetric_forward_observer"]["contract"]["execution_authority"] =
        serde_json::json!("hyperliquid_mainnet");

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("asymmetric observer authority must fail");

    assert!(error.contains("asymmetric portfolio observer contract"));
}

#[test]
fn projects_ranked_route_side_composition() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["side_composition"] = side_composition();

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid composition");
    let composition = parsed.side_composition.expect("side composition");

    assert_eq!(composition.components, 2);
    assert_eq!(composition.long_frontier.len(), 1);
    assert_eq!(composition.short_frontier.len(), 1);
    assert_eq!(
        composition.long_frontier[0].component,
        "hype_breakout_onset_bidirectional_v1|HYPE|long"
    );
    assert_eq!(composition.long_frontier[0].trades, 8);
    assert_eq!(composition.long_frontier[0].net_pnl_usd, 0.502458);
    assert_eq!(composition.short_frontier[0].trades, 1);
}

#[test]
fn rejects_side_composition_with_execution_authority() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["side_composition"] = side_composition();
    checkpoint["audit"]["side_composition"]["contract"]["execution_authority"] =
        serde_json::json!("hyperliquid_mainnet");

    let error = parse_cohort_checkpoint(&checkpoint.to_string())
        .expect_err("side composition authority must fail");

    assert!(error.contains("side composition contract"));
}

#[test]
fn projects_four_asset_portfolio_archive_without_inflating_current_run() {
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["portfolio_archive"] = serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false
        },
        "symbols": ["BTC", "ETH", "SOL", "HYPE"],
        "accounting_epoch": {
            "epoch_id": "growth_5000_v51",
            "profile_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "start_venue_timestamp_ms": 1786648891318_u64
        },
        "coverage": {
            "complete": true,
            "closed_orders": 26,
            "leverage_matches": 26
        },
        "performance": {
            "scope": "all_live_history",
            "return_basis": "net_pnl_divided_by_sum_entry_margin",
            "total": performance_summary(26, 13, 13, -1.695979, 198.277796, Some(0.654718)),
            "by_strategy": {
                "hulk_expansion_bidirectional_tuned_v2":
                    performance_summary(2, 2, 0, 0.343915, 9.901729, None),
                "hype_breakout_onset_bidirectional_v1":
                    performance_summary(18, 8, 10, -1.760917, 149.334936, Some(0.599289)),
                "hypervelocity_source_follow_bidirectional_5m_v1":
                    performance_summary(5, 3, 2, -0.104597, 24.588796, Some(0.695054)),
                "range_onset_bidirectional_v1":
                    performance_summary(1, 0, 1, -0.174380, 14.452335, Some(0.0))
            },
            "by_provider_symbol": {},
            "limitations": []
        },
        "preserved_history": {
            "scope": "full_backend_history",
            "symbols": ["BTC", "ETH", "SOL", "HYPE", "ZEC", "xyz:SPCX", "xyz:SNDK"],
            "observed_through_utc": "2026-09-03T19:05:00+00:00",
            "coverage": {
                "complete": true,
                "closed_orders": 123,
                "leverage_matches": 123
            },
            "performance": {
                "scope": "all_live_history",
                "return_basis": "net_pnl_divided_by_sum_entry_margin",
                "total": performance_summary(123, 50, 73, -316.779764, 1000.0, Some(0.5)),
                "by_strategy": {
                    "strategy": performance_summary(
                        123,
                        50,
                        73,
                        -316.779764,
                        1000.0,
                        Some(0.5),
                    )
                },
                "by_provider_symbol": {},
                "limitations": []
            }
        }
    });

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid archive");

    let archive = parsed.portfolio_archive.expect("portfolio archive");
    assert_eq!(archive.symbols, ["BTC", "ETH", "SOL", "HYPE"]);
    assert_eq!(archive.performance.total.closed_trades, 26);
    assert_eq!(archive.performance.total.wins, 13);
    assert_eq!(archive.performance.total.losses, 13);
    let preserved = archive.preserved_history.expect("preserved backend history");
    assert_eq!(preserved.performance.total.closed_trades, 123);
    assert_eq!(preserved.performance.total.wins, 50);
    assert_eq!(preserved.performance.total.losses, 73);
    assert_eq!(
        archive.accounting_epoch.expect("accounting epoch").epoch_id,
        "growth_5000_v51"
    );
    assert_eq!(parsed.closed_trades, Some(0));
}

#[test]
fn projects_exact_accounting_epoch_profile_lineage() {
    let current = "b".repeat(64);
    let parent = "a".repeat(64);
    let mut checkpoint = minimal_checkpoint();
    checkpoint["audit"]["portfolio_archive"] = portfolio_archive_with_epoch(
        serde_json::json!({
            "epoch_id": "v58_v59_growth_5000",
            "profile_fingerprint": current,
            "start_venue_timestamp_ms": 1787164729837_u64,
            "included_profile_fingerprints": [parent, current]
        }),
    );

    let parsed = parse_cohort_checkpoint(&checkpoint.to_string()).expect("valid lineage");
    let epoch = parsed
        .portfolio_archive
        .expect("portfolio archive")
        .accounting_epoch
        .expect("accounting epoch");

    assert_eq!(epoch.included_profile_fingerprints, ["a".repeat(64), "b".repeat(64)]);
}

#[test]
fn rejects_invalid_accounting_epoch_profile_lineages() {
    let current = "b".repeat(64);
    let invalid = [
        serde_json::json!(["a".repeat(64), current, current]),
        serde_json::json!(["not-a-fingerprint", current]),
        serde_json::json!(["a".repeat(64)]),
    ];
    for included in invalid {
        let mut checkpoint = minimal_checkpoint();
        checkpoint["audit"]["portfolio_archive"] = portfolio_archive_with_epoch(
            serde_json::json!({
                "epoch_id": "v58_v59_growth_5000",
                "profile_fingerprint": current,
                "start_venue_timestamp_ms": 1787164729837_u64,
                "included_profile_fingerprints": included
            }),
        );

        let error = parse_cohort_checkpoint(&checkpoint.to_string())
            .expect_err("invalid lineage must fail closed");

        assert!(error.contains("portfolio archive contract is invalid"));
    }
}

fn portfolio_archive_with_epoch(epoch: serde_json::Value) -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_live_portfolio_archive_v1",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false
        },
        "symbols": ["BTC", "ETH", "SOL", "HYPE"],
        "accounting_epoch": epoch,
        "coverage": {
            "complete": true,
            "closed_orders": 0,
            "leverage_matches": 0
        },
        "performance": {
            "scope": "all_live_history",
            "return_basis": "net_pnl_divided_by_sum_entry_margin",
            "total": performance_summary(0, 0, 0, 0.0, 0.0, None),
            "by_strategy": {},
            "by_provider_symbol": {},
            "limitations": []
        }
    })
}

fn asymmetric_observer() -> serde_json::Value {
    serde_json::json!({
        "schema_version": 1,
        "mode": "cohort_asymmetric_shared_portfolio_forward_observer_v1",
        "scope": "resolved_venue_lifecycles_entered_at_or_after_predeclared_cutoff",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "runtime_strategy_changed": false,
            "automatic_strategy_changes": false,
            "automatic_promotion": false,
            "performance_gate": false,
            "balance_gate": false,
            "trade_count_gate": false,
            "actual_resolved_lifecycles_only": true,
            "counterfactual_fills_claimed": false,
            "capital_reallocation_claimed": false
        },
        "hypothesis_id": "cohort-asymmetric-shared-portfolio",
        "selected_variant_id": "sol_symmetric_sensitivity",
        "current_profile_fingerprint": "profile-v25",
        "current_run_id": "run-v25",
        "predeclared_at_utc": "2026-08-09T06:02:47Z",
        "entry_cutoff_timestamp_ms": 1786255367000_u64,
        "candidate_route_sides": [
            ["hype_breakout_onset_bidirectional_v1", "HYPE", "long"],
            ["eth_breakout_precompression_pullback_bidirectional_v1", "ETH", "long"],
            ["range_onset_bidirectional_v1", "SOL", "long"],
            ["range_onset_bidirectional_v1", "SOL", "short"]
        ],
        "excluded_symmetric_route_sides": [
            ["hype_breakout_onset_bidirectional_v1", "HYPE", "short"],
            ["eth_breakout_precompression_pullback_bidirectional_v1", "ETH", "short"]
        ],
        "source_counts": {
            "candidate_post_cutoff": 2,
            "excluded_symmetric_post_cutoff": 1,
            "pre_cutoff_in_scope": 3,
            "profile_mismatch_in_scope": 0,
            "unrelated": 4
        },
        "candidate": observer_economics(2, 1, 1, 0.5, Some(2.0), Some(-0.5)),
        "excluded_symmetric_sides": observer_economics(
            1,
            0,
            1,
            -1.0,
            Some(0.0),
            None,
        ),
        "evidence_state": "prospective_resolutions_observed",
        "limitations": ["report only"]
    })
}

fn side_composition() -> serde_json::Value {
    serde_json::json!({
        "schema_version": 2,
        "mode": "cohort_separate_side_composition",
        "contract": {
            "report_only": true,
            "execution_authority": "none",
            "performance_gate": false,
            "balance_gate": false,
            "trade_count_gate": false,
            "automatic_promotion": false,
            "runtime_strategy_changed": false,
            "ranking_only": true,
            "descriptive_tier_profit_factor_basis": "normalized_profit_factor",
            "minimum_repeated_trades_for_descriptive_tier": 5,
            "mixed_profile_history_is_not_current_profile_edge": true
        },
        "source": {
            "run_id": "run-v25",
            "profile_id": "profile-v25",
            "profile_fingerprint": "fingerprint-v25",
            "as_of_utc": "2026-08-09T11:30:00+00:00",
            "live_history_scope": "all_live_history_mixed_profiles"
        },
        "summary": {
            "components": 2,
            "long_frontier_components": 1,
            "short_frontier_components": 1,
            "both_side_frontier_available": true,
            "evidence_tiers": {
                "positive_sparse_mixed_profile": 1,
                "repeated_positive_mixed_profile": 1
            },
            "automatic_promotion": false,
            "runtime_strategy_changed": false
        },
        "frontier": {
            "long": [{
                "component": "hype_breakout_onset_bidirectional_v1|HYPE|long",
                "priority": 4,
                "evidence_tier": "repeated_positive_mixed_profile",
                "evidence_tension": true,
                "trades": 8,
                "net_pnl_usd": 0.502458,
                "usd_profit_factor": 1.30454,
                "normalized_profit_factor": 3.079128
            }],
            "short": [{
                "component": "hypervelocity_source_follow_bidirectional_5m_v1|BTC|short",
                "priority": 3,
                "evidence_tier": "positive_sparse_mixed_profile",
                "evidence_tension": true,
                "trades": 1,
                "net_pnl_usd": 0.135163,
                "usd_profit_factor": null,
                "normalized_profit_factor": null
            }]
        },
        "components": {
            "hype_breakout_onset_bidirectional_v1|HYPE|long": {},
            "hypervelocity_source_follow_bidirectional_5m_v1|BTC|short": {}
        }
    })
}

fn observer_economics(
    closed_trades: usize,
    wins: usize,
    losses: usize,
    net_pnl_usd: f64,
    profit_factor: Option<f64>,
    net_without_largest: Option<f64>,
) -> serde_json::Value {
    serde_json::json!({
        "closed_trades": closed_trades,
        "wins": wins,
        "losses": losses,
        "breakeven": 0,
        "net_pnl_usd": net_pnl_usd,
        "fees_usd": 0.2,
        "funding_usd": -0.02,
        "profit_factor": profit_factor,
        "mean_return_on_margin_pct": 1.0,
        "median_return_on_margin_pct": 1.0,
        "largest_winner_usd": if wins > 0 { Some(1.0) } else { None },
        "net_pnl_excluding_largest_winner_usd": net_without_largest,
        "by_route_side": {}
    })
}

fn performance_summary(
    closed: usize,
    wins: usize,
    losses: usize,
    net_pnl_usd: f64,
    margin_usd: f64,
    profit_factor: Option<f64>,
) -> serde_json::Value {
    serde_json::json!({
        "closed_trades": closed,
        "wins": wins,
        "losses": losses,
        "breakeven": 0,
        "win_rate_pct": wins as f64 / closed as f64 * 100.0,
        "net_pnl_usd": net_pnl_usd,
        "entry_margin_used_usd": margin_usd,
        "net_return_on_margin_pct": net_pnl_usd / margin_usd * 100.0,
        "mean_trade_return_on_margin_pct": net_pnl_usd / margin_usd * 100.0,
        "profit_factor": profit_factor,
        "fees_usd": 0.0,
        "funding_usd": 0.0
    })
}
