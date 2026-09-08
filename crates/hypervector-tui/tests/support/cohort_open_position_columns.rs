fn sndk_open_position_app() -> App {
    let mut app = complete_portfolio_app();
    let mut asset = app.backend.cohort.assets[0].clone();
    asset.symbol = "xyz:SNDK".into();
    asset.position_side = Some("long".into());
    asset.state = "OPEN".into();
    asset.entry_price = Some(1803.4);
    asset.mark_price = Some(1804.1);
    asset.stop_oid = Some(538_806_460_232);
    asset.target_oid = None;
    asset.target_price = None;
    asset.margin_used_usd = 49.95;
    asset.position_value_usd = 497.93;
    asset.fees_net_usd = Some(0.04);
    asset.funding_net_usd = Some(0.0);
    app.backend.cohort.assets[6] = asset;
    app
}

#[test]
fn compact_dashboard_preserves_full_open_stop_identity_and_costs() {
    let mut app = sndk_open_position_app();
    let screen = render(&mut app, 0, 120, 36);
    let row = screen
        .lines()
        .find(|line| line.contains("xyz:SNDK") && line.contains("LONG"))
        .expect("SNDK open position row");
    assert!(row.contains("STOP #538806460232"), "{screen}");
    assert!(row.contains("$0.04 / +0.00"), "{screen}");
    assert!(row.contains("$1803.4000"), "{screen}");
    assert!(screen.contains("PLAN/FAULT"), "{screen}");
}

#[test]
fn compact_trade_tracker_preserves_full_margin_and_notional() {
    let mut app = sndk_open_position_app();
    let screen = render(&mut app, 4, 120, 36);
    let row = screen
        .lines()
        .find(|line| line.contains("xyz:SNDK") && line.contains("LONG"))
        .expect("SNDK open risk row");
    assert!(row.contains("$49.95/$497.93"), "{screen}");
    assert!(row.contains("STOP #538806460232"), "{screen}");
    assert!(screen.contains("MARGIN/NOTIONAL"), "{screen}");
}

#[test]
fn wide_position_views_preserve_the_same_full_native_stop_id() {
    let mut app = sndk_open_position_app();
    for tab in [0, 4] {
        let screen = render(&mut app, tab, 190, 52);
        assert!(screen.contains("STOP #538806460232"), "{screen}");
        assert!(screen.contains("xyz:SNDK"), "{screen}");
    }
}

#[test]
fn minimum_dashboard_keeps_every_asset_and_selected_open_details_visible() {
    let mut app = sndk_open_position_app();
    app.selected_cohort_symbol_index = 6;
    for (width, height) in [(100, 28), (120, 28), (119, 36)] {
        let screen = render(&mut app, 0, width, height);
        for symbol in COMPLETE_SYMBOLS {
            assert!(screen.contains(symbol), "missing {symbol}\n{screen}");
        }
        for expected in [
            "STOP #538806460232",
            "$49.95/$497.93",
            "STATE OPEN",
            "LIQ",
            "PLAN",
        ] {
            assert!(screen.contains(expected), "missing {expected}\n{screen}");
        }
    }
}

#[test]
fn minimum_trade_view_keeps_open_positions_ahead_of_flat_rows() {
    let mut app = sndk_open_position_app();
    let screen = render(&mut app, 4, 100, 28);
    for expected in [
        "xyz:SNDK",
        "STOP #538806460232",
        "$49.95/$497.93",
        "COMPLETED TRADES",
        "VENUE FILL LEGS",
    ] {
        assert!(screen.contains(expected), "missing {expected}\n{screen}");
    }
}
