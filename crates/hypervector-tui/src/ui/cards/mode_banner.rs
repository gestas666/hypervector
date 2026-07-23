//! Full-width execution mode banner (always visible, no scroll).

use ratatui::layout::Rect;
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

use crate::model::{AppSnapshot, LiveState};
use crate::theme::{ExecMode, Theme};

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme) {
    let mode = snap.exec_mode;
    let network = if snap.readiness.network.is_empty() {
        snap.status.network()
    } else {
        snap.readiness.network.as_str()
    };
    let tape = match snap.tape_source {
        crate::cli_args::TapeMode::Paper => "tape:paper",
        crate::cli_args::TapeMode::Live => "tape:live",
        crate::cli_args::TapeMode::Auto => "tape:auto",
    };

    let mode_label = mode.as_str();
    let chip = snap.readiness.banner_chip(mode);
    let chip_style = match chip {
        "DRY-RUN READY" => Style::default()
            .fg(theme.positive)
            .add_modifier(Modifier::BOLD),
        "LIVE DANGER" | "LIVE ARMED" => Style::default()
            .fg(theme.mode_live)
            .bg(theme.mode_live_bg)
            .add_modifier(Modifier::BOLD),
        "LIVE REFUSED" => Style::default()
            .fg(theme.warning)
            .add_modifier(Modifier::BOLD),
        _ => theme.muted_style(),
    };

    let style = theme.banner_style(mode);
    let muted = theme.muted_style();

    let left = format!("  MODE: {mode_label}  ·  {network}  ·  {tape}  ");
    let mid = format!(" {chip} ");
    let right = "  hypervector-tui  ·  READ-ONLY  ";

    let mut spans = vec![
        Span::styled(left, style),
        Span::styled(mid, chip_style),
    ];

    if mode == ExecMode::Live || snap.readiness.live_state == LiveState::Armed {
        spans.push(Span::styled(" ⚠ no arm from TUI ", style));
    } else {
        spans.push(Span::styled(" monitor only ", muted));
    }
    spans.push(Span::styled(right, muted));

    let line = Line::from(spans);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(style)
        .title(Span::styled(" SHADOW OPS ", style));

    frame.render_widget(Paragraph::new(line).block(block).style(style), area);
}
