//! Thin, scaled closed-lifecycle equity line for the cohort dashboard.

use ratatui::{buffer::Buffer, layout::Rect, style::Style, widgets::Widget};

const AXIS_WIDTH: u16 = 11;

/// Render a connected equity line from backend-authored closed lifecycle values.
pub(crate) struct ClosedEquityCurve<'a> {
    pub(crate) values: &'a [f64],
    pub(crate) deltas: &'a [f64],
    pub(crate) baseline: f64,
    pub(crate) gain: Style,
    pub(crate) loss: Style,
    pub(crate) neutral: Style,
    pub(crate) baseline_style: Style,
    pub(crate) drawdown: Style,
}

impl Widget for ClosedEquityCurve<'_> {
    fn render(self, area: Rect, buffer: &mut Buffer) {
        if self.values.is_empty()
            || area.width <= AXIS_WIDTH + 2
            || area.height < 3
            || !self.baseline.is_finite()
        {
            return;
        }
        let (observed_low, observed_high) = observed_bounds(self.values, self.baseline);
        let (low, high) = padded_bounds(observed_low, observed_high);
        let plot = Rect::new(
            area.x + AXIS_WIDTH,
            area.y,
            area.width - AXIS_WIDTH,
            area.height,
        );
        let baseline_y = value_y(self.baseline, low, high, plot.height);
        render_axis(
            area,
            buffer,
            observed_low,
            observed_high,
            self.baseline,
            baseline_y,
            self.neutral,
        );
        render_baseline(plot, buffer, baseline_y, self.baseline_style);
        self.render_line(plot, buffer, low, high);
        self.render_drawdowns(plot, buffer, low, high);
        self.render_markers(plot, buffer, low, high);
    }
}

impl ClosedEquityCurve<'_> {
    fn render_line(&self, plot: Rect, buffer: &mut Buffer, low: f64, high: f64) {
        let last = self.values.len().saturating_sub(1);
        for index in 1..self.values.len() {
            let start = (
                point_x(index - 1, last, plot.width),
                value_y(self.values[index - 1], low, high, plot.height),
            );
            let end = (
                point_x(index, last, plot.width),
                value_y(self.values[index], low, high, plot.height),
            );
            render_segment(plot, buffer, start, end, self.value_style(index));
        }
    }

    fn render_drawdowns(&self, plot: Rect, buffer: &mut Buffer, low: f64, high: f64) {
        let last = self.values.len().saturating_sub(1);
        let mut peak = self.values[0];
        for (index, value) in self.values.iter().copied().enumerate().skip(1) {
            if value < peak {
                let x = point_x(index, last, plot.width);
                let peak_y = value_y(peak, low, high, plot.height);
                let value_y = value_y(value, low, high, plot.height);
                for y in peak_y.saturating_add(1)..value_y {
                    buffer.set_string(plot.x + x, plot.y + y, "┊", self.drawdown);
                }
            }
            peak = peak.max(value);
        }
    }

    fn render_markers(&self, plot: Rect, buffer: &mut Buffer, low: f64, high: f64) {
        let last = self.values.len().saturating_sub(1);
        let start_y = value_y(self.values[0], low, high, plot.height);
        buffer.set_string(plot.x, plot.y + start_y, "◆", self.neutral);
        for index in 1..self.values.len() {
            let x = point_x(index, last, plot.width);
            let after = value_y(self.values[index], low, high, plot.height);
            let style = self.value_style(index);
            let delta = self.deltas.get(index - 1).copied().unwrap_or(0.0);
            let marker = if delta > 0.0 {
                "▲"
            } else if delta < 0.0 {
                "▼"
            } else {
                "◆"
            };
            buffer.set_string(plot.x + x, plot.y + after, marker, style);
        }
    }

    fn value_style(&self, point_index: usize) -> Style {
        let delta = point_index
            .checked_sub(1)
            .and_then(|index| self.deltas.get(index))
            .copied()
            .unwrap_or(0.0);
        if delta > 0.0 {
            self.gain
        } else if delta < 0.0 {
            self.loss
        } else {
            self.neutral
        }
    }
}

fn render_axis(
    area: Rect,
    buffer: &mut Buffer,
    low: f64,
    high: f64,
    baseline: f64,
    baseline_y: u16,
    style: Style,
) {
    let bottom = area.height - 1;
    for (row, prefix, value, marker) in [
        (0, "H", high, "┤"),
        (baseline_y, "B", baseline, "┼"),
        (bottom, "L", low, "┤"),
    ] {
        let label = format!("{prefix} {:>7}{marker}", axis_money(value));
        buffer.set_stringn(area.x, area.y + row, label, AXIS_WIDTH as usize, style);
    }
}

fn render_baseline(plot: Rect, buffer: &mut Buffer, row: u16, style: Style) {
    for x in 0..plot.width {
        buffer.set_string(plot.x + x, plot.y + row, "┄", style);
    }
}

fn render_segment(
    plot: Rect,
    buffer: &mut Buffer,
    start: (u16, u16),
    end: (u16, u16),
    style: Style,
) {
    let width = end.0.saturating_sub(start.0);
    let mut previous_y = start.1;
    for offset in 0..=width {
        let progress = if width == 0 {
            1.0
        } else {
            f64::from(offset) / f64::from(width)
        };
        let y = (f64::from(start.1) + f64::from(end.1 as i32 - start.1 as i32) * progress).round()
            as u16;
        let glyph = if y < previous_y {
            "╱"
        } else if y > previous_y {
            "╲"
        } else {
            "─"
        };
        buffer.set_string(plot.x + start.0 + offset, plot.y + y, glyph, style);
        previous_y = y;
    }
}

fn observed_bounds(values: &[f64], baseline: f64) -> (f64, f64) {
    let low = values
        .iter()
        .copied()
        .reduce(f64::min)
        .unwrap_or(baseline)
        .min(baseline);
    let high = values
        .iter()
        .copied()
        .reduce(f64::max)
        .unwrap_or(baseline)
        .max(baseline);
    (low, high)
}

fn padded_bounds(low: f64, high: f64) -> (f64, f64) {
    let span = (high - low).abs();
    let padding = (span * 0.12).max(0.01);
    (low - padding, high + padding)
}

fn point_x(index: usize, last: usize, width: u16) -> u16 {
    if last == 0 {
        return 0;
    }
    u16::try_from(index * usize::from(width.saturating_sub(1)) / last)
        .expect("equity point is bounded by terminal width")
}

fn value_y(value: f64, low: f64, high: f64, height: u16) -> u16 {
    let normalized = ((value - low) / (high - low)).clamp(0.0, 1.0);
    let from_bottom = (normalized * f64::from(height.saturating_sub(1))).round() as u16;
    height.saturating_sub(1).saturating_sub(from_bottom)
}

fn axis_money(value: f64) -> String {
    if value.abs() >= 10_000.0 {
        format!("${value:.0}")
    } else {
        format!("${value:.2}")
    }
}
