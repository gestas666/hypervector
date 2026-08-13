//! Compact selected-coin directional component stack.

use std::collections::BTreeMap;

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
};
use serde_json::Value;

use crate::app::App;
use crate::cohort_regime::latest_regime;
use crate::cohort_widgets::panel;

/// Render the backend-authored directional vote stack for the selected coin.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let symbol = app.selected_cohort_symbol().unwrap_or("N/A");
    let Some(evaluation) = latest_regime(app, symbol) else {
        crate::cohort_regime_provider::render_compact(frame, app, area, symbol);
        return;
    };
    let metrics = &evaluation.readiness.metrics;
    let title = format!(" TREND STACK // {symbol} // {} ", alignment(metrics));
    frame.render_widget(
        Paragraph::new(component_lines(app, metrics)).block(panel(title, app)),
        area,
    );
}

fn component_lines<'a>(app: &'a App, metrics: &BTreeMap<String, Value>) -> Vec<Line<'a>> {
    vec![
        paired_line(
            app,
            "EMA",
            metric(metrics, "ema_21_55_gap_bps"),
            "SMA",
            metric(metrics, "sma_100_200_gap_bps"),
        ),
        paired_line(
            app,
            "CIPHER",
            metric(metrics, "cipher_a_direction"),
            "HA-RSI",
            metric(metrics, "harsi_direction"),
        ),
        paired_line(
            app,
            "MTF 5M",
            metric(metrics, "mtf_5m_bias"),
            "15M",
            metric(metrics, "mtf_15m_bias"),
        ),
        quality_line(app, metrics),
    ]
}

fn paired_line<'a>(
    app: &'a App,
    left_label: &str,
    left: Option<f64>,
    right_label: &str,
    right: Option<f64>,
) -> Line<'a> {
    Line::from(vec![
        Span::styled(
            format!("{left_label} {}", signed(left)),
            direction_style(app, left),
        ),
        Span::raw("  │  "),
        Span::styled(
            format!("{right_label} {}", signed(right)),
            direction_style(app, right),
        ),
    ])
}

fn quality_line<'a>(app: &'a App, metrics: &BTreeMap<String, Value>) -> Line<'a> {
    Line::from(vec![
        Span::styled(
            format!("TQI {}", decimal(metrics, "self_aware_tqi", 2)),
            app.theme.cyan,
        ),
        Span::raw("  │  "),
        Span::styled(
            format!("R² {}", decimal(metrics, "trend_r2", 2)),
            app.theme.carry,
        ),
        Span::raw("  │  "),
        Span::styled(
            format!("CHOP {}", decimal(metrics, "choppiness_14", 1)),
            app.theme.gold,
        ),
    ])
}

fn alignment(metrics: &BTreeMap<String, Value>) -> &'static str {
    let votes = [
        metric(metrics, "ema_21_55_gap_bps"),
        metric(metrics, "sma_100_200_gap_bps"),
        metric(metrics, "cipher_a_direction"),
        metric(metrics, "harsi_direction"),
    ];
    let up = votes.iter().flatten().any(|value| *value > 0.0);
    let down = votes.iter().flatten().any(|value| *value < 0.0);
    if up && down {
        "CONFLICT"
    } else if up {
        "BULL STACK"
    } else if down {
        "BEAR STACK"
    } else {
        "NEUTRAL"
    }
}

fn direction_style(app: &App, value: Option<f64>) -> Style {
    match value {
        Some(number) if number > 0.0 => app.theme.bull,
        Some(number) if number < 0.0 => app.theme.bear,
        Some(_) => app.theme.gold,
        None => app.theme.muted,
    }
}

fn metric(metrics: &BTreeMap<String, Value>, key: &str) -> Option<f64> {
    metrics.get(key).and_then(Value::as_f64)
}

fn signed(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}"))
}

fn decimal(metrics: &BTreeMap<String, Value>, key: &str, places: usize) -> String {
    metric(metrics, key).map_or_else(|| "N/A".into(), |number| format!("{number:.places$}"))
}
