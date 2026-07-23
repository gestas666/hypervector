//! Decision tape table.

use ratatui::layout::{Constraint, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::Span;
use ratatui::widgets::{Block, Borders, BorderType, Cell, Row, Table, TableState};
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId, DecisionRow};
use crate::theme::Theme;

pub fn render(
    frame: &mut Frame,
    area: Rect,
    snap: &AppSnapshot,
    theme: &Theme,
    focused: bool,
    state: &mut TableState,
) {
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);

    let source = match snap.tape_source {
        crate::cli_args::TapeMode::Paper => "paper",
        crate::cli_args::TapeMode::Live => "live",
        crate::cli_args::TapeMode::Auto => "auto",
    };
    let path_hint = snap
        .tape_path
        .as_ref()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|| "—".into());

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} [{source}] ", CardId::Tape.title()),
            title,
        ))
        .title_bottom(Span::styled(
            format!(" {path_hint} "),
            theme.muted_style(),
        ));

    if snap.decisions.is_empty() {
        let empty = ratatui::widgets::Paragraph::new(Span::styled(
            "no decisions yet — empty ledger (designed empty state)",
            theme.muted_style(),
        ))
        .block(block);
        frame.render_widget(empty, area);
        return;
    }

    let header = Row::new(vec!["time", "mode", "action", "side", "sub", "px"])
        .style(
            Style::default()
                .fg(theme.muted)
                .add_modifier(Modifier::BOLD),
        )
        .height(1);

    let rows: Vec<Row> = snap
        .decisions
        .iter()
        .rev() // newest first on tape
        .map(|r| row_from_decision(r, theme))
        .collect();

    let widths = [
        Constraint::Percentage(28),
        Constraint::Percentage(12),
        Constraint::Percentage(16),
        Constraint::Percentage(12),
        Constraint::Percentage(10),
        Constraint::Percentage(22),
    ];

    let table = Table::new(rows, widths)
        .header(header)
        .block(block)
        .row_highlight_style(
            Style::default()
                .fg(theme.fg)
                .bg(theme.border)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol("▸ ");

    frame.render_stateful_widget(table, area, state);
}

fn row_from_decision(r: &DecisionRow, theme: &Theme) -> Row<'static> {
    let mode = r.mode_str().to_string();
    let mode_style = match mode.as_str() {
        "live" => Style::default().fg(theme.mode_live).bg(theme.mode_live_bg),
        "paper" => Style::default().fg(theme.mode_paper),
        "shadow" => Style::default().fg(theme.mode_shadow),
        _ => Style::default().fg(theme.muted),
    };
    let px = r
        .fill_px
        .or(r.mark_px)
        .map(|p| format!("{p:.2}"))
        .unwrap_or_else(|| "—".into());

    Row::new(vec![
        Cell::from(truncate(&r.timestamp_display(), 22)),
        Cell::from(mode).style(mode_style),
        Cell::from(r.action_str().to_string()),
        Cell::from(r.side.clone().unwrap_or_else(|| "—".into())),
        Cell::from(r.submitted_str().to_string()),
        Cell::from(px),
    ])
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        s.to_string()
    } else {
        format!("{}…", &s[..max.saturating_sub(1)])
    }
}

pub fn focus_table<'a>(
    decisions: &'a [DecisionRow],
    theme: &'a Theme,
) -> (Row<'static>, Vec<Row<'static>>, [Constraint; 6]) {
    let header = Row::new(vec!["time", "mode", "action", "side", "sub", "px"])
        .style(
            Style::default()
                .fg(theme.muted)
                .add_modifier(Modifier::BOLD),
        );
    let rows: Vec<Row> = decisions
        .iter()
        .rev()
        .map(|r| row_from_decision(r, theme))
        .collect();
    let widths = [
        Constraint::Percentage(28),
        Constraint::Percentage(12),
        Constraint::Percentage(16),
        Constraint::Percentage(12),
        Constraint::Percentage(10),
        Constraint::Percentage(22),
    ];
    (header, rows, widths)
}
