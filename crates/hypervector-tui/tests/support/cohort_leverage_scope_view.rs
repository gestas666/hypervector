#[test]
fn leverage_rows_retain_configured_and_venue_values_at_every_layout() {
    let mut app = complete_portfolio_app();
    app.backend.cohort.assets[0].leverage = Some(10);
    app.backend.cohort.asset_configs[0].leverage = 20.0;
    for (width, height) in [(100, 28), (119, 35), (120, 36), (159, 40), (190, 52)] {
        for tab in [0, 4] {
            let screen = render(&mut app, tab, width, height);
            let row = screen.lines().find(|line| line.contains("BTC") && line.contains("LONG"))
                .expect("BTC position row");
            assert!(screen.contains("LEV C/V"), "{width}x{height} tab {tab}\n{screen}");
            assert!(row.contains(" 20x/10x"), "{width}x{height} tab {tab}\n{screen}");
        }
    }
}

#[test]
fn leverage_rows_do_not_substitute_configuration_for_missing_venue_evidence() {
    let mut app = complete_portfolio_app();
    app.backend.cohort.asset_configs[0].leverage = 20.0;
    app.backend.cohort.assets[0].leverage = None;
    for flat in [false, true] {
        if flat {
            app.backend.cohort.assets[0].position_side = None;
            app.backend.cohort.assets[0].position_size_signed = 0.0;
            app.backend.cohort.assets[0].state = "FLAT".into();
        }
        for width in [100, 120, 190] {
            let screen = render(&mut app, 0, width, 52);
            let row = screen.lines().find(|line| line.contains("BTC") && line.contains(if flat { "FLAT" } else { "LONG" })).unwrap();
            let expected = if flat { "20x/-" } else { "20x/N/A" };
            assert!(row.contains(expected), "{width}\n{screen}");
        }
    }
}

#[test]
fn rolling_execution_label_follows_checkpoint_scope_instead_of_inventing_a_run() {
    for (scope, label) in [(Some("compatible_profile_history"), "PROFILE"),
                           (Some("current_run"), "RUN"), (None, "SCOPE N/A"),
                           (Some("unknown_scope"), "SCOPE N/A")] {
        let raw = json!({
            "schema_version": 1, "mode": "multi_asset_bidirectional_live_checkpoint",
            "generated_at_utc": "2026-09-15T16:00:00Z",
            "lifecycle": {"state": "running_consistent", "asset_states": {"BTC": "FLAT"}},
            "audit": {"coverage": {"complete": true, "technical_gaps": []},
                "readiness": {"evaluations": 1},
                "execution": {"scope": scope, "closed_trades": 8, "net_pnl_usd": -25.61},
                "learning": {"evidence_state": "descriptive_trade_evidence"}}
        });
        let mut app = complete_portfolio_app();
        app.backend.cohort_checkpoint = hypervector_tui::backend_cohort_checkpoint::parse_cohort_checkpoint(&raw.to_string()).unwrap();
        let screen = render(&mut app, 0, 190, 52);
        assert!(screen.contains(&format!("{label} 8C NET -$25.61")), "scope {scope:?}\n{screen}");
    }
}
