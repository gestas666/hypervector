//! Synthetic depth acceptance: clocks, exact levels, viewport and identity changes.

use std::collections::BTreeSet;

use hypervector_tui::{
    App,
    backend_cohort::{CohortBookLevel, CohortBookSnapshot},
};
use ratatui::{Terminal, backend::TestBackend};

const SIZES: [(u16, u16); 3] = [(120, 36), (190, 52), (100, 28)];
const SYNTHETIC_2030_MS: u64 = 1_893_510_600_000;

fn book(symbol: &str) -> CohortBookSnapshot {
    let levels = |bid: bool| {
        (0..20)
            .map(|index| CohortBookLevel {
                price: if bid {
                    100.0 - index as f64
                } else {
                    101.0 + index as f64
                },
                size: (index + 1) as f64,
                orders: Some((index + 1) as u64),
            })
            .collect()
    };
    CohortBookSnapshot {
        symbol: symbol.into(),
        source: "hyperliquid_mainnet_l2_rest".into(),
        exchange_ts_ms: SYNTHETIC_2030_MS,
        recv_ts_ms: SYNTHETIC_2030_MS + 2_374,
        mid_px: 100.5,
        spread_bps: 1.0 / 100.5 * 10_000.0,
        bid_depth_ratio: 1.0,
        opi: 0.0,
        bids: levels(true),
        asks: levels(false),
    }
}

fn app() -> App {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.backend.strategy_name = Some("multi_asset_bidirectional_cohort".into());
    app.backend.cohort.enabled_symbols = vec!["BTC".into(), "ETH".into()];
    for symbol in ["BTC", "ETH"] {
        app.backend.cohort.books.insert(symbol.into(), book(symbol));
    }
    app.backend.cohort_checkpoint.configured = true;
    app.backend.cohort_checkpoint.available = true;
    app.backend.cohort_checkpoint.stale = true;
    app.backend.cohort_checkpoint.publication_stale = true;
    app.active_tab = 3;
    app
}

fn render(app: &App, width: u16, height: u16) -> String {
    let mut terminal = Terminal::new(TestBackend::new(width, height)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .expect("render depth");
    let buffer = terminal.backend().buffer();
    (0..height)
        .map(|y| {
            (0..width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn depth_rows(screen: &str) -> Vec<Vec<String>> {
    screen
        .lines()
        .flat_map(|line| line.split('│'))
        .map(|cell| {
            cell.split_whitespace()
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .filter(|row| {
            row.len() == 6 && row[0].parse::<usize>().is_ok() && row[1].parse::<f64>().is_ok()
        })
        .collect()
}

#[test]
fn freshness_date_and_receive_delay_remain_visible_at_all_sizes() {
    for (width, height) in SIZES {
        let screen = render(&app(), width, height);
        for label in [
            "BACKEND L2 SNAPSHOT",
            "BOOK AGE",
            "CHECKPOINT STALE",
            "2030-01-01",
            "RECEIVE DELTA 2374ms",
            "MAINNET",
        ] {
            assert!(
                screen.contains(label),
                "{width}x{height} missing {label}\n{screen}"
            );
        }
        assert!(!screen.contains("LIVE HYPERLIQUID L2"));
    }
}

#[test]
fn scrolling_exposes_every_source_level_with_correct_cumulative_and_full_totals() {
    for (width, height) in SIZES {
        let mut app = app();
        let mut prices = BTreeSet::new();
        for _ in 0..21 {
            let screen = render(&app, width, height);
            assert!(screen.contains("TOTAL ALL"));
            assert!(screen.contains("210.00000"));
            for row in depth_rows(&screen) {
                let rank = row[0].parse::<usize>().expect("rank");
                assert_eq!(row[2], format!("{:.5}", rank as f64));
                assert_eq!(row[3], format!("{:.5}", (rank * (rank + 1) / 2) as f64));
                assert_eq!(row[4], rank.to_string());
                prices.insert(format!("{:.8}", row[1].parse::<f64>().expect("exact price")));
            }
            app.move_cohort_depth(1);
        }
        let expected = (81..=120)
            .map(|price| format!("{:.8}", price as f64))
            .collect();
        assert_eq!(
            prices, expected,
            "unreachable source levels at {width}x{height}"
        );
    }
}

#[test]
fn asset_changes_reset_depth_and_boundaries_do_not_erase_scroll_position() {
    let mut app = app();
    render(&app, 100, 28);
    app.move_cohort_depth(isize::MAX);
    assert!(render(&app, 100, 28).contains("LEVELS 20-20 / 20"));
    app.move_cohort_symbol(1);
    let changed = render(&app, 100, 28);
    assert!(changed.contains("ETH  MID"));
    assert!(changed.contains("LEVELS 1-1 / 20"));
    app.move_cohort_depth(isize::MAX);
    app.move_cohort_symbol(1);
    assert!(render(&app, 100, 28).contains("LEVELS 20-20 / 20"));
}

#[test]
fn resize_and_unequal_book_shrink_show_available_ranges_without_invented_rows() {
    let mut app = app();
    render(&app, 100, 28);
    app.move_cohort_depth(isize::MAX);
    assert!(render(&app, 190, 52).contains("LEVELS 5-20 / 20"));
    let book = app.backend.cohort.books.get_mut("BTC").expect("book");
    book.bids.truncate(2);
    book.asks.truncate(5);
    let shrunk = render(&app, 100, 28);
    assert!(shrunk.contains("BID DEPTH // LEVELS NONE / 2"));
    assert!(shrunk.contains("ASK DEPTH // LEVELS 5-5 / 5"));
    assert_eq!(depth_rows(&shrunk).len(), 1);
    app.move_cohort_depth(isize::MIN);
    assert!(render(&app, 100, 28).contains("BID DEPTH // LEVELS 1-1 / 2"));
}

#[test]
fn page_keys_move_by_visible_capacity_and_return_to_top() {
    let mut app = app();
    render(&app, 120, 36);
    app.page_cohort_depth(1);
    assert!(render(&app, 120, 36).contains("LEVELS 10-18 / 20"));
    app.page_cohort_depth(1);
    assert!(render(&app, 120, 36).contains("LEVELS 12-20 / 20"));
    app.page_cohort_depth(-1);
    assert!(render(&app, 120, 36).contains("LEVELS 3-11 / 20"));
    app.page_cohort_depth(-1);
    assert!(render(&app, 120, 36).contains("LEVELS 1-9 / 20"));
}

#[test]
fn unavailable_book_and_checkpoint_states_are_named_separately() {
    let mut app = app();
    app.backend.cohort_checkpoint.available = false;
    assert!(render(&app, 120, 36).contains("CHECKPOINT UNAVAILABLE"));
    app.backend.cohort_checkpoint.configured = false;
    assert!(render(&app, 120, 36).contains("CHECKPOINT NOT CONFIGURED"));
    app.backend.cohort_checkpoint.configured = true;
    app.backend.cohort_checkpoint.available = true;
    app.backend.cohort_checkpoint.publication_stale = false;
    assert!(render(&app, 120, 36).contains("CHECKPOINT SOURCE ISSUE"));
    app.backend.cohort_checkpoint.stale = false;
    assert!(render(&app, 120, 36).contains("CHECKPOINT FRESH"));
    app.backend.cohort.books.clear();
    assert!(render(&app, 120, 36).contains("BTC depth unavailable"));
    app.backend.cohort.enabled_symbols.clear();
    app.move_cohort_symbol(1);
    assert!(render(&app, 120, 36).contains("No enabled market reported"));
}
