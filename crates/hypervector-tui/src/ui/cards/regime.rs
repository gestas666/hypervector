//! Regime card — metrics only; no second detector.

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{BarChart, Block, Borders, BorderType, Paragraph};
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId, RegimeSnapshot};
use crate::theme::Theme;

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme, focused: bool) {
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);
    let r = &snap.regime;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} ", CardId::Regime.title()),
            title,
        ));
    let inner = block.inner(area);
    frame.render_widget(block, area);

    if !r.available {
        frame.render_widget(
            Paragraph::new(vec![
                Line::from(Span::styled(
                    "no regime metrics yet",
                    theme.muted_style(),
                )),
                Line::from(Span::styled(
                    "press R to run: hypervector regime (read-only)",
                    theme.muted_style(),
                )),
            ]),
            inner,
        );
        return;
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(2), Constraint::Min(3)])
        .split(inner);

    let dom_style = match r.dominant.as_str() {
        "up" => Style::default().fg(theme.positive),
        "down" => Style::default().fg(theme.negative),
        "range" => Style::default().fg(theme.warning),
        _ => theme.muted_style(),
    };

    let header = Line::from(vec![
        Span::styled("dominant ", theme.muted_style()),
        Span::styled(r.dominant.to_uppercase(), dom_style),
        Span::styled(
            format!(
                "  up {:.0}%  down {:.0}%  range {:.0}%",
                r.pct_up * 100.0,
                r.pct_down * 100.0,
                r.pct_range * 100.0
            ),
            theme.fg_style(),
        ),
    ]);
    let meta = Line::from(Span::styled(
        format!(
            "n_bars={}  flip_rate={:.3}  mean_dur={:.1}  R=refresh",
            r.n_bars, r.flip_rate, r.mean_duration
        ),
        theme.muted_style(),
    ));
    frame.render_widget(Paragraph::new(vec![header, meta]), chunks[0]);

    // BarChart expects (&str, u64) — use percent as integer.
    let up = (r.pct_up * 100.0).round() as u64;
    let down = (r.pct_down * 100.0).round() as u64;
    let range = (r.pct_range * 100.0).round() as u64;
    let data = [("up", up), ("dn", down), ("rg", range)];
    let chart = BarChart::default()
        .data(&data)
        .bar_width(3)
        .bar_gap(1)
        .bar_style(Style::default().fg(theme.accent))
        .value_style(Style::default().fg(theme.fg));
    frame.render_widget(chart, chunks[1]);
}

/// Full metrics table lines for focus view.
pub fn metrics_lines(r: &RegimeSnapshot, theme: &Theme) -> Vec<Line<'static>> {
    let fg = theme.fg;
    let muted = theme.muted;
    let row = |k: &str, v: String| {
        Line::from(vec![
            Span::styled(
                format!("{k:<16}"),
                Style::default().fg(muted),
            ),
            Span::styled(v, Style::default().fg(fg)),
        ])
    };
    vec![
        row("dominant", r.dominant.clone()),
        row("pct_up", format!("{:.4}", r.pct_up)),
        row("pct_down", format!("{:.4}", r.pct_down)),
        row("pct_range", format!("{:.4}", r.pct_range)),
        row("flip_rate", format!("{:.4}", r.flip_rate)),
        row("mean_duration", format!("{:.2}", r.mean_duration)),
        row("n_bars", format!("{}", r.n_bars)),
        row(
            "params",
            format!(
                "fast={:?} slow={:?}",
                r.params_fast, r.params_slow
            ),
        ),
        row(
            "age_secs",
            r.age_secs
                .map(|a| a.to_string())
                .unwrap_or_else(|| "—".into()),
        ),
        row(
            "available",
            r.available.to_string(),
        ),
    ]
}
