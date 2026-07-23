//! Readiness / gates card — paper green path vs live refused (bools only).

use ratatui::layout::Rect;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Paragraph};
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId, LiveState};
use crate::theme::Theme;

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme, focused: bool) {
    let g = &snap.gates;
    let s = &snap.status;
    let r = &snap.readiness;
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);
    let fg = theme.fg_style();
    let muted = theme.muted_style();
    let ok = theme.positive;
    let bad = theme.negative;

    let mut lines: Vec<Line> = Vec::new();

    if !r.layout_ok && !g.layout_ok {
        lines.push(Line::from(Span::styled(
            "no layout — run: hypervector infra-init",
            theme.muted_style().fg(theme.warning),
        )));
        lines.push(Line::from(Span::styled(
            format!("data-root: {}", snap.data_root.display()),
            muted,
        )));
    } else {
        let ready_label = if r.dry_run_ready {
            "DRY-RUN READY"
        } else {
            "DRY-RUN BLOCKED"
        };
        let ready_style = if r.dry_run_ready {
            fg.fg(ok)
        } else {
            fg.fg(theme.warning)
        };
        lines.push(Line::from(vec![
            Span::styled("status   ", muted),
            Span::styled(ready_label, ready_style),
            Span::styled("  ", muted),
            Span::styled(
                r.live_state.as_str(),
                match r.live_state {
                    LiveState::Refused => fg.fg(theme.warning),
                    LiveState::Ready => fg.fg(ok),
                    LiveState::Armed => fg.fg(theme.mode_live).bg(theme.mode_live_bg),
                },
            ),
        ]));
        lines.push(Line::from(vec![
            Span::styled("data     ", muted),
            Span::styled(snap.data_root.display().to_string(), fg),
        ]));

        lines.push(Line::from(Span::styled("— paper / shadow —", muted)));
        lines.push(Line::from(vec![
            Span::styled("mode     ", muted),
            Span::styled(
                if r.paper_mode.is_empty() {
                    "shadow".into()
                } else {
                    r.paper_mode.clone()
                },
                fg,
            ),
            Span::styled("  no_submit=", muted),
            bool_span(r.paper_no_submit || g.paper.no_submit || s.paper.no_submit, ok, bad),
        ]));
        lines.push(Line::from(vec![
            Span::styled("book     ", muted),
            bool_span(g.paper.book_feed, ok, bad),
            Span::styled("  l2_walk=", muted),
            bool_span(g.paper.l2_walk_available, ok, bad),
            Span::styled("  metalabel=", muted),
            bool_span(g.paper.metalabel_enabled, ok, bad),
        ]));

        lines.push(Line::from(Span::styled("— live (fail-closed) —", muted)));
        lines.push(Line::from(vec![
            Span::styled("enabled  ", muted),
            bool_span(g.live.enabled, ok, bad),
            Span::styled("  armed=", muted),
            bool_span(g.live.armed, ok, bad),
            Span::styled("  can_start=", muted),
            bool_span(g.live.can_start || s.live.can_start, ok, bad),
        ]));
        lines.push(Line::from(vec![
            Span::styled("wired    ", muted),
            bool_span(g.live.submit_wired || s.live.submit_wired, ok, bad),
            Span::styled(
                format!(
                    "  max=${:.0}",
                    if g.live.max_notional_usd > 0.0 {
                        g.live.max_notional_usd
                    } else {
                        s.max_notional_usd()
                    }
                ),
                fg,
            ),
            Span::styled("  secrets=", muted),
            bool_span(g.live.secrets_present || g.paper.secrets_present, ok, bad),
        ]));
        if !r.live_reason.is_empty() {
            let reason = if r.live_reason.len() > 64 {
                format!("{}…", &r.live_reason[..63])
            } else {
                r.live_reason.clone()
            };
            lines.push(Line::from(vec![
                Span::styled("reason   ", muted),
                Span::styled(reason, fg.fg(theme.warning)),
            ]));
        }
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} ", CardId::Gates.title()),
            title,
        ));

    frame.render_widget(Paragraph::new(lines).block(block), area);
}

fn bool_span(v: bool, ok: ratatui::style::Color, bad: ratatui::style::Color) -> Span<'static> {
    if v {
        Span::styled("true", ratatui::style::Style::default().fg(ok))
    } else {
        Span::styled("false", ratatui::style::Style::default().fg(bad))
    }
}

/// Full checklist for focus view.
pub fn checklist_lines(snap: &AppSnapshot, theme: &Theme) -> Vec<Line<'static>> {
    let g = &snap.gates;
    let s = &snap.status;
    let r = &snap.readiness;
    let muted = theme.muted;
    let fg = theme.fg;
    let ok = theme.positive;
    let bad = theme.negative;

    let items: Vec<(&str, bool)> = vec![
        ("dry_run_ready", r.dry_run_ready),
        ("paper.no_submit", g.paper.no_submit || s.paper.no_submit),
        ("paper.book_feed", g.paper.book_feed),
        ("paper.l2_walk", g.paper.l2_walk_available),
        ("live.submit_wired", g.live.submit_wired || s.live.submit_wired),
        ("live.enabled", g.live.enabled),
        ("live.armed", g.live.armed),
        ("live.can_start", g.live.can_start || s.live.can_start),
        (
            "live.secrets_present",
            g.live.secrets_present || g.paper.secrets_present,
        ),
        (
            "honesty.paper_never_exec_client",
            s.honesty.paper_never_constructs_exec_client,
        ),
        (
            "honesty.live_fail_closed",
            s.honesty.live_run_fail_closed,
        ),
        (
            "honesty.secrets_never_printed",
            s.honesty.secret_values_never_printed,
        ),
    ];

    items
        .into_iter()
        .map(|(name, val)| {
            let mark = if val { "[x]" } else { "[ ]" };
            Line::from(vec![
                Span::styled(
                    format!("{mark} "),
                    ratatui::style::Style::default().fg(if val { ok } else { bad }),
                ),
                Span::styled(name.to_string(), ratatui::style::Style::default().fg(fg)),
                Span::styled(
                    format!(" = {val}"),
                    ratatui::style::Style::default().fg(muted),
                ),
            ])
        })
        .collect()
}
