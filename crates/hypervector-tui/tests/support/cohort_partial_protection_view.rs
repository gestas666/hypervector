fn partial_protection_app(coverage: &str, pending: bool) -> App {
    let mut app = complete_portfolio_app();
    let mut raw = asset_snapshot("BTC", 100.0);
    raw["state"] = json!(if pending { "EXIT_PENDING" } else { "OPEN" });
    raw["opened_at_ms"] = json!(1785599700000_u64);
    raw["protective_exit_pending"] = json!(pending);
    raw["partial_exit_fill_count"] = json!(2);
    raw["partial_exit_size"] = json!(0.25);
    raw["stop_protection"] = json!(coverage);
    app.backend.cohort.assets[0] = serde_json::from_value(raw).unwrap();
    app
}

#[test]
fn partial_protection_missing_stop_never_renders_saved_oid_as_coverage() {
    let mut app = partial_protection_app("missing", true);
    for (width, height) in [(100, 28), (120, 36), (190, 52)] {
        for tab in [0, 4] {
            let screen = render(&mut app, tab, width, height);
            assert!(screen.contains("EXIT DUE / NO STOP"), "{screen}");
            let btc = screen
                .lines()
                .find(|line| line.contains("BTC") && line.contains("LONG"))
                .expect("BTC position row must remain visible");
            assert!(!btc.contains("S12/T13"), "{screen}");
            assert!(!btc.contains("STOP #12"), "{screen}");
        }
    }
}

#[test]
fn partial_protection_minimum_view_keeps_original_clock_and_partial_receipts() {
    let mut app = partial_protection_app("covering", false);
    let screen = render(&mut app, 0, 100, 28);
    for required in ["PARTIAL 2/0.25000", "OPENED 08-01 15:55:00Z", "STATE OPEN"] {
        assert!(screen.contains(required), "missing {required}\n{screen}");
    }
    for symbol in COMPLETE_SYMBOLS {
        assert!(screen.contains(symbol), "missing {symbol}\n{screen}");
    }
}

#[test]
fn partial_protection_full_portfolio_keeps_selected_receipts_visible() {
    let mut app = partial_protection_app("covering", false);
    for (width, height) in [(120, 36), (190, 52)] {
        let screen = render(&mut app, 0, width, height);
        for required in ["PARTIAL 2/0.25000", "OPENED 08-01 15:55:00Z"] {
            assert!(screen.contains(required), "missing {required}\n{screen}");
        }
    }
}
