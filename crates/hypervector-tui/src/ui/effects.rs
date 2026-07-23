//! Sparse effects hooks — skeleton / toast / help popup.
//!
//! Keep motion informative only (no rain/particles). Full tachyonfx is optional;
//! v1 uses lightweight state flags the floor already honors.

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Clear, Paragraph, Wrap};
use ratatui::Frame;

use crate::theme::Theme;

/// Centered help overlay (`?`).
pub fn render_help(frame: &mut Frame, area: Rect, theme: &Theme) {
    let popup = centered_rect(70, 60, area);
    frame.render_widget(Clear, popup);

    let text = vec![
        Line::from(Span::styled(
            "hypervector-tui — keys",
            Style::default()
                .fg(theme.accent)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from("  Tab / ← →     cycle focused card"),
        Line::from("  Enter         card focus view"),
        Line::from("  Esc           back to ops floor"),
        Line::from("  r             refresh status/gates/tape"),
        Line::from("  R             regime probe (read-only CLI)"),
        Line::from("  p / l / a     tape: paper / live / auto"),
        Line::from("  ?             this help"),
        Line::from("  q / Ctrl+C    quit (restores terminal)"),
        Line::from(""),
        Line::from(Span::styled(
            "Read-only: no paper-run / live-run / arm. No secrets on screen.",
            theme.muted_style(),
        )),
        Line::from(Span::styled(
            "Truth: data/paper · data/live + CLI JSON. Visual bar: tickrs density.",
            theme.muted_style(),
        )),
    ];

    let block = Block::default()
        .title(" HELP ")
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(theme.border_focus));

    frame.render_widget(
        Paragraph::new(text).block(block).wrap(Wrap { trim: false }),
        popup,
    );
}

/// Lightweight toast at bottom for non-secret errors.
pub fn render_toast(frame: &mut Frame, area: Rect, theme: &Theme, msg: &str) {
    let toast_area = Rect {
        x: area.x + 2,
        y: area.y + area.height.saturating_sub(4),
        width: area.width.saturating_sub(4),
        height: 3,
    };
    frame.render_widget(Clear, toast_area);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme.warning))
        .title(" toast ");
    frame.render_widget(
        Paragraph::new(Span::styled(msg.to_string(), Style::default().fg(theme.warning)))
            .block(block),
        toast_area,
    );
}

/// Skeleton placeholders while first load is in flight.
pub fn render_skeleton(frame: &mut Frame, area: Rect, theme: &Theme) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(theme.muted_style())
        .title(Span::styled(" loading… ", theme.muted_style()));
    frame.render_widget(
        Paragraph::new(Span::styled(
            "████  ████  ████    skeleton — awaiting CLI/ledger",
            theme.muted_style(),
        ))
        .block(block),
        area,
    );
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
