//! Backend-authored market depth and order-flow workspace.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table, Tabs},
};

use crate::app::App;
use crate::backend_cohort::{CohortBookLevel, CohortBookSnapshot};
use crate::cohort_format::fill_time;
use crate::cohort_widgets::{page_label, panel, render_empty, selected_page};

const MARKET_TABS_PER_PAGE: usize = 4;
const FIXED_DEPTH_HEADER_HEIGHT: u16 = 8;
const COMPACT_LOWER_DECK_HEIGHT: u16 = 8;
const WIDE_LOWER_DECK_HEIGHT: u16 = 12;
const TALL_WIDE_LOWER_DECK_HEIGHT: u16 = 17;
const BALANCED_LOWER_DECK_HEIGHT: u16 = 11;
const WIDE_DEPTH_WIDTH: u16 = 132;
const TALL_DEPTH_HEIGHT: u16 = 38;

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let symbol_area = Rect::new(area.x, area.y, area.width, area.height.min(3));
    render_symbol_tabs(frame, app, symbol_area);
    let Some(symbol) = app.selected_cohort_symbol() else {
        render_missing_symbol(frame, app, area);
        return;
    };
    let Some(book) = app.backend.cohort.books.get(symbol) else {
        render_missing_book(frame, app, area, symbol);
        return;
    };
    let ladder_height = desired_ladder_height(area, book);
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(5),
            Constraint::Length(ladder_height),
            Constraint::Min(minimum_lower_deck_height(area)),
        ])
        .split(area);
    render_summary(frame, app, sections[1], book);
    render_ladders(frame, app, sections[2], book);
    render_lower_telemetry(frame, app, sections[3], book);
}

fn desired_ladder_height(area: Rect, book: &CohortBookSnapshot) -> u16 {
    let level_count = book.bids.len().max(book.asks.len());
    let desired = u16::try_from(level_count)
        .unwrap_or(u16::MAX)
        .saturating_add(4);
    let reserved = FIXED_DEPTH_HEADER_HEIGHT + minimum_lower_deck_height(area);
    let available = area.height.saturating_sub(reserved).max(7);
    desired.clamp(7, available)
}

fn minimum_lower_deck_height(area: Rect) -> u16 {
    if area.width >= WIDE_DEPTH_WIDTH && area.height >= TALL_DEPTH_HEIGHT {
        TALL_WIDE_LOWER_DECK_HEIGHT
    } else if area.width >= WIDE_DEPTH_WIDTH {
        WIDE_LOWER_DECK_HEIGHT
    } else {
        COMPACT_LOWER_DECK_HEIGHT
    }
}

fn render_missing_symbol(frame: &mut Frame, app: &App, area: Rect) {
    let body = Rect::new(
        area.x,
        area.y.saturating_add(3),
        area.width,
        area.height.saturating_sub(3),
    );
    render_empty(
        frame,
        app,
        body,
        " LIVE HYPERLIQUID L2 ",
        "No enabled market reported",
    );
}

fn render_missing_book(frame: &mut Frame, app: &App, area: Rect, symbol: &str) {
    let body = Rect::new(
        area.x,
        area.y.saturating_add(3),
        area.width,
        area.height.saturating_sub(3),
    );
    render_empty(
        frame,
        app,
        body,
        " LIVE HYPERLIQUID L2 // BACKEND SOURCE REQUIRED ",
        &format!(
            "{symbol} depth unavailable in the current cohort projection; no synthetic levels generated"
        ),
    );
}

fn render_symbol_tabs(frame: &mut Frame, app: &App, area: Rect) {
    let (visible, local_selected) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        MARKET_TABS_PER_PAGE,
    );
    let titles = app
        .backend
        .cohort
        .enabled_symbols
        .get(visible.clone())
        .unwrap_or(&[])
        .iter()
        .map(|symbol| format!(" {symbol} "))
        .collect::<Vec<_>>();
    let label = page_label(&visible, app.backend.cohort.enabled_symbols.len());
    frame.render_widget(
        Tabs::new(titles)
            .select(local_selected)
            .highlight_style(app.theme.highlight)
            .divider(" │ ")
            .block(panel(
                format!(" SELECTED MARKET // MARKETS {label} // [←/→] "),
                app,
            )),
        area,
    );
}

fn render_summary(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let transport_ms = book.recv_ts_ms.saturating_sub(book.exchange_ts_ms);
    let lines = vec![
        Line::from(vec![
            Span::styled(
                format!("{}  MID {:.8}", book.symbol, book.mid_px),
                app.theme.title,
            ),
            Span::raw(format!(
                "  //  SPREAD {:.3} bps  //  VENUE {}",
                book.spread_bps,
                fill_time(book.exchange_ts_ms),
            )),
        ]),
        Line::from(format!(
            "SOURCE {}  //  RECEIVE DELTA {}ms  //  EXACT LEVELS {}/{}",
            book.source,
            transport_ms,
            book.bids.len(),
            book.asks.len(),
        )),
        hip3_summary_line(app),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(
            " LIVE HYPERLIQUID L2 // TOP OF BOOK // MAINNET ",
            app,
        )),
        area,
    );
}

fn render_ladders(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area);
    render_side(
        frame,
        app,
        columns[0],
        " BID DEPTH // BEST FIRST ",
        &book.bids,
        true,
    );
    render_side(
        frame,
        app,
        columns[1],
        " ASK DEPTH // BEST FIRST ",
        &book.asks,
        false,
    );
}

fn render_side(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    title: &str,
    levels: &[CohortBookLevel],
    bid: bool,
) {
    let total: f64 = levels.iter().map(|level| level.size).sum();
    let maximum = levels
        .iter()
        .map(|level| level.size)
        .fold(0.0_f64, f64::max);
    let rows = side_rows(levels, app, bid, maximum);
    let table = Table::new(
        rows,
        [
            Constraint::Length(3),
            Constraint::Length(15),
            Constraint::Length(11),
            Constraint::Length(11),
            Constraint::Length(5),
            Constraint::Min(8),
        ],
    )
    .header(Row::new(["#", "PRICE", "SIZE", "CUM", "ORD", "DEPTH"]).style(app.theme.header))
    .footer(Row::new(vec![
        Cell::from(""),
        Cell::from("TOTAL"),
        Cell::from(format!("{total:.5}")),
    ]))
    .block(panel(title, app));
    frame.render_widget(table, area);
}

fn side_rows(levels: &[CohortBookLevel], app: &App, bid: bool, maximum: f64) -> Vec<Row<'static>> {
    let mut cumulative = 0.0;
    levels
        .iter()
        .enumerate()
        .map(|(index, level)| {
            cumulative += level.size;
            let bar = depth_bar(level.size, maximum, 8);
            let style = if bid {
                app.theme.depth_bid
            } else {
                app.theme.depth_ask
            };
            Row::new(vec![
                Cell::from(format!("{}", index + 1)),
                Cell::from(format!("{:.8}", level.price)).style(style),
                Cell::from(format!("{:.5}", level.size)),
                Cell::from(format!("{:.5}", cumulative)),
                Cell::from(
                    level
                        .orders
                        .map_or_else(|| "N/A".into(), |value| value.to_string()),
                ),
                Cell::from(bar).style(style),
            ])
        })
        .collect()
}

fn render_lower_telemetry(frame: &mut Frame, app: &App, area: Rect, book: &CohortBookSnapshot) {
    if area.height < BALANCED_LOWER_DECK_HEIGHT {
        crate::cohort_depth_analytics::render(frame, app, area, book);
        return;
    }
    crate::cohort_depth_analytics::render_balanced(frame, app, area, book);
}

fn hip3_summary_line(app: &App) -> Line<'static> {
    let status = &app.backend.hip3_roster;
    if !status.configured {
        return Line::from("HIP-3 ROSTER NOT CONFIGURED  //  REPORT ONLY");
    }
    if !status.available {
        return Line::from(format!(
            "HIP-3 ROSTER UNAVAILABLE  //  {}",
            status
                .issue
                .as_deref()
                .unwrap_or("backend checkpoint missing"),
        ));
    }
    let freshness = if status.stale { "STALE" } else { "LIVE" };
    let enabled_count =
        crate::cohort_hip3_roster::enabled_markets(status, &app.backend.cohort.enabled_symbols)
            .count();
    Line::from(format!(
        "HIP-3 {freshness}  //  {enabled_count}/{} ENABLED MARKETS  //  NO EXECUTION AUTHORITY",
        status.markets.len(),
    ))
}

fn depth_bar(value: f64, maximum: f64, width: usize) -> String {
    let filled = if maximum <= 0.0 {
        0
    } else {
        ((value / maximum) * width as f64).round() as usize
    };
    format!(
        "{}{}",
        "█".repeat(filled.min(width)),
        "░".repeat(width.saturating_sub(filled)),
    )
}
