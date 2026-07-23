//! KPI / charts strip — decisions, action mix, price & equity sparklines.

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Paragraph, Sparkline};
use ratatui::Frame;
use tui_big_text::{BigText, PixelSize};

use crate::model::{AppSnapshot, CardId};
use crate::theme::Theme;

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme, focused: bool) {
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);
    let agg = &snap.tape_agg;
    let series = &snap.series;
    let mix = &series.action_mix;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} · CHARTS ", CardId::Kpi.title()),
            title,
        ));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    if inner.height == 0 || inner.width == 0 {
        return;
    }

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(if inner.height >= 8 { 3 } else { 1 }),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Min(2),
        ])
        .split(inner);

    let primary = format!("{}", agg.decision_count);
    if rows[0].height >= 3 && rows[0].width >= 12 {
        let big = BigText::builder()
            .pixel_size(PixelSize::Quadrant)
            .style(Style::default().fg(theme.accent))
            .lines(vec![primary.clone().into()])
            .build();
        frame.render_widget(big, rows[0]);
    } else {
        frame.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled("decisions ", theme.muted_style()),
                Span::styled(
                    primary,
                    Style::default()
                        .fg(theme.accent)
                        .add_modifier(Modifier::BOLD),
                ),
            ])),
            rows[0],
        );
    }

    let mark = series
        .last_mark
        .map(|m| format!("{m:.2}"))
        .unwrap_or_else(|| "—".into());
    let eq = series
        .last_equity
        .map(|e| format!("eq≈{e:.0}"))
        .unwrap_or_else(|| "eq=—".into());
    let mix_line = format!(
        "buy={} sell={} hold={}  mark={}  {eq}  sub={}/{}",
        mix.buy,
        mix.sell,
        mix.hold,
        mark,
        agg.submitted_count,
        agg.decision_count
    );
    frame.render_widget(
        Paragraph::new(Span::styled(mix_line, theme.muted_style())),
        rows[1],
    );

    frame.render_widget(
        Paragraph::new(Span::styled(
            "px spark · activity · equity(derived)",
            theme.muted_style(),
        )),
        rows[2],
    );

    if rows[3].height >= 1 {
        let split = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(40),
                Constraint::Percentage(30),
                Constraint::Percentage(30),
            ])
            .split(rows[3]);

        let price_data: Vec<u64> = if series.mark_px.is_empty() {
            if series.fill_px.is_empty() {
                vec![0]
            } else {
                series.fill_px.clone()
            }
        } else {
            series.mark_px.clone()
        };
        let act_data: Vec<u64> = if series.activity.is_empty() {
            vec![0]
        } else {
            series.activity.clone()
        };
        let eq_data: Vec<u64> = if series.equity.is_empty() {
            vec![0]
        } else {
            series.equity.clone()
        };

        frame.render_widget(
            Sparkline::default()
                .data(&price_data)
                .style(Style::default().fg(theme.accent)),
            split[0],
        );
        frame.render_widget(
            Sparkline::default()
                .data(&act_data)
                .style(Style::default().fg(theme.positive)),
            split[1],
        );
        frame.render_widget(
            Sparkline::default()
                .data(&eq_data)
                .style(Style::default().fg(theme.warning)),
            split[2],
        );
    }
}

pub fn focus_lines(snap: &AppSnapshot, theme: &Theme) -> Vec<Line<'static>> {
    let a = &snap.tape_agg;
    let s = &snap.series;
    let m = &s.action_mix;
    let fg = theme.fg_style();
    let muted = theme.muted_style();
    vec![
        Line::from(Span::styled(
            format!("decisions: {}", a.decision_count),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "actions: buy={} sell={} hold={} other={}",
                m.buy, m.sell, m.hold, m.other
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "submitted={}  place_attempted={}",
                a.submitted_count, a.place_attempted_count
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "last_mark={}  last_fill={}",
                s.last_mark
                    .map(|v| format!("{v:.4}"))
                    .unwrap_or_else(|| "—".into()),
                s.last_fill
                    .map(|v| format!("{v:.4}"))
                    .unwrap_or_else(|| "—".into())
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "derived_equity={}  (shadow sketch, not venue PnL)",
                s.last_equity
                    .map(|v| format!("{v:.2}"))
                    .unwrap_or_else(|| "—".into())
            ),
            muted,
        )),
        Line::from(Span::styled(
            format!(
                "series lens: mark_pts={} fill_pts={} equity_pts={}",
                s.mark_px.len(),
                s.fill_px.len(),
                s.equity.len()
            ),
            muted,
        )),
    ]
}
