//! Inventory and execution-quality panels for the Apex MM backend view.

use crate::{
    apex_mm_format::{
        active_entry, bps, json_number, millis, money, oid, percent, percent_fraction,
        position_margin,
    },
    apex_mm_view::render_paragraph,
    app::App,
};
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::Line,
};

pub(crate) fn render_inventory(f: &mut Frame, app: &App, area: Rect) {
    let mut lines = inventory_position_lines(app);
    lines.extend(inventory_execution_lines(app));
    render_paragraph(f, app, area, " NET INVENTORY & LOSS RESPONSE ", lines);
}

fn inventory_position_lines(app: &App) -> Vec<Line<'static>> {
    let mm = &app.backend.apex_mm;
    let signed = signed_position(app);
    let cap = json_number(&app.backend.risk, "max_inventory_notional_usd");
    let mark = app.backend.book.as_ref().map(|book| book.mid_price);
    vec![
        Line::from(format!(
            "SIGNED SIZE {signed:+.6} {}  |  SIDE {}  |  LEVERAGE {:.1}x ISOLATED",
            app.symbol, app.active_position.direction, app.active_position.leverage
        )),
        Line::from(format!(
            "ENTRY {}  |  MARK {}  |  U/PNL {:+.4} USD",
            money(active_entry(app)),
            money(mark),
            app.paper_stats.unrealized_pnl
        )),
        Line::from(format!(
            "INVENTORY {} / {} CAP  |  UTIL {}  |  ONE-WAY NET",
            money(mm.inventory_notional_usd),
            money(cap),
            percent_fraction(mm.inventory_utilization)
        )),
        Line::from(format!(
            "LIQ PRICE {}  |  LIQ DIST {}  |  MARGIN {}",
            money(app.active_position.liquidation_price),
            percent(mm.liquidation_distance_pct),
            money(position_margin(app))
        )),
    ]
}

fn inventory_execution_lines(app: &App) -> Vec<Line<'static>> {
    let mm = &app.backend.apex_mm;
    let started = mm
        .quote_started_at_ms
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    vec![
        Line::from(format!(
            "FEES ${:.4}  |  FUNDING {:+.4} USD  |  QUOTE START {started}",
            mm.total_fee_usd, mm.total_funding_usd
        )),
        Line::from(format!(
            "BID OID {}  |  ASK OID {}  |  POSITION LIMIT: ONE PER SYMBOL",
            oid(mm.bid_oid),
            oid(mm.ask_oid)
        )),
        Line::from("IF BID FILLS: LONG -> FAVOR SELL  |  IF ASK FILLS: SHORT -> FAVOR BUY"),
        Line::from(
            "LOSS RESPONSE: SKEW EXIT QUOTE; NO FIXED TP; CAP BREACH -> CANCEL + FLATTEN + FAULT",
        ),
    ]
}

fn signed_position(app: &App) -> f64 {
    app.backend.apex_mm.position_size_signed.unwrap_or_else(|| {
        if app.active_position.direction == "SHORT" {
            -app.active_position.size_btc
        } else {
            app.active_position.size_btc
        }
    })
}

pub(crate) fn render_measurements(f: &mut Frame, app: &App, area: Rect) {
    let panels = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(34),
            Constraint::Percentage(33),
            Constraint::Percentage(33),
        ])
        .split(area);
    render_execution_counts(f, app, panels[0]);
    render_fill_costs(f, app, panels[1]);
    render_quality_risk(f, app, panels[2]);
}

fn render_execution_counts(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let lines = vec![
        Line::from(format!(
            "QUOTES {}  |  INTENTS {}  |  ACKS {}",
            mm.quote_observations, mm.order_intents, mm.acknowledgement_count
        )),
        Line::from(format!(
            "ACCEPTED {}  |  REJECTED {}  |  FAULTS {}",
            mm.accepted_count, mm.rejected_count, mm.fault_count
        )),
    ];
    render_paragraph(f, app, area, " EXECUTION COUNTS ", lines);
}

fn render_fill_costs(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let lines = vec![
        Line::from(format!(
            "MAKER FILLS {}  |  TAKER FILLS {}",
            mm.maker_fill_count, mm.taker_fill_count
        )),
        Line::from(format!(
            "FILLS {}  |  FEES ${:.4}  |  FUNDING {:+.4}",
            mm.fill_count, mm.total_fee_usd, mm.total_funding_usd
        )),
    ];
    render_paragraph(f, app, area, " FILLS & COSTS ", lines);
}

fn render_quality_risk(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let lines = vec![
        Line::from(format!(
            "MARKOUT {}  |  SLIPPAGE {}",
            bps(mm.latest_markout_bps),
            bps(mm.latest_slippage_bps)
        )),
        Line::from(format!(
            "ACK {}  |  LIQ DIST {}",
            millis(mm.latest_ack_latency_ms),
            percent(mm.liquidation_distance_pct)
        )),
    ];
    render_paragraph(f, app, area, " QUALITY & RISK ", lines);
}
