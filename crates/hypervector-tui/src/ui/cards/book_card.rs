//! BOOK card — equity, position, realized/unrealized from paper ledger.

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
    let book = &snap.book;

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border)
        .title(Span::styled(
            format!(" {} ", CardId::Book.title()),
            title,
        ));
    let inner = block.inner(area);
    frame.render_widget(block, area);
    if inner.height == 0 || inner.width == 0 {
        return;
    }

    if !book.has_book {
        frame.render_widget(
            Paragraph::new(vec![
                Line::from(Span::styled(
                    "no paper session book yet",
                    theme.muted_style(),
                )),
                Line::from(Span::styled(
                    "start a paper/shadow session — ledger writes position/equity",
                    theme.muted_style(),
                )),
            ]),
            inner,
        );
        return;
    }

    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(if inner.height >= 9 { 3 } else { 1 }),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Length(1),
            Constraint::Min(2),
        ])
        .split(inner);

    // Hero: equity
    let equity_txt = format!("{:.0}", book.equity);
    let eq_style = theme.signed_style(book.total_pnl);
    if rows[0].height >= 3 && rows[0].width >= 14 {
        let big = BigText::builder()
            .pixel_size(PixelSize::Quadrant)
            .style(eq_style.add_modifier(Modifier::BOLD))
            .lines(vec![equity_txt.clone().into()])
            .build();
        frame.render_widget(big, rows[0]);
    } else {
        frame.render_widget(
            Paragraph::new(Line::from(vec![
                Span::styled("equity ", theme.muted_style()),
                Span::styled(equity_txt, eq_style.add_modifier(Modifier::BOLD)),
            ])),
            rows[0],
        );
    }

    // Strategy / symbol / mode
    frame.render_widget(
        Paragraph::new(Span::styled(
            format!(
                "{}  {}  {}",
                book.strategy_name, book.symbol, book.execution_mode
            ),
            theme.muted_style(),
        )),
        rows[1],
    );

    // Position line
    let pos_style = if book.flat {
        theme.muted_style()
    } else if book.position_qty > 0.0 {
        Style::default().fg(theme.positive)
    } else {
        Style::default().fg(theme.negative)
    };
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(format!("{} ", book.side_label), pos_style.add_modifier(Modifier::BOLD)),
            Span::styled(
                format!(
                    "qty={:.4}  avg={:.2}  mark={:.2}",
                    book.position_qty, book.position_avg_px, book.mark_px
                ),
                theme.fg_style(),
            ),
        ])),
        rows[2],
    );

    // PnL line
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled("uPnL ", theme.muted_style()),
            Span::styled(
                format!("{:+.2}", book.unrealized_pnl),
                theme.signed_style(book.unrealized_pnl),
            ),
            Span::styled("  rPnL ", theme.muted_style()),
            Span::styled(
                format!("{:+.2}", book.realized_pnl),
                theme.signed_style(book.realized_pnl),
            ),
            Span::styled("  total ", theme.muted_style()),
            Span::styled(
                format!("{:+.2}", book.total_pnl),
                theme.signed_style(book.total_pnl),
            ),
        ])),
        rows[3],
    );

    // Equity sparkline + price sparkline
    if rows[4].height >= 1 {
        let split = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(55), Constraint::Percentage(45)])
            .split(rows[4]);
        let eq_data = if book.equity_spark.is_empty() {
            vec![0]
        } else {
            book.equity_spark.clone()
        };
        let px_data = if snap.series.mark_px.is_empty() {
            vec![0]
        } else {
            snap.series.mark_px.clone()
        };
        frame.render_widget(
            Sparkline::default()
                .data(&eq_data)
                .style(Style::default().fg(theme.accent)),
            split[0],
        );
        frame.render_widget(
            Sparkline::default()
                .data(&px_data)
                .style(Style::default().fg(theme.warning)),
            split[1],
        );
    }
}

pub fn focus_lines(snap: &AppSnapshot, theme: &Theme) -> Vec<Line<'static>> {
    let b = &snap.book;
    let fg = theme.fg_style();
    let muted = theme.muted_style();
    if !b.has_book {
        return vec![
            Line::from(Span::styled("no book fields on ledger", muted)),
            Line::from(Span::styled(
                "session ledger must include position_qty/equity on decisions.jsonl",
                muted,
            )),
        ];
    }
    vec![
        Line::from(Span::styled(
            format!("strategy: {}  symbol: {}", b.strategy_name, b.symbol),
            fg,
        )),
        Line::from(Span::styled(
            format!("mode: {}  side: {}", b.execution_mode, b.side_label),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "position_qty={:.6}  avg={:.4}  mark={:.4}",
                b.position_qty, b.position_avg_px, b.mark_px
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "equity={:.4}  init_cash={:.4}  total_pnl={:+.4}",
                b.equity, b.init_cash, b.total_pnl
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!(
                "unrealized={:+.4}  realized={:+.4}",
                b.unrealized_pnl, b.realized_pnl
            ),
            fg,
        )),
        Line::from(Span::styled(
            format!("equity_points={}", b.equity_series.len()),
            muted,
        )),
    ]
}
