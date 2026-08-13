//! Backend-specific policy summaries and registered-strategy matrix.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Row, Table},
};

use super::dashboard::backend_f64;
use crate::{app::App, backend_telemetry::BackendConnectionState};

pub(super) fn render_specialized_policy(f: &mut Frame, app: &App, area: Rect) -> bool {
    if app.backend.is_apex_mm() {
        render_apex_mm_policy_panel(f, app, area);
    } else if app.backend.is_source_follow() {
        render_source_follow_policy_panel(f, app, area);
    } else if app.backend.is_pine_stack() {
        render_pine_stack_policy_panel(f, app, area);
    } else if app.backend.is_hulk_smash() {
        render_hulk_smash_policy_panel(f, app, area);
    } else {
        return false;
    }
    true
}

fn render_pine_stack_policy_panel(f: &mut Frame, app: &App, area: Rect) {
    let pine = &app.backend.pine_stack;
    let action = app
        .backend
        .latest_decision_action
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let lines = vec![
        Line::from("30m COMPLETED-BAR OBSERVER │ ZERO CAPITAL │ NO ORDERS"),
        Line::from(format!(
            "CS {} │ TREND {} │ SENTIMENT {} / 100",
            pine.cs_state
                .map_or("N/A".into(), |value| value.to_string()),
            pine.trend_state
                .map_or("N/A".into(), |value| value.to_string()),
            pine.sentiment_score
                .map_or("N/A".into(), |value| format!("{value:.1}"))
        )),
        Line::from(format!("LAST ACTION {action} │ REGIME NOT CLASSIFIED")),
        Line::from("HISTORICAL PSEUDO-HOLDOUT FAILED │ FRESH FORWARD EVIDENCE ONLY"),
    ];
    render_policy_block(f, app, area, " FOUR-PINE OBSERVER POLICY ", lines);
}

fn render_apex_mm_policy_panel(f: &mut Frame, app: &App, area: Rect) {
    render_policy_block(
        f,
        app,
        area,
        " APEX MM LIVE EXECUTION MEASUREMENT ",
        apex_mm_policy_lines(app),
    );
}

fn apex_mm_policy_lines(app: &App) -> Vec<Line<'static>> {
    let mm = &app.backend.apex_mm;
    let state = app.backend.live_state.as_deref().unwrap_or("NOT REPORTED");
    let cap = backend_f64(&app.backend.risk, "max_inventory_notional_usd").unwrap_or(0.0);
    let base = backend_f64(&app.backend.strategy_params, "base_order_notional_usd").unwrap_or(0.0);
    let maker = backend_f64(&app.backend.costs, "maker_fee_rate").unwrap_or(0.0);
    let markout = formatted_optional(mm.latest_markout_bps, "{:+.2} bps", "awaiting fill");
    let slippage = formatted_optional(mm.latest_slippage_bps, "{:+.2} bps", "awaiting fill");
    let liquidation = formatted_optional(mm.liquidation_distance_pct, "{:.2}%", "flat");
    let latency = mm
        .latest_ack_latency_ms
        .map_or_else(|| "awaiting ACK".into(), |v| format!("{v}ms"));
    vec![
        Line::from(format!(
            "LIFECYCLE {state} │ QUOTE {} │ 3x ISOLATED",
            if mm.quote_active == Some(true) {
                "ACTIVE"
            } else {
                "WITHHELD"
            }
        )),
        Line::from(format!(
            "BID {} │ ASK {}",
            mm_quote_leg(mm.bid_oid, mm.bid_price, mm.bid_size),
            mm_quote_leg(mm.ask_oid, mm.ask_price, mm.ask_size)
        )),
        Line::from(format!(
            "INVENTORY ${:.2} / ${cap:.2} CAP │ BASE ${base:.2} │ LIQ DIST {liquidation}",
            mm.inventory_notional_usd.unwrap_or(0.0).abs()
        )),
        Line::from(format!(
            "1s MARKOUT {markout} │ SLIP {slippage} │ ACK {latency} │ MAKER {:.3}%",
            maker * 100.0
        )),
    ]
}

fn formatted_optional(value: Option<f64>, pattern: &str, missing: &str) -> String {
    value.map_or_else(
        || missing.into(),
        |value| match pattern {
            "{:+.2} bps" => format!("{value:+.2} bps"),
            _ => format!("{value:.2}%"),
        },
    )
}

fn mm_quote_leg(oid: Option<u64>, price: Option<f64>, size: Option<f64>) -> String {
    format!(
        "#{} ${:.0} {:.5} BTC",
        oid.map_or_else(|| "-".into(), |value| value.to_string()),
        price.unwrap_or(0.0),
        size.unwrap_or(0.0)
    )
}

fn render_source_follow_policy_panel(f: &mut Frame, app: &App, area: Rect) {
    let lines = crate::source_follow_view::policy_lines(app, area.width, area.height);
    render_policy_block(f, app, area, " BTC SOURCE-FOLLOW POLICY & RISK ", lines);
}

fn render_hulk_smash_policy_panel(f: &mut Frame, app: &App, area: Rect) {
    let hulk = &app.backend.hulk_smash;
    let score = hulk
        .score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let minimum = hulk
        .minimum_score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let trigger = hulk
        .trigger
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let stop = hulk
        .planned_stop_price
        .map_or_else(|| "N/A".into(), |value| format!("${value:.2}"));
    let target = hulk
        .planned_target_price
        .map_or_else(|| "N/A".into(), |value| format!("${value:.2}"));
    let lines = vec![
        Line::from(format!(
            "30m SCORE {score}/{minimum} │ SHORT ONLY │ TRIGGER {trigger}"
        )),
        Line::from("COMPLETED-BAR SIGNAL │ NEXT-BAR EXECUTION │ REGIME NOT CLASSIFIED"),
        Line::from(format!(
            "PLANNED STOP {stop} │ TARGET {target} │ 3R │ 5x ISOLATED"
        )),
        Line::from("0.25% EQUITY RISK │ STOP 20-75 bps │ MAX HOLD 48 bars"),
    ];
    render_policy_block(f, app, area, " HULK SMASH SIGNAL & RISK CONTRACT ", lines);
}

fn render_policy_block(
    f: &mut Frame,
    app: &App,
    area: Rect,
    title: &'static str,
    lines: Vec<Line<'static>>,
) {
    let block = Block::default()
        .title(title)
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

pub(super) fn render_registered_strategy_matrix(f: &mut Frame, app: &App, area: Rect) {
    let row = strategy_row(app);
    let table = Table::new(
        vec![row],
        [
            Constraint::Length(26),
            Constraint::Length(24),
            Constraint::Length(14),
            Constraint::Length(14),
            Constraint::Min(30),
        ],
    )
    .header(strategy_header(app))
    .block(
        Block::default()
            .title(" BACKEND STRATEGY EXECUTION TELEMETRY ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );
    f.render_widget(table, area);
}

fn strategy_header(app: &App) -> Row<'static> {
    Row::new(
        [
            "Backend Strategy",
            "Telemetry",
            "Model p",
            "Leverage",
            "Authoritative Run Identity",
        ]
        .into_iter()
        .map(|value| Span::styled(value, app.theme.header)),
    )
}

fn strategy_row(app: &App) -> Row<'static> {
    let state = connection_label(app);
    let strategy = app
        .backend
        .strategy_name
        .as_deref()
        .unwrap_or("unknown")
        .to_string();
    let probability = app
        .backend
        .latest_metalabel_p
        .map_or_else(|| "n/a".into(), |value| format!("{value:.4}"));
    let leverage = app
        .backend
        .strategy_params
        .get("leverage")
        .and_then(serde_json::Value::as_f64)
        .map_or_else(|| "n/a".into(), |value| format!("{value:.1}x"));
    let telemetry = if app.backend.is_apex_mm() {
        format!(
            "{state} {}",
            app.backend.live_state.as_deref().unwrap_or("STARTING")
        )
    } else {
        state.into()
    };
    Row::new(vec![
        Span::styled(strategy, app.theme.gold),
        Span::styled(telemetry, app.theme.cyan),
        Span::styled(probability, app.theme.gold),
        Span::styled(leverage, app.theme.cyan),
        Span::styled(run_identity(app), app.theme.title),
    ])
}

fn connection_label(app: &App) -> &'static str {
    match app.backend.connection {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    }
}

fn run_identity(app: &App) -> String {
    if app.backend.is_apex_mm() {
        return apex_mm_run_identity(app);
    }
    format!(
        "run={} | profile={} | execution={} | metalabel={}",
        app.backend.run_id.as_deref().unwrap_or("unknown"),
        app.backend.profile_id.as_deref().unwrap_or("unreported"),
        app.backend.execution_mode.as_deref().unwrap_or("unknown"),
        app.backend.metalabel_mode.as_deref().unwrap_or("off"),
    )
}

fn apex_mm_run_identity(app: &App) -> String {
    let mm = &app.backend.apex_mm;
    let markout = mm
        .latest_markout_bps
        .map_or_else(|| "n/a".into(), |value| format!("{value:+.2}bps"));
    format!(
        "run={} | BID #{} ${:.0} | ASK #{} ${:.0} | INV ${:.2} | 1s {markout}",
        app.backend.run_id.as_deref().unwrap_or("unknown"),
        mm.bid_oid
            .map_or_else(|| "-".into(), |value| value.to_string()),
        mm.bid_price.unwrap_or(0.0),
        mm.ask_oid
            .map_or_else(|| "-".into(), |value| value.to_string()),
        mm.ask_price.unwrap_or(0.0),
        mm.inventory_notional_usd.unwrap_or(0.0).abs(),
    )
}
