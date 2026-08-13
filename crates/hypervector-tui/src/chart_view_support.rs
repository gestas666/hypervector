//! Shared formatting and source-follow panel helpers for the chart screen.

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::Line,
    widgets::{Block, Borders, Paragraph},
};

use super::strategy_levels;
use crate::{
    app::App,
    chart_widgets::{StrategyLevel, price_bounds},
    model::RegimeSnapshot,
};

pub(super) fn previous_price(app: &App) -> Option<f64> {
    app.current_index
        .checked_sub(1)
        .and_then(|index| app.snapshots.get(index))
        .map(|snap| snap.price)
}

pub(super) fn change_style(app: &App, change_bps: f64) -> Style {
    if change_bps > 0.0 {
        app.theme.bull
    } else if change_bps < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

pub(super) fn position_style(app: &App) -> Style {
    match app.active_position.direction.as_str() {
        "LONG" => app.theme.bull,
        "SHORT" => app.theme.bear,
        _ => app.theme.muted,
    }
}

pub(super) fn pine_strategy_levels(app: &App) -> Vec<StrategyLevel> {
    let pine = &app.backend.pine_stack;
    let mut levels = Vec::new();
    if let Some(price) = pine.cs_trailing_stop {
        levels.push(level("CS-STOP", price, app.theme.coiling));
    }
    if let Some(price) = pine.trend_episode_high {
        levels.push(level("T-HI", price, app.theme.bear));
    }
    if let Some(price) = pine.trend_episode_low {
        levels.push(level("T-LO", price, app.theme.bull));
    }
    if let Some(price) = pine.trend_episode_mid {
        levels.push(level("T-MID", price, app.theme.carry));
    }
    levels
}

pub(super) fn level(label: &str, price: f64, style: Style) -> StrategyLevel {
    StrategyLevel {
        label: label.to_string(),
        price,
        style,
    }
}

pub(super) fn pine_state(value: Option<i64>) -> &'static str {
    match value {
        Some(1) => "BULL",
        Some(-1) => "BEAR",
        Some(0) => "NEUTRAL",
        _ => "N/A",
    }
}

pub(super) fn optional_oid(value: Option<u64>) -> String {
    value.map_or_else(|| "-".into(), |number| number.to_string())
}

pub(super) fn optional_money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.2}"))
}

pub(super) fn optional_quantity(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.6}"))
}

pub(super) fn render_source_follow_strategy_panel(
    f: &mut Frame,
    app: &App,
    candles: &[RegimeSnapshot],
    area: Rect,
) {
    let levels = level_line(&strategy_levels(app), price_bounds(candles));
    let lines = crate::source_follow_view::chart_lines(app, levels);
    let block = Block::default()
        .title(" BTC SOURCE-FOLLOW · BACKEND ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

pub(super) fn render_default_strategy_panel(
    f: &mut Frame,
    app: &App,
    candles: &[RegimeSnapshot],
    area: Rect,
) {
    let lines = default_strategy_lines(app, candles);
    let block = Block::default()
        .title(" STRATEGY LEVELS · BACKEND ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn default_strategy_lines(app: &App, candles: &[RegimeSnapshot]) -> Vec<Line<'static>> {
    let snap = app.current_snapshot();
    let levels = strategy_levels(app);
    vec![
        Line::from(format!(
            "ENTRY ELIGIBILITY  ELIGIBLE {}  │  STRUCT {}  │  SETUP {}  │  1m {}  │  5m {}  │  15m {}",
            direction_label(app.backend.entry_direction.as_deref(), "WAIT"),
            direction_label(app.backend.structural_direction.as_deref(), "NONE"),
            cross_label(app.backend.tactical_breakout_direction.as_deref()),
            snap.trend_1m,
            snap.trend_5m,
            snap.trend_15m
        )),
        Line::from(format!(
            "POSITION {}  │  U/PNL {:+.2}  │  ENTRY FEE ${:.2}  │  FUNDING ${:.2}",
            app.active_position.direction,
            app.paper_stats.unrealized_pnl,
            app.active_position.entry_fee_usd,
            app.active_position.funding_payment_usd
        )),
        Line::from(level_line(&levels, price_bounds(candles))),
        Line::from(format!(
            "BBWP {} {:.1}% <{}  │  GAP {}  │  RSI X {} {:.1}/{}",
            readiness_label(app.backend.compression_ready),
            snap.bbwp_percentile,
            optional_percent(app.backend.bbwp_compression_threshold),
            optional_bps(app.backend.ema_gap_bps_signed),
            cross_label(app.backend.rsi_cross_direction.as_deref()),
            snap.rsi,
            optional_number(app.backend.rsi_ema)
        )),
        Line::from(format!(
            "VOL {}  │  RANGE {}  │  SOURCE BACKEND ONLY",
            optional_ratio(app.backend.breakout_volume_ratio),
            range_label(app.backend.prior_range_low, app.backend.prior_range_high)
        )),
    ]
}

pub(super) fn render_hulk_smash_strategy_panel(
    f: &mut Frame,
    app: &App,
    candles: &[RegimeSnapshot],
    area: Rect,
) {
    let lines = hulk_smash_lines(app, candles);
    let block = Block::default()
        .title(" HULK SMASH · BACKEND ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn hulk_smash_lines(app: &App, candles: &[RegimeSnapshot]) -> Vec<Line<'static>> {
    let hulk = &app.backend.hulk_smash;
    let score = hulk
        .score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let minimum = hulk
        .minimum_score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let evidence = hulk.evidence.join(" + ").to_uppercase();
    let stop = optional_level_price(hulk.planned_stop_price);
    let target = optional_level_price(hulk.planned_target_price);
    let r = hulk
        .planned_target_r_multiple
        .map_or_else(|| "N/A".into(), |value| format!("{value:.1}R"));
    let trigger = hulk
        .trigger
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    vec![
        Line::from(format!(
            "30m SCORE {score}/{minimum} │ SHORT ONLY │ REGIME NOT CLASSIFIED"
        )),
        Line::from(format!("TRIGGER {trigger} │ EVIDENCE {evidence}")),
        Line::from(format!(
            "POSITION {} │ U/PNL {:+.2} │ ENTRY FEE ${:.2} │ FUNDING ${:.2}",
            app.active_position.direction,
            app.paper_stats.unrealized_pnl,
            app.active_position.entry_fee_usd,
            app.active_position.funding_payment_usd
        )),
        Line::from(level_line(&strategy_levels(app), price_bounds(candles))),
        Line::from(format!(
            "STOP {stop} │ TARGET {target} │ {r} │ MAX HOLD 48 bars"
        )),
    ]
}

fn optional_level_price(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |price| format!("${price:.2}"))
}

pub(super) fn direction_label<'a>(direction: Option<&'a str>, fallback: &'a str) -> &'a str {
    match direction {
        Some("long") => "LONG",
        Some("short") => "SHORT",
        Some(value) => value,
        None => fallback,
    }
}

pub(super) fn readiness_label(ready: Option<bool>) -> &'static str {
    match ready {
        Some(true) => "READY",
        Some(false) => "WAIT",
        None => "N/A",
    }
}

pub(super) fn cross_label(direction: Option<&str>) -> &'static str {
    match direction {
        Some("BK_UPWARD") => "UP",
        Some("BK_DOWNWARD") => "DOWN",
        _ => "NONE",
    }
}

pub(super) fn optional_number(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1}"))
}

pub(super) fn optional_percent(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1}%"))
}

pub(super) fn optional_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.1}bps"))
}

pub(super) fn optional_ratio(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}x"))
}

pub(super) fn range_label(low: Option<f64>, high: Option<f64>) -> String {
    match (low, high) {
        (Some(low), Some(high)) => format!("${low:.2}-${high:.2}"),
        _ => "N/A".into(),
    }
}

pub(super) fn level_line(levels: &[StrategyLevel], bounds: Option<(f64, f64)>) -> String {
    if levels.is_empty() {
        return "LEVELS ENTRY N/A  │  TP N/A  │  LIQ N/A  │  MAKER N/A".to_string();
    }
    levels
        .iter()
        .map(|level| {
            let edge = edge_badge(level.price, bounds);
            format!("{} ${:.2}{edge}", level.label, level.price)
        })
        .collect::<Vec<_>>()
        .join("  │  ")
}

fn edge_badge(price: f64, bounds: Option<(f64, f64)>) -> &'static str {
    match bounds {
        Some((low, _)) if price < low => " ↓ OFFSCREEN",
        Some((_, high)) if price > high => " ↑ OFFSCREEN",
        _ => "",
    }
}
