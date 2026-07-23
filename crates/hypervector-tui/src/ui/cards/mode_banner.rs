//! Full-width execution mode banner (always visible, no scroll).

use ratatui::layout::Rect;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

use crate::model::AppSnapshot;
use crate::theme::{ExecMode, Theme};

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme) {
    let mode = snap.exec_mode;
    let network = snap.status.network();
    let tape = match snap.tape_source {
        crate::cli_args::TapeMode::Paper => "tape:paper",
        crate::cli_args::TapeMode::Live => "tape:live",
        crate::cli_args::TapeMode::Auto => "tape:auto",
    };

    let mode_label = mode.as_str();
    let left = format!("  MODE: {mode_label}  ·  {network}  ·  {tape}  ");
    let right = "  hypervector-tui  ·  READ-ONLY  ";

    let style = theme.banner_style(mode);
    let muted = theme.muted_style();

    let danger = if mode == ExecMode::Live {
        Span::styled(" ⚠ LIVE — no arm from TUI ", style)
    } else {
        Span::styled(" monitor only ", muted)
    };

    let line = Line::from(vec![
        Span::styled(left, style),
        danger,
        Span::styled(right, muted),
    ]);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(style)
        .title(Span::styled(" EXECUTION ", style));

    frame.render_widget(Paragraph::new(line).block(block).style(style), area);
}
