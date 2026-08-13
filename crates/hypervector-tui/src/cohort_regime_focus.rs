//! Selected-coin compression, trend-strength, and breakout-energy console.

use std::collections::BTreeMap;

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
};
use serde_json::Value;

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_format::fill_time;
use crate::cohort_regime::latest_regime;
use crate::cohort_widgets::panel;

/// Render backend-causal regime anatomy as compact operational meters.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let symbol = app.selected_cohort_symbol().unwrap_or("N/A");
    let Some(evaluation) = latest_regime(app, symbol) else {
        crate::cohort_regime_provider::render_focus(frame, app, area, symbol);
        return;
    };
    let block = panel(format!(" COMPRESSION + BREAKOUT ENGINE // {symbol} "), app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let sections = Layout::vertical([
        Constraint::Length(2),
        Constraint::Min(5),
        Constraint::Length(3),
    ])
    .split(inner);
    render_summary(frame, app, evaluation, sections[0]);
    render_meters(frame, app, evaluation, sections[1]);
    render_footer(frame, app, symbol, evaluation, sections[2]);
}

fn render_summary(frame: &mut Frame, app: &App, value: &CohortProviderEvaluation, area: Rect) {
    let state = value.primary_regime.as_deref().unwrap_or("N/A");
    let one = value.state_1m.as_deref().unwrap_or("N/A");
    let five = value.state_5m.as_deref().unwrap_or("N/A");
    let fifteen = value.context_15m.as_deref().unwrap_or("N/A");
    let lines = vec![
        Line::from(vec![
            Span::styled(format!("5M VERDICT {state}"), state_style(app, state)),
            Span::raw("  //  CANONICAL PRIMARY"),
        ]),
        Line::from(vec![
            Span::styled(format!("1M {one}"), state_style(app, one)),
            Span::raw("  │  "),
            Span::styled(format!("5M {five}"), state_style(app, five)),
            Span::raw("  │  "),
            Span::styled(format!("15M {fifteen}"), state_style(app, fifteen)),
        ]),
    ];
    frame.render_widget(Paragraph::new(lines), area);
}

fn render_meters(frame: &mut Frame, app: &App, value: &CohortProviderEvaluation, area: Rect) {
    let rows = Layout::vertical([Constraint::Ratio(1, 5); 5]).split(area);
    let metrics = &value.readiness.metrics;
    let meters = [
        movement_meter(app, value),
        bbwp_meter(app, metrics),
        strength_meter(app, metrics),
        gap_meter(app, metrics),
        breakout_meter(app, metrics),
    ];
    for (row, (label, ratio, style)) in rows.iter().zip(meters) {
        crate::cohort_thick_meter::render(frame, app, *row, label, ratio, style);
    }
}

fn movement_meter(app: &App, value: &CohortProviderEvaluation) -> (String, Option<f64>, Style) {
    let label = value.confidence.map_or_else(
        || "MOVE STRENGTH N/A // NOT PROBABILITY".into(),
        |score| format!("MOVE STRENGTH {:.1}% // NOT PROBABILITY", score * 100.0),
    );
    meter(app, label, value.confidence, app.theme.cyan)
}

fn bbwp_meter(app: &App, metrics: &BTreeMap<String, Value>) -> (String, Option<f64>, Style) {
    let value = number(metrics, "regime_5m_bbwp_percentile");
    let threshold = number(metrics, "regime_bbwp_threshold_pct");
    let label = comparison_label("BBWP", value, threshold, "%", false, false);
    let style = comparison_style(app, value, threshold, true);
    meter(app, label, value.map(|number| number / 100.0), style)
}

fn strength_meter(app: &App, metrics: &BTreeMap<String, Value>) -> (String, Option<f64>, Style) {
    let value = number(metrics, "regime_5m_strength_percentile");
    let low = number(metrics, "regime_range_strength_threshold_pct");
    let high = number(metrics, "regime_trend_strength_threshold_pct");
    let label = match (value, low, high) {
        (Some(current), Some(range), Some(trend)) => {
            format!("TREND STRENGTH {current:.0}% // RANGE ≤{range:.0} TREND ≥{trend:.0}")
        }
        _ => "TREND STRENGTH N/A // THRESHOLDS UNAVAILABLE".into(),
    };
    meter(
        app,
        label,
        value.map(|number| number / 100.0),
        app.theme.carry,
    )
}

fn gap_meter(app: &App, metrics: &BTreeMap<String, Value>) -> (String, Option<f64>, Style) {
    let value = number(metrics, "regime_5m_ema_gap_bps");
    let threshold = number(metrics, "regime_minimum_gap_bps");
    let label = comparison_label("EMA GAP", value, threshold, "bps", true, true);
    let ratio = threshold_ratio(value.map(f64::abs), threshold);
    meter(
        app,
        label,
        ratio,
        comparison_style(app, value.map(f64::abs), threshold, true),
    )
}

fn breakout_meter(app: &App, metrics: &BTreeMap<String, Value>) -> (String, Option<f64>, Style) {
    let value = number(metrics, "regime_5m_breakout_volume_ratio");
    let threshold = number(metrics, "regime_breakout_volume_multiple");
    let label = comparison_label("BREAKOUT VOLUME", value, threshold, "x", false, false);
    meter(
        app,
        label,
        threshold_ratio(value, threshold),
        app.theme.gold,
    )
}

fn meter(
    _app: &App,
    label: String,
    ratio: Option<f64>,
    style: Style,
) -> (String, Option<f64>, Style) {
    (label, ratio, style)
}

fn render_footer(
    frame: &mut Frame,
    app: &App,
    symbol: &str,
    value: &CohortProviderEvaluation,
    area: Rect,
) {
    let metrics = &value.readiness.metrics;
    let lines = vec![
        cause_line(app, value, metrics),
        state_window_line(app, symbol, value),
        pressure_line(app, symbol, value),
    ];
    frame.render_widget(Paragraph::new(lines), area);
}

fn cause_line<'a>(
    app: &'a App,
    evaluation: &CohortProviderEvaluation,
    metrics: &BTreeMap<String, Value>,
) -> Line<'a> {
    let causes = active_causes(metrics);
    let why = if causes.is_empty() {
        "NO ACTIVE 5M CAUSE".into()
    } else {
        causes.join(" ")
    };
    let blocker = evaluation
        .readiness
        .blockers
        .first()
        .map_or("NO BLOCKER".into(), |value| {
            value.replace('_', " ").to_uppercase()
        });
    Line::from(Span::styled(
        format!("WHY RANGE {why}  //  NEXT {blocker}"),
        app.theme.coiling,
    ))
}

fn active_causes(metrics: &BTreeMap<String, Value>) -> Vec<String> {
    let mut causes = Vec::new();
    if boolean(metrics, "regime_5m_range_cause_filter") == Some(true) {
        causes.push(
            text(metrics, "regime_range_filter_name")
                .unwrap_or("FILTER")
                .to_uppercase(),
        );
    }
    for (key, label) in [
        ("regime_5m_range_cause_coiling", "COILING"),
        ("regime_5m_range_cause_strength", "WEAK"),
        ("regime_5m_range_cause_gap", "GAP"),
    ] {
        if boolean(metrics, key) == Some(true) {
            causes.push(label.into());
        }
    }
    causes
}

fn state_window_line<'a>(app: &'a App, symbol: &str, value: &CohortProviderEvaluation) -> Line<'a> {
    let (age, counts) = state_window(app, symbol, value);
    Line::from(format!(
        "STATE AGE {age} BAR(S)  //  RG{} TU{} TD{} BK{} TR{}",
        counts[0], counts[1], counts[2], counts[3], counts[4]
    ))
}

fn state_window(app: &App, symbol: &str, value: &CohortProviderEvaluation) -> (usize, [usize; 5]) {
    let values = app
        .backend
        .cohort
        .regime_history
        .iter()
        .filter(|item| item.symbol == symbol)
        .collect::<Vec<_>>();
    let current = value.primary_regime.as_deref().unwrap_or("UNKNOWN");
    let age = values
        .iter()
        .rev()
        .take_while(|item| item.primary_regime.as_deref() == Some(current))
        .count();
    let mut counts = [0; 5];
    for item in values {
        if let Some(index) = state_index(item.primary_regime.as_deref()) {
            counts[index] += 1;
        }
    }
    (age, counts)
}

fn pressure_line<'a>(app: &'a App, symbol: &str, value: &CohortProviderEvaluation) -> Line<'a> {
    let pressure = app.backend.cohort.books.get(symbol).map(|book| book.opi);
    let label = match pressure {
        Some(number) if number > 0.15 => "BID",
        Some(number) if number < -0.15 => "ASK",
        Some(_) => "BAL",
        None => "N/A",
    };
    let opi = pressure.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}"));
    Line::from(Span::styled(
        format!(
            "L2 OPI {opi} {label}  //  DECISION {}",
            fill_time(value.decision_time_ms)
        ),
        app.theme.muted,
    ))
}

fn comparison_label(
    label: &str,
    value: Option<f64>,
    threshold: Option<f64>,
    suffix: &str,
    absolute: bool,
    signed: bool,
) -> String {
    match (value, threshold) {
        (Some(current), Some(limit)) => {
            let compared = if absolute { current.abs() } else { current };
            let shown = if signed {
                format!("{current:+.1}")
            } else {
                format!("{current:.1}")
            };
            format!(
                "{label} {shown}{suffix} {} {limit:.1}{suffix}",
                if compared < limit { "<" } else { "≥" }
            )
        }
        _ => format!("{label} N/A // CANONICAL INPUT UNAVAILABLE"),
    }
}

fn comparison_style(
    app: &App,
    value: Option<f64>,
    threshold: Option<f64>,
    lower_active: bool,
) -> Style {
    match (value, threshold) {
        (Some(current), Some(limit)) if (current < limit) == lower_active => app.theme.coiling,
        (Some(_), Some(_)) => app.theme.cyan,
        _ => app.theme.muted,
    }
}

fn threshold_ratio(value: Option<f64>, threshold: Option<f64>) -> Option<f64> {
    match (value, threshold) {
        (Some(current), Some(limit)) if current.is_finite() && limit.is_finite() && limit > 0.0 => {
            Some(current / limit)
        }
        _ => None,
    }
}

fn state_index(state: Option<&str>) -> Option<usize> {
    match state {
        Some("RANGE") => Some(0),
        Some("TREND_UP") => Some(1),
        Some("TREND_DOWN") => Some(2),
        Some("BREAKOUT") => Some(3),
        Some("TRANSITION") => Some(4),
        _ => None,
    }
}

fn number(metrics: &BTreeMap<String, Value>, key: &str) -> Option<f64> {
    metrics.get(key).and_then(Value::as_f64)
}

fn boolean(metrics: &BTreeMap<String, Value>, key: &str) -> Option<bool> {
    metrics.get(key).and_then(Value::as_bool)
}

fn text<'a>(metrics: &'a BTreeMap<String, Value>, key: &str) -> Option<&'a str> {
    metrics.get(key).and_then(Value::as_str)
}

fn state_style(app: &App, state: &str) -> Style {
    match state {
        "TREND_UP" => app.theme.bull,
        "TREND_DOWN" => app.theme.bear,
        "BREAKOUT" => app.theme.cyan,
        "RANGE" => app.theme.coiling,
        "TRANSITION" => app.theme.carry,
        _ => app.theme.muted,
    }
}
