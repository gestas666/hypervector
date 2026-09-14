//! Actual offline Python runner output must survive cohort parsing and compact rendering.

use hypervector_tui::{App, backend_telemetry::parse_backend_telemetry};
use ratatui::{Terminal, backend::TestBackend};
use serde_json::Value;

const CASES: [(&str, bool); 4] = [
    (
        include_str!("fixtures/native_runner_shared_cleanup/full_first.jsonl"),
        false,
    ),
    (
        include_str!("fixtures/native_runner_shared_cleanup/full_last.jsonl"),
        false,
    ),
    (
        include_str!("fixtures/native_runner_shared_cleanup/partial_first.jsonl"),
        true,
    ),
    (
        include_str!("fixtures/native_runner_shared_cleanup/partial_last.jsonl"),
        true,
    ),
];

#[test]
fn native_shared_account_and_owned_lifecycle_fields_survive_projection() {
    for (input, partial) in CASES {
        let backend = parse_backend_telemetry(input).expect("native cohort ledger must parse");
        let raw = source_snapshot(input);
        let account = backend.cohort.account.as_ref().expect("shared account");
        assert_eq!(backend.cohort.assets.len(), 7);
        assert_eq!(account.open_position_count, if partial { 7 } else { 0 });
        assert_eq!(
            account.account_value_usd,
            raw["account_value_usd"].as_f64().unwrap()
        );
        assert_eq!(
            account.total_notional_position_usd,
            raw["total_notional_position_usd"].as_f64().unwrap()
        );
        assert!(
            !backend.cohort.evaluations.is_empty(),
            "native provider context was lost"
        );
        for (asset, expected) in backend
            .cohort
            .assets
            .iter()
            .zip(raw["assets"].as_array().unwrap())
        {
            assert_eq!(asset.symbol, expected["symbol"].as_str().unwrap());
            assert_eq!(
                asset.position_size_signed,
                expected["position_size_signed"].as_f64().unwrap()
            );
            assert_eq!(asset.fees_net_usd, expected["fees_net_usd"].as_f64());
            assert_eq!(
                asset.realized_pnl_usd,
                expected["realized_pnl_usd"].as_f64()
            );
            assert_eq!(asset.opened_at_ms, expected["opened_at_ms"].as_i64());
            assert_eq!(asset.protective_exit_pending, Some(partial));
            assert_eq!(
                asset.stop_protection.as_deref(),
                Some(if partial { "missing" } else { "flat" })
            );
        }
    }
}

#[test]
fn native_pending_exit_and_original_clock_remain_visible_for_each_selected_asset() {
    for (input, partial) in CASES {
        let backend = parse_backend_telemetry(input).expect("native cohort ledger must parse");
        let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        app.apply_backend_telemetry(backend);
        for selected in 0..7 {
            app.selected_cohort_symbol_index = selected;
            for (width, height) in [(100, 28), (120, 36), (190, 52)] {
                let screen = render(&mut app, 0, width, height);
                for asset in &app.backend.cohort.assets {
                    assert!(
                        screen.contains(&asset.symbol),
                        "missing {}\n{screen}",
                        asset.symbol
                    );
                }
                if partial {
                    let asset = &app.backend.cohort.assets[selected];
                    let opened =
                        chrono::DateTime::from_timestamp_millis(asset.opened_at_ms.unwrap())
                            .unwrap();
                    let clock = opened.format("OPENED %m-%d %H:%M:%SZ").to_string();
                    assert!(screen.contains(&clock), "{screen}");
                    assert!(screen.contains("PARTIAL "), "{screen}");
                    assert!(screen.contains("EXIT DUE / NO STOP"), "{screen}");
                } else {
                    assert!(!screen.contains("EXIT DUE / NO STOP"), "{screen}");
                }
                let orders = render(&mut app, 4, width, height);
                assert_eq!(orders.contains("EXIT DUE / NO STOP"), partial, "{orders}");
            }
        }
    }
}

fn source_snapshot(input: &str) -> Value {
    input
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).unwrap())
        .find(|row| row["event_type"] == "cohort_snapshot")
        .expect("native snapshot")["payload"]
        .clone()
}

fn render(app: &mut App, tab: usize, width: u16, height: u16) -> String {
    app.active_tab = tab;
    let mut terminal = Terminal::new(TestBackend::new(width, height)).unwrap();
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, app))
        .unwrap();
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
