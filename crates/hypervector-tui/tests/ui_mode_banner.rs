//! UI unit: mode banner text present on floor render (TestBackend).

use std::path::PathBuf;

use hypervector_tui::cli_args::TapeMode;
use hypervector_tui::model::{AppSnapshot, CardId, RegimeSnapshot, StatusSnapshot};
use hypervector_tui::theme::{ExecMode, Theme};
use hypervector_tui::ui::render_floor;
use ratatui::backend::TestBackend;
use ratatui::widgets::TableState;
use ratatui::Terminal;

#[test]
fn floor_renders_mode_banner_shadow() {
    let backend = TestBackend::new(120, 40);
    let mut terminal = Terminal::new(backend).unwrap();
    let mut snap = AppSnapshot::cold(PathBuf::from("data"), TapeMode::Paper);
    snap.exec_mode = ExecMode::Shadow;
    snap.status = StatusSnapshot {
        ok: true,
        live: hypervector_tui::model::status::StatusLive {
            network: "mainnet".into(),
            max_notional_usd: 50.0,
            submit_wired: true,
            ..Default::default()
        },
        paper: hypervector_tui::model::status::StatusPaper {
            no_submit: true,
            default_mode: "shadow".into(),
        },
        ..Default::default()
    };
    snap.regime = RegimeSnapshot::empty_hint();
    let theme = Theme::ansi();
    let mut tape_state = TableState::default();

    terminal
        .draw(|f| {
            render_floor(f, f.area(), &snap, &theme, CardId::Gates, &mut tape_state);
        })
        .unwrap();

    let buffer = terminal.backend().buffer();
    let mut flat = String::new();
    for y in 0..buffer.area.height {
        for x in 0..buffer.area.width {
            flat.push_str(buffer[(x, y)].symbol());
        }
        flat.push('\n');
    }
    assert!(
        flat.contains("SHADOW") || flat.contains("MODE"),
        "mode banner missing from buffer:\n{flat}"
    );
    assert!(
        flat.contains("mainnet") || flat.contains("MAINNET") || flat.contains("mainnet"),
        "network missing"
    );
    assert!(flat.contains("GATES") || flat.contains("gates") || flat.contains("GATES"));
}

// Re-export status nested types for test — StatusLive is pub in status module.
// If private fields block, use Default + partial update already done above.
