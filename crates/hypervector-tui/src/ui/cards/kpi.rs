//! KPI strip — big-text primary metric + sparklines (tickrs-inspired density).

use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Gauge, Paragraph, Sparkline};
use ratatui::Frame;
use tui_big_text::{BigText, PixelSize};

use crate::model::{AppSnapshot, CardId};
use crate::theme::Theme;

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme, focused: bool) {
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);
    let agg = &snap.tape_agg;
    let max_n = snap.status.max_notional_usd().max(1.0);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(format!(" {} ", CardId::Kpi.title()), title));

    let inner = block.inner(area);
    frame.render_widget(block, area);

    if inner.height == 0 || inner.width == 0 {
        return;
    }

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(if inner.height >= 6 { 3 } else { 1 }),
            Constraint::Length(1),
            Constraint::Min(1),
        ])
        .split(inner);

    // Primary metric: decision count
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
                        .add_modifier(ratatui::style::Modifier::BOLD),
                ),
            ])),
            rows[0],
        );
    }

    // Secondary line
    let sub = format!(
        "submitted={}  place_attempted={}  tape_rows={}",
        agg.submitted_count, agg.place_attempted_count, snap.decisions.len()
    );
    frame.render_widget(
        Paragraph::new(Span::styled(sub, theme.muted_style())),
        rows[1],
    );

    // Bottom: sparkline + notional gauge
    if rows[2].height >= 1 {
        let split = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(55), Constraint::Percentage(45)])
            .split(rows[2]);

        let data: Vec<u64> = if agg.buckets.is_empty() {
            vec![0]
        } else {
            agg.buckets.clone()
        };
        let spark = Sparkline::default()
            .data(&data)
            .style(Style::default().fg(theme.accent));
        frame.render_widget(spark, split[0]);

        // Notional utilization proxy: submitted share as soft gauge (not real exposure).
        let ratio = if agg.decision_count == 0 {
            0.0
        } else {
            (agg.submitted_count as f64 / agg.decision_count as f64).clamp(0.0, 1.0)
        };
        // Cap label shows max notional policy.
        let label = format!("max ${max_n:.0} · sub {:.0}%", ratio * 100.0);
        let gauge = Gauge::default()
            .gauge_style(Style::default().fg(if ratio > 0.5 {
                theme.gauge_warn
            } else {
                theme.gauge_ok
            }))
            .ratio(ratio)
            .label(label);
        frame.render_widget(gauge, split[1]);
    }
}
