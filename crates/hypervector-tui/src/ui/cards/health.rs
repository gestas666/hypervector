//! Honesty / health footer.

use ratatui::layout::Rect;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, BorderType, Paragraph};
use ratatui::Frame;

use crate::model::{AppSnapshot, CardId};
use crate::theme::Theme;

pub fn render(frame: &mut Frame, area: Rect, snap: &AppSnapshot, theme: &Theme, focused: bool) {
    let h = &snap.health;
    let border = theme.card_border(focused);
    let title = theme.title_style(focused);
    let muted = theme.muted_style();
    let fg = theme.fg_style();

    let age = h.age_secs();
    let age_style = if age > 10 {
        fg.fg(theme.warning)
    } else {
        muted
    };

    let mut parts = vec![
        Span::styled("honesty ", muted),
        Span::styled(
            if h.paper_no_submit {
                "paper_no_submit"
            } else {
                "paper_submit?"
            },
            if h.paper_no_submit {
                fg.fg(theme.positive)
            } else {
                fg.fg(theme.negative)
            },
        ),
        Span::styled(" · ", muted),
        Span::styled(
            if h.live_fail_closed {
                "live_fail_closed"
            } else {
                "live_open?"
            },
            if h.live_fail_closed {
                fg.fg(theme.positive)
            } else {
                fg.fg(theme.warning)
            },
        ),
        Span::styled(" · ", muted),
        Span::styled(format!("refresh {age}s"), age_style),
        Span::styled(" · ", muted),
        Span::styled("keys: Tab focus · Enter expand · Esc floor · r refresh · R regime · p/l/a tape · ? help · q quit", muted),
    ];

    if let Some(ref err) = h.last_error {
        parts.push(Span::styled(" · ", muted));
        parts.push(Span::styled(
            format!("err: {err}"),
            fg.fg(theme.negative),
        ));
    }

    if h.refreshing || h.regime_refreshing {
        parts.push(Span::styled(" · ", muted));
        parts.push(Span::styled("⟳", fg.fg(theme.accent)));
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} ", CardId::Health.title()),
            title,
        ));

    frame.render_widget(
        Paragraph::new(Line::from(parts)).block(block),
        area,
    );
}
