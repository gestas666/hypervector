//! Pure Ratatui widgets for backend candles, volume, and aligned regimes.

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
    widgets::{Block, Borders, Widget},
};

use crate::{
    app::App,
    model::{RegimeSnapshot, RegimeState},
    theme::CockpitTheme,
    ui::format_time_display,
};

const AXIS_WIDTH: u16 = 10;
const MAX_VISIBLE_CANDLES: usize = 90;

#[derive(Clone)]
pub(crate) struct StrategyLevel {
    pub(crate) label: String,
    pub(crate) price: f64,
    pub(crate) style: Style,
}

pub(crate) fn visible_candles(app: &App, width: u16) -> &[RegimeSnapshot] {
    let plot_columns = width.saturating_sub(AXIS_WIDTH + 2) as usize;
    let capacity = (plot_columns / 2).clamp(1, MAX_VISIBLE_CANDLES);
    let end = (app.current_index + 1).min(app.snapshots.len());
    let start = end.saturating_sub(capacity);
    &app.snapshots[start..end]
}

pub(crate) fn price_bounds(candles: &[RegimeSnapshot]) -> Option<(f64, f64)> {
    let low = candles
        .iter()
        .map(|candle| candle.low)
        .fold(f64::MAX, f64::min);
    let high = candles
        .iter()
        .map(|candle| candle.high)
        .fold(f64::MIN, f64::max);
    if !low.is_finite() || !high.is_finite() {
        return None;
    }
    let padding = ((high - low) * 0.04).max(0.01);
    Some((low - padding, high + padding))
}

pub(crate) struct CandlePane<'a> {
    candles: &'a [RegimeSnapshot],
    levels: &'a [StrategyLevel],
    theme: &'a CockpitTheme,
}

impl<'a> CandlePane<'a> {
    pub(crate) fn new(
        candles: &'a [RegimeSnapshot],
        levels: &'a [StrategyLevel],
        theme: &'a CockpitTheme,
    ) -> Self {
        Self {
            candles,
            levels,
            theme,
        }
    }
}

impl Widget for CandlePane<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .title(" CANDLES · BACKEND OHLC ")
            .title_style(self.theme.title)
            .borders(Borders::ALL)
            .border_style(self.theme.border);
        let inner = block.inner(area);
        block.render(area, buf);
        let Some(plot) = candle_plot_area(inner) else {
            return;
        };
        let Some((low, high)) = price_bounds(self.candles) else {
            return;
        };
        render_price_axis(buf, inner, plot, low, high, self.theme);
        render_candles(buf, plot, self.candles, low, high, self.theme);
        render_levels(buf, plot, self.levels, low, high);
        render_time_axis(buf, inner, plot, self.candles, self.theme);
        render_open_warning(buf, plot, self.candles, self.theme);
    }
}

fn candle_plot_area(inner: Rect) -> Option<Rect> {
    if inner.width <= AXIS_WIDTH + 1 || inner.height < 3 {
        return None;
    }
    Some(Rect::new(
        inner.x + AXIS_WIDTH,
        inner.y,
        inner.width - AXIS_WIDTH,
        inner.height - 1,
    ))
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
        (plot.y + plot.height.saturating_sub(1), low),
    ] {
        buf.set_string(inner.x, y, format!("${price:>8.2}"), theme.muted);
        for x in plot.x..plot.right() {
            put(buf, plot, x, y, "┄", theme.bar_ghost);
        }
    }
}

fn render_candles(
    buf: &mut Buffer,
    plot: Rect,
    candles: &[RegimeSnapshot],
    low: f64,
    high: f64,
    theme: &CockpitTheme,
) {
    for (index, candle) in candles.iter().enumerate() {
        let Some(open) = candle.open else { continue };
        let x = candle_x(plot, index, candles.len());
        let style = candle_style(theme, open, candle.price);
        let high_y = price_y(plot, candle.high, low, high);
        let low_y = price_y(plot, candle.low, low, high);
        for y in high_y..=low_y {
            put(buf, plot, x, y, "│", style);
        }
        render_body(buf, plot, x, open, candle.price, low, high, style);
        render_eligibility_marker(buf, plot, x, candle, low_y, high_y, theme);
    }
}

#[allow(clippy::too_many_arguments)]
fn render_body(
    buf: &mut Buffer,
    plot: Rect,
    x: u16,
    open: f64,
    close: f64,
    low: f64,
    high: f64,
    style: Style,
) {
    let open_y = price_y(plot, open, low, high);
    let close_y = price_y(plot, close, low, high);
    if open_y == close_y {
        put(buf, plot, x, open_y, "━", style);
        return;
    }
    for y in open_y.min(close_y)..=open_y.max(close_y) {
        put(buf, plot, x, y, "█", style);
    }
}

#[allow(clippy::too_many_arguments)]
fn render_eligibility_marker(
    buf: &mut Buffer,
    plot: Rect,
    x: u16,
    candle: &RegimeSnapshot,
    low_y: u16,
    high_y: u16,
    theme: &CockpitTheme,
) {
    if candle.max_leverage <= 0.0 {
        return;
    }
    if candle.long_weight > candle.short_weight {
        put(buf, plot, x, low_y.saturating_add(1), "▲", theme.bull);
    } else if candle.short_weight > candle.long_weight {
        put(buf, plot, x, high_y.saturating_sub(1), "▼", theme.bear);
    }
}

fn render_levels(buf: &mut Buffer, plot: Rect, levels: &[StrategyLevel], low: f64, high: f64) {
    for level in levels
        .iter()
        .filter(|level| (low..=high).contains(&level.price))
    {
        let y = price_y(plot, level.price, low, high);
        for x in plot.x..plot.right() {
            put(buf, plot, x, y, "┈", level.style);
        }
        let label = format!("{} ${:.2}", level.label, level.price);
        let x = plot.right().saturating_sub(label.len() as u16);
        buf.set_string(x, y, label, level.style);
    }
}

fn render_open_warning(
    buf: &mut Buffer,
    plot: Rect,
    candles: &[RegimeSnapshot],
    theme: &CockpitTheme,
) {
    if candles.iter().all(|candle| candle.open.is_none()) {
        let message = "OPEN DATA UNAVAILABLE";
        let x = plot.x + plot.width.saturating_sub(message.len() as u16) / 2;
        let y = plot.y + plot.height / 2;
        buf.set_string(x, y, message, theme.bear);
    }
}

fn render_time_axis(
    buf: &mut Buffer,
    inner: Rect,
    plot: Rect,
    candles: &[RegimeSnapshot],
    theme: &CockpitTheme,
) {
    let y = inner.bottom().saturating_sub(1);
    if let Some(first) = candles.first() {
        buf.set_string(
            plot.x,
            y,
            format_time_display(&first.timestamp_str),
            theme.muted,
        );
    }
    if let Some(last) = candles.last() {
        let label = format_time_display(&last.timestamp_str);
        let x = plot.right().saturating_sub(label.len() as u16);
        buf.set_string(x, y, label, theme.muted);
    }
}

fn candle_style(theme: &CockpitTheme, open: f64, close: f64) -> Style {
    if close > open {
        theme.bull
    } else if close < open {
        theme.bear
    } else {
        theme.chop
    }
}

fn candle_x(plot: Rect, index: usize, count: usize) -> u16 {
    if count == 0 {
        return plot.x;
    }
    let numerator = (2 * index + 1) * plot.width as usize;
    (plot.x + (numerator / (2 * count)) as u16).min(plot.right().saturating_sub(1))
}

fn price_y(plot: Rect, price: f64, low: f64, high: f64) -> u16 {
    let ratio = ((high - price) / (high - low)).clamp(0.0, 1.0);
    plot.y + (ratio * f64::from(plot.height.saturating_sub(1))).round() as u16
}

fn put(buf: &mut Buffer, area: Rect, x: u16, y: u16, symbol: &str, style: Style) {
    if x >= area.x && x < area.right() && y >= area.y && y < area.bottom() {
        buf[(x, y)].set_symbol(symbol).set_style(style);
    }
}

pub(crate) struct VolumePane<'a> {
    candles: &'a [RegimeSnapshot],
    theme: &'a CockpitTheme,
}

impl<'a> VolumePane<'a> {
    pub(crate) fn new(candles: &'a [RegimeSnapshot], theme: &'a CockpitTheme) -> Self {
        Self { candles, theme }
    }
}

impl Widget for VolumePane<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .title(" VOLUME · BACKEND ")
            .title_style(self.theme.title)
            .borders(Borders::ALL)
            .border_style(self.theme.border);
        let inner = block.inner(area);
        block.render(area, buf);
        let Some(plot) = lower_plot_area(inner) else {
            return;
        };
        let max = self
            .candles
            .iter()
            .map(|candle| candle.volume)
            .fold(0.0, f64::max);
        buf.set_string(inner.x, inner.y, format!("{max:>8.2}"), self.theme.muted);
        for (index, candle) in self.candles.iter().enumerate() {
            render_volume_bar(
                buf,
                plot,
                candle,
                index,
                self.candles.len(),
                max,
                self.theme,
            );
        }
    }
}

fn render_volume_bar(
    buf: &mut Buffer,
    plot: Rect,
    candle: &RegimeSnapshot,
    index: usize,
    count: usize,
    max: f64,
    theme: &CockpitTheme,
) {
    let height = volume_height(candle.volume, max, plot.height);
    let x = candle_x(plot, index, count);
    let style = candle
        .open
        .map(|open| candle_style(theme, open, candle.price))
        .unwrap_or(theme.muted);
    for offset in 0..height {
        put(buf, plot, x, plot.bottom() - 1 - offset, "█", style);
    }
}

fn volume_height(volume: f64, max: f64, height: u16) -> u16 {
    if max <= 0.0 || height == 0 {
        return 0;
    }
    ((volume / max).clamp(0.0, 1.0) * f64::from(height)).ceil() as u16
}

pub(crate) struct RegimeTape<'a> {
    candles: &'a [RegimeSnapshot],
    theme: &'a CockpitTheme,
}

impl<'a> RegimeTape<'a> {
    pub(crate) fn new(candles: &'a [RegimeSnapshot], theme: &'a CockpitTheme) -> Self {
        Self { candles, theme }
    }
}

impl Widget for RegimeTape<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let current = self
            .candles
            .last()
            .map(|candle| candle.state.primary_label())
            .unwrap_or("N/A");
        let block = Block::default()
            .title(format!(" REGIME TAPE · {current} "))
            .title_style(self.theme.title)
            .borders(Borders::ALL)
            .border_style(self.theme.border);
        let inner = block.inner(area);
        block.render(area, buf);
        let Some(plot) = lower_plot_area(inner) else {
            return;
        };
        for (index, candle) in self.candles.iter().enumerate() {
            let x = candle_x(plot, index, self.candles.len());
            put(
                buf,
                plot,
                x,
                plot.y,
                "█",
                regime_style(self.theme, candle.state),
            );
        }
    }
}

fn lower_plot_area(inner: Rect) -> Option<Rect> {
    if inner.width <= AXIS_WIDTH || inner.height == 0 {
        return None;
    }
    Some(Rect::new(
        inner.x + AXIS_WIDTH,
        inner.y,
        inner.width - AXIS_WIDTH,
        inner.height,
    ))
}

fn regime_style(theme: &CockpitTheme, state: RegimeState) -> Style {
    match state {
        RegimeState::BullMomentum => theme.bull,
        RegimeState::BearMomentum => theme.bear,
        RegimeState::VolatilityCoiling => theme.coiling,
        RegimeState::FundingCarry => theme.carry,
        RegimeState::RangeChop | RegimeState::Unknown => theme.chop,
    }
}
