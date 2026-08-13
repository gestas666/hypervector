//! Candlestick visualization derived only from backend-completed cohort bars.

use ratatui::{
    Frame,
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph, Widget},
};

use crate::app::App;
use crate::backend_cohort::CohortCandle;
use crate::cohort_format::{fill_time, number};
use crate::cohort_widgets::{page_label, panel, render_empty, selected_page};
use crate::theme::CockpitTheme;

const AXIS_WIDTH: u16 = 11;
const MAX_VISIBLE_CANDLES: usize = 90;
const MINUTE_MS: u64 = 60_000;
const CHARTS_PER_PAGE: usize = 4;

/// Render four selectable candlestick panes from backend completed 1-minute bars.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(12)])
        .split(area);
    let (visible, _) = selected_page(
        app.backend.cohort.enabled_symbols.len(),
        app.selected_cohort_symbol_index,
        CHARTS_PER_PAGE,
    );
    render_explanation(frame, app, sections[0], &visible);
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(sections[1]);
    let top = chart_columns(rows[0]);
    let bottom = chart_columns(rows[1]);
    let panels = [top[0], top[1], bottom[0], bottom[1]];
    for (panel_index, symbol_index) in visible.clone().enumerate() {
        let symbol = &app.backend.cohort.enabled_symbols[symbol_index];
        render_symbol_chart(
            frame,
            app,
            panels[panel_index],
            symbol,
            symbol_index == app.selected_cohort_symbol_index,
        );
    }
    for area in panels.iter().skip(visible.len()) {
        render_empty(
            frame,
            app,
            *area,
            " UNASSIGNED MARKET PANE ",
            "No additional asset is configured on this page",
        );
    }
}

/// Render the selected strategy's completed decision-timeframe candles.
pub(crate) fn render_focused(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    symbol: &str,
    timeframe: &str,
) {
    let source = app
        .backend
        .cohort
        .candle_history
        .get(symbol)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if source.is_empty() {
        render_empty(
            frame,
            app,
            area,
            &format!(" {symbol} CANDLES "),
            "BACKEND OHLCV UNAVAILABLE",
        );
        return;
    }
    let candles = match decision_timeframe_candles(source, timeframe) {
        Ok(candles) if !candles.is_empty() => candles,
        Ok(_) => {
            render_empty(
                frame,
                app,
                area,
                &format!(" {symbol} {} CANDLES ", timeframe.to_uppercase()),
                &format!(
                    "NO COMPLETE {} BAR IN BACKEND WINDOW",
                    timeframe.to_uppercase()
                ),
            );
            return;
        }
        Err(message) => {
            render_empty(frame, app, area, " STRATEGY CANDLES ", &message);
            return;
        }
    };
    render_chart_series(frame, app, area, symbol, timeframe, &candles, true);
}

fn render_explanation(frame: &mut Frame, app: &App, area: Rect, visible: &std::ops::Range<usize>) {
    let line = Line::from(vec![
        Span::styled("BACKEND 1M OVERVIEW", app.theme.title),
        Span::raw(
            "  //  PRICE  //  DETAIL USES PROVIDER TF + INDICATORS  //  [←/→] PAGE  //  [ENTER] INSPECT",
        ),
    ]);
    frame.render_widget(
        Paragraph::new(line).block(panel(
            format!(
                " MARKET CANDLES // ASSETS {} // READ ONLY ",
                page_label(visible, app.backend.cohort.enabled_symbols.len())
            ),
            app,
        )),
        area,
    );
}

fn render_symbol_chart(frame: &mut Frame, app: &App, area: Rect, symbol: &str, selected: bool) {
    let candles = app
        .backend
        .cohort
        .candle_history
        .get(symbol)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if candles.is_empty() {
        render_empty(
            frame,
            app,
            area,
            &format!(" {symbol} CANDLES "),
            "BACKEND OHLCV UNAVAILABLE",
        );
        return;
    }
    render_chart_series(frame, app, area, symbol, "1m", candles, selected);
}

fn render_chart_series(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    symbol: &str,
    timeframe: &str,
    candles: &[CohortCandle],
    selected: bool,
) {
    frame.render_widget(
        CohortCandlePane::new(symbol, timeframe, candles, &app.theme, selected),
        area,
    );
}

struct CohortCandlePane<'a> {
    symbol: &'a str,
    timeframe: &'a str,
    candles: &'a [CohortCandle],
    theme: &'a CockpitTheme,
    selected: bool,
}

impl<'a> CohortCandlePane<'a> {
    fn new(
        symbol: &'a str,
        timeframe: &'a str,
        candles: &'a [CohortCandle],
        theme: &'a CockpitTheme,
        selected: bool,
    ) -> Self {
        Self {
            symbol,
            timeframe,
            candles,
            theme,
            selected,
        }
    }
}

impl Widget for CohortCandlePane<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let candles = visible_candles(self.candles, area.width);
        let block = candle_block(
            chart_title(self.symbol, self.timeframe, candles, self.selected),
            self.theme,
            self.selected,
        );
        let inner = block.inner(area);
        block.render(area, buf);
        let Some((price_plot, time_y, volume_plot)) = plot_areas(inner) else {
            return;
        };
        let (low, high) = price_bounds(candles);
        render_price_axis(buf, inner, price_plot, low, high, self.theme);
        render_candles(buf, price_plot, candles, low, high, self.theme);
        render_time_axis(buf, price_plot, time_y, candles, self.theme);
        render_volume(buf, volume_plot, candles, self.theme);
    }
}

fn candle_block(title: String, theme: &CockpitTheme, selected: bool) -> Block<'static> {
    Block::default()
        .title(title)
        .title_style(theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(if selected {
            theme.border_active
        } else {
            theme.border
        })
}

fn visible_candles(candles: &[CohortCandle], width: u16) -> &[CohortCandle] {
    let capacity =
        (width.saturating_sub(AXIS_WIDTH + 2) as usize / 2).clamp(1, MAX_VISIBLE_CANDLES);
    &candles[candles.len().saturating_sub(capacity)..]
}

fn plot_areas(inner: Rect) -> Option<(Rect, u16, Rect)> {
    if inner.width <= AXIS_WIDTH + 2 || inner.height < 6 {
        return None;
    }
    let price_height = inner.height - 3;
    let plot_x = inner.x + AXIS_WIDTH;
    let plot_width = inner.width - AXIS_WIDTH;
    let price = Rect::new(plot_x, inner.y, plot_width, price_height);
    let time_y = price.bottom();
    let volume = Rect::new(plot_x, time_y + 1, plot_width, 2);
    Some((price, time_y, volume))
}

fn chart_title(symbol: &str, timeframe: &str, candles: &[CohortCandle], selected: bool) -> String {
    let first = candles.first().expect("non-empty candle history");
    let last = candles.last().expect("non-empty candle history");
    let delta_bps = (last.close / first.close - 1.0) * 10_000.0;
    let bar_label = if candles.len() == 1 { "bar" } else { "bars" };
    format!(
        " {}{symbol} {} CANDLES | {} | {} {bar_label} | {delta_bps:+.1}bps ",
        if selected { "▸ " } else { "" },
        timeframe.to_uppercase(),
        number(Some(last.close)),
        candles.len(),
    )
}

fn decision_timeframe_candles(
    candles: &[CohortCandle],
    timeframe: &str,
) -> Result<Vec<CohortCandle>, String> {
    let minutes = timeframe
        .strip_suffix('m')
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| matches!(value, 1 | 5 | 15 | 30))
        .ok_or_else(|| {
            format!(
                "UNSUPPORTED DECISION TIMEFRAME {}",
                timeframe.to_uppercase()
            )
        })?;
    if minutes == 1 {
        return Ok(candles.to_vec());
    }
    Ok(aggregate_complete_buckets(candles, minutes))
}

fn aggregate_complete_buckets(candles: &[CohortCandle], minutes: usize) -> Vec<CohortCandle> {
    let interval_ms = minutes as u64 * MINUTE_MS;
    let mut output = Vec::new();
    let mut start = 0;
    while start < candles.len() {
        let bucket_ms = candles[start].timestamp_ms / interval_ms * interval_ms;
        let end = candles[start..]
            .iter()
            .position(|bar| bar.timestamp_ms >= bucket_ms + interval_ms)
            .map_or(candles.len(), |offset| start + offset);
        if let Some(bar) = aggregate_bucket(&candles[start..end], bucket_ms, minutes) {
            output.push(bar);
        }
        start = end;
    }
    output
}

fn aggregate_bucket(
    candles: &[CohortCandle],
    bucket_ms: u64,
    minutes: usize,
) -> Option<CohortCandle> {
    let complete = candles.len() == minutes
        && candles
            .iter()
            .enumerate()
            .all(|(index, bar)| bar.timestamp_ms == bucket_ms + index as u64 * MINUTE_MS);
    complete.then(|| CohortCandle {
        timestamp_ms: bucket_ms,
        open: candles.first().expect("complete bucket").open,
        high: candles.iter().map(|bar| bar.high).fold(f64::MIN, f64::max),
        low: candles.iter().map(|bar| bar.low).fold(f64::MAX, f64::min),
        close: candles.last().expect("complete bucket").close,
        volume: candles.iter().map(|bar| bar.volume).sum(),
    })
}

fn price_bounds(candles: &[CohortCandle]) -> (f64, f64) {
    let low = candles.iter().map(|bar| bar.low).fold(f64::MAX, f64::min);
    let high = candles.iter().map(|bar| bar.high).fold(f64::MIN, f64::max);
    let padding = ((high - low) * 0.04).max(high.abs() * 0.000_01);
    (low - padding, high + padding)
}

fn render_price_axis(
    buf: &mut Buffer,
    inner: Rect,
    plot: Rect,
    low: f64,
    high: f64,
    theme: &CockpitTheme,
) {
    for (y, price) in [
        (plot.y, high),
        (plot.y + plot.height / 2, (high + low) / 2.0),
        (plot.bottom() - 1, low),
    ] {
        buf.set_string(inner.x, y, axis_price(price), theme.muted);
        for x in plot.x..plot.right() {
            put(buf, plot, x, y, "┄", theme.bar_ghost);
        }
    }
}

fn render_candles(
    buf: &mut Buffer,
    plot: Rect,
    candles: &[CohortCandle],
    low: f64,
    high: f64,
    theme: &CockpitTheme,
) {
    for (index, candle) in candles.iter().enumerate() {
        let x = candle_x(plot, index, candles.len());
        let style = candle_style(candle, theme);
        let high_y = price_y(plot, candle.high, low, high);
        let low_y = price_y(plot, candle.low, low, high);
        for y in high_y..=low_y {
            put(buf, plot, x, y, "│", style);
        }
        let open_y = price_y(plot, candle.open, low, high);
        let close_y = price_y(plot, candle.close, low, high);
        if open_y == close_y {
            put(buf, plot, x, open_y, "━", style);
        } else {
            for y in open_y.min(close_y)..=open_y.max(close_y) {
                put(buf, plot, x, y, "█", style);
            }
        }
    }
}

fn render_time_axis(
    buf: &mut Buffer,
    plot: Rect,
    y: u16,
    candles: &[CohortCandle],
    theme: &CockpitTheme,
) {
    let first = short_time(candles.first().expect("candles").timestamp_ms);
    let last = short_time(candles.last().expect("candles").timestamp_ms);
    buf.set_string(plot.x, y, first, theme.muted);
    let x = plot.right().saturating_sub(last.len() as u16);
    buf.set_string(x, y, last, theme.muted);
}

fn render_volume(buf: &mut Buffer, plot: Rect, candles: &[CohortCandle], theme: &CockpitTheme) {
    let maximum = candles.iter().map(|bar| bar.volume).fold(0.0, f64::max);
    for (index, candle) in candles.iter().enumerate() {
        let height = if maximum > 0.0 {
            ((candle.volume / maximum) * f64::from(plot.height)).ceil() as u16
        } else {
            0
        };
        let x = candle_x(plot, index, candles.len());
        for offset in 0..height.min(plot.height) {
            put(
                buf,
                plot,
                x,
                plot.bottom() - 1 - offset,
                "▄",
                candle_style(candle, theme),
            );
        }
    }
}

fn candle_style(candle: &CohortCandle, theme: &CockpitTheme) -> Style {
    if candle.close > candle.open {
        theme.bull
    } else if candle.close < candle.open {
        theme.bear
    } else {
        theme.chop
    }
}

fn candle_x(plot: Rect, index: usize, count: usize) -> u16 {
    let numerator = (2 * index + 1) * plot.width as usize;
    (plot.x + (numerator / (2 * count)) as u16).min(plot.right() - 1)
}

fn price_y(plot: Rect, price: f64, low: f64, high: f64) -> u16 {
    let ratio = ((high - price) / (high - low)).clamp(0.0, 1.0);
    plot.y + (ratio * f64::from(plot.height - 1)).round() as u16
}

fn short_time(timestamp_ms: u64) -> String {
    fill_time(timestamp_ms)
        .split(':')
        .take(2)
        .collect::<Vec<_>>()
        .join(":")
}

fn axis_price(price: f64) -> String {
    if price >= 1_000.0 {
        format!("{price:>10.2}")
    } else if price >= 1.0 {
        format!("{price:>10.4}")
    } else {
        format!("{price:>10.6}")
    }
}

fn put(buf: &mut Buffer, area: Rect, x: u16, y: u16, symbol: &str, style: Style) {
    if x >= area.x && x < area.right() && y >= area.y && y < area.bottom() {
        buf[(x, y)].set_symbol(symbol).set_style(style);
    }
}

fn chart_columns(area: Rect) -> std::rc::Rc<[Rect]> {
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(area)
}
