//! Decision tape table — ops-grade columns, newest first.

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
        .map(|p| shorten_path(&p.display().to_string(), 72))
        .unwrap_or_else(|| "—".into());

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(
                " {} [{source}] n={} ",
                CardId::Tape.title(),
                snap.decisions.len()
            ),
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

    let header = Row::new(vec![
        "time", "mode", "act", "side", "sub", "qty", "mark", "fill",
    ])
    .style(
        Style::default()
            .fg(theme.muted)
            .add_modifier(Modifier::BOLD),
    )
    .height(1);

    let rows: Vec<Row> = snap
        .decisions
        .iter()
        .rev()
        .map(|r| row_from_decision(r, theme))
        .collect();

    let widths = [
        Constraint::Length(20),
        Constraint::Length(7),
        Constraint::Length(5),
        Constraint::Length(5),
        Constraint::Length(3),
        Constraint::Length(7),
        Constraint::Length(10),
        Constraint::Length(10),
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
    let act = r.action_str().to_string();
    let act_style = match act.to_ascii_lowercase().as_str() {
        "buy" => Style::default().fg(theme.positive),
        "sell" => Style::default().fg(theme.negative),
        _ => Style::default().fg(theme.muted),
    };
    let qty = r
        .qty
        .map(|q| format!("{q:.4}"))
        .unwrap_or_else(|| "—".into());
    let mark = r
        .mark_px
        .map(|p| format!("{p:.2}"))
        .unwrap_or_else(|| "—".into());
    let fill = r
        .fill_px
        .map(|p| format!("{p:.2}"))
        .unwrap_or_else(|| "—".into());

    Row::new(vec![
        Cell::from(truncate(&r.timestamp_display(), 20)),
        Cell::from(truncate(&mode, 7)).style(mode_style),
        Cell::from(truncate(&act, 5)).style(act_style),
        Cell::from(truncate(
            &r.side.clone().unwrap_or_else(|| "—".into()),
            5,
        )),
        Cell::from(r.submitted_str().to_string()),
        Cell::from(qty),
        Cell::from(mark),
        Cell::from(fill),
    ])
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let t: String = s.chars().take(max.saturating_sub(1)).collect();
        format!("{t}…")
    }
}

fn shorten_path(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    if let Some(idx) = s.find("/paper/") {
        return format!("…{}", &s[idx..]);
    }
    if let Some(idx) = s.find("/live/") {
        return format!("…{}", &s[idx..]);
    }
    truncate(s, max)
}

pub fn focus_table<'a>(
    decisions: &'a [DecisionRow],
    theme: &'a Theme,
) -> (Row<'static>, Vec<Row<'static>>, [Constraint; 8]) {
    let header = Row::new(vec![
        "time", "mode", "act", "side", "sub", "qty", "mark", "fill",
    ])
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
        Constraint::Length(20),
        Constraint::Length(7),
        Constraint::Length(5),
        Constraint::Length(5),
        Constraint::Length(3),
        Constraint::Length(7),
        Constraint::Length(10),
        Constraint::Length(10),
    ];
    (header, rows, widths)
}
