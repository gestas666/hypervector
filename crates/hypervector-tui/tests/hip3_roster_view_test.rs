use hypervector_tui::backend_cohort::{CohortBookLevel, CohortBookSnapshot};
use hypervector_tui::backend_hip3_roster::{
    Hip3BookTelemetry, Hip3MarketTelemetry, Hip3RosterTelemetry, Hip3VenueTelemetry,
    WtiAliasTelemetry,
};
use hypervector_tui::cohort_hip3_roster::{market_row_values, roster_title};
use hypervector_tui::{App, cohort_view};
use ratatui::{Terminal, backend::TestBackend};

#[test]
fn roster_rows_show_exact_symbol_pressure_fee_and_unresolved_state() {
    let resolved = market("xyz:SP500", Some(0.0000864));
    let unresolved = market("xyz:GOLD", None);

    assert_eq!(
        market_row_values(&resolved),
        [
            "xyz:SP500",
            "7714.2000",
            "0.259",
            "-4/-23",
            "0.864",
            "N/A",
            "FLAT"
        ]
    );
    assert_eq!(market_row_values(&unresolved)[4], "UNRES");
}

#[test]
fn title_makes_report_only_and_wti_non_equivalence_visible() {
    let status = Hip3RosterTelemetry {
        configured: true,
        available: true,
        lifecycle: Some("running".into()),
        polls: Some(32),
        wti_alias: Some(WtiAliasTelemetry {
            status: "historical_only".into(),
            live_symbol: None,
            historical_symbol: "cash:WTI".into(),
            active_alternative: "xyz:BRENTOIL".into(),
            equivalence_assumed: false,
        }),
        ..Hip3RosterTelemetry::default()
    };

    let title = roster_title(&status);

    assert!(title.contains("REPORT ONLY"));
    assert!(title.contains("WTI HIST != BRENT"));
    assert!(title.contains("POLL 32"));
}

#[test]
fn stale_roster_title_and_table_do_not_present_old_account_data_as_live() {
    let mut app = App::new("BTC".into(), "5m".into(), Vec::new(), true, false);
    app.active_tab = 3;
    app.backend.cohort.enabled_symbols = vec!["BTC".into()];
    app.backend.cohort.books.insert("BTC".into(), crypto_book());
    app.backend.hip3_roster = Hip3RosterTelemetry {
        configured: true,
        available: true,
        stale: true,
        lifecycle: Some("stopped".into()),
        polls: Some(32),
        markets: vec![market("xyz:GOLD", None)],
        wti_alias: Some(WtiAliasTelemetry {
            status: "historical_only".into(),
            live_symbol: None,
            historical_symbol: "cash:WTI".into(),
            active_alternative: "xyz:BRENTOIL".into(),
            equivalence_assumed: false,
        }),
        ..Hip3RosterTelemetry::default()
    };
    let backend = TestBackend::new(180, 40);
    let mut terminal = Terminal::new(backend).expect("test terminal");

    terminal
        .draw(|frame| cohort_view::render(frame, &app))
        .expect("render stale depth screen");

    let text = terminal
        .backend()
        .buffer()
        .content()
        .iter()
        .map(|cell| cell.symbol())
        .collect::<String>();
    assert!(text.contains("STALE SNAPSHOT"), "{text}");
    assert!(text.contains("LAST ACCT"), "{text}");
}

#[test]
fn depth_screen_renders_backend_hip3_roster_without_local_fallback() {
    let mut app = App::new("BTC".into(), "5m".into(), Vec::new(), true, false);
    app.active_tab = 3;
    app.backend.cohort.enabled_symbols = vec!["BTC".into()];
    app.backend.cohort.books.insert("BTC".into(), crypto_book());
    app.backend.hip3_roster = Hip3RosterTelemetry {
        configured: true,
        available: true,
        lifecycle: Some("running".into()),
        polls: Some(32),
        markets: vec![
            market("xyz:SP500", Some(0.0000864)),
            market("xyz:GOLD", None),
        ],
        wti_alias: Some(WtiAliasTelemetry {
            status: "historical_only".into(),
            live_symbol: None,
            historical_symbol: "cash:WTI".into(),
            active_alternative: "xyz:BRENTOIL".into(),
            equivalence_assumed: false,
        }),
        ..Hip3RosterTelemetry::default()
    };
    let backend = TestBackend::new(180, 40);
    let mut terminal = Terminal::new(backend).expect("test terminal");

    terminal
        .draw(|frame| cohort_view::render(frame, &app))
        .expect("render depth screen");

    let text = terminal
        .backend()
        .buffer()
        .content()
        .iter()
        .map(|cell| cell.symbol())
        .collect::<String>();
    assert!(text.contains("HIP-3 RESEARCH"));
    assert!(text.contains("WTI HIST != BRENT"));
    assert!(text.contains("xyz:SP500"));
    assert!(text.contains("xyz:GOLD"));
    assert!(text.contains("UNRES"));
}

fn market(symbol: &str, taker_fee_rate: Option<f64>) -> Hip3MarketTelemetry {
    Hip3MarketTelemetry {
        symbol: symbol.into(),
        book: Hip3BookTelemetry {
            mid_price: 7714.2,
            spread_bps: 0.259,
            bid_levels: 20,
            ask_levels: 20,
            depth_5_pressure: -0.04,
            depth_20_pressure: -0.23,
            exchange_timestamp_ms: 1_786_041_106_711,
        },
        venue: Hip3VenueTelemetry {
            mark_price: 7713.65,
            max_leverage: 50,
            funding_rate_hourly: None,
            effective_fee_status: if taker_fee_rate.is_some() {
                "resolved".into()
            } else {
                "unresolved_growth_mode".into()
            },
            maker_fee_rate: None,
            taker_fee_rate,
        },
        position_size_signed: 0.0,
        open_order_count: 0,
    }
}

fn crypto_book() -> CohortBookSnapshot {
    CohortBookSnapshot {
        symbol: "BTC".into(),
        source: "hyperliquid_mainnet_l2_rest".into(),
        exchange_ts_ms: 1_786_041_106_711,
        recv_ts_ms: 1_786_041_106_800,
        mid_px: 64_000.5,
        spread_bps: 0.156,
        bid_depth_ratio: 1.2,
        opi: 0.1,
        bids: (0_u32..8)
            .map(|index| CohortBookLevel {
                price: 64_000.0 - f64::from(index),
                size: f64::from(index + 1),
                orders: Some(u64::from(index + 1)),
            })
            .collect(),
        asks: (0_u32..8)
            .map(|index| CohortBookLevel {
                price: 64_001.0 + f64::from(index),
                size: f64::from(index + 1),
                orders: Some(u64::from(index + 1)),
            })
            .collect(),
    }
}
