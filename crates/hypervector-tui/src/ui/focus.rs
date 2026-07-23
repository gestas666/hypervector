//! Card Focus — second view only (Esc → Floor).

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Paragraph, Table, TableState};
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId};
use crate::theme::Theme;
use crate::ui::cards::{book_card, gates, regime, tape};

pub fn render_focus(
    frame: &mut Frame,
    area: Rect,
    snap: &AppSnapshot,
    theme: &Theme,
    card: CardId,
    tape_state: &mut TableState,
) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(3)])
        .split(area);

    // Mini mode banner so mode stays obvious in focus view.
    crate::ui::cards::mode_banner::render(frame, chunks[0], snap, theme);

    let title = format!(
        " FOCUS · {} · Esc=floor ",
        card.title()
    );
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(theme.card_border(true))
        .title(Span::styled(
            title,
            theme
                .title_style(true)
                .add_modifier(Modifier::BOLD),
        ));

    let inner = block.inner(chunks[1]);
    frame.render_widget(block, chunks[1]);

    match card {
        CardId::Regime => {
            let lines = regime::metrics_lines(&snap.regime, theme);
            frame.render_widget(Paragraph::new(lines), inner);
        }
        CardId::Tape => {
            let (header, rows, widths) = tape::focus_table(&snap.decisions, theme);
            if rows.is_empty() {
                frame.render_widget(
                    Paragraph::new(Span::styled(
                        "empty tape",
                        theme.muted_style(),
                    )),
                    inner,
                );
            } else {
                let table = Table::new(rows, widths)
                    .header(header)
                    .row_highlight_style(
                        Style::default()
                            .fg(theme.fg)
                            .bg(theme.border)
                            .add_modifier(Modifier::BOLD),
                    )
                    .highlight_symbol("▸ ");
                frame.render_stateful_widget(table, inner, tape_state);
            }
        }
        CardId::Gates | CardId::Mode => {
            let lines = gates::checklist_lines(snap, theme);
            frame.render_widget(Paragraph::new(lines), inner);
        }
        CardId::Book => {
            let lines = book_card::focus_lines(snap, theme);
            frame.render_widget(Paragraph::new(lines), inner);
        }
        CardId::Health => {
            let h = &snap.health;
            let lines = vec![
                Line::from(format!("refresh_age_s: {}", h.age_secs())),
                Line::from(format!("paper_no_submit: {}", h.paper_no_submit)),
                Line::from(format!("live_fail_closed: {}", h.live_fail_closed)),
                Line::from(format!(
                    "secrets_never_printed: {}",
                    h.secrets_never_printed
                )),
                Line::from(format!(
                    "last_error: {}",
                    h.last_error.as_deref().unwrap_or("—")
                )),
            ];
            frame.render_widget(Paragraph::new(lines), inner);
        }
    }
}
