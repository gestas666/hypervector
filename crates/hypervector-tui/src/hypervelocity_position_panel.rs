//! Active-position telemetry and lifecycle presentation.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use super::hypervelocity_order_book::render_book_ladder;
use super::{backend_exit_display, backend_number};
use crate::animation;
use crate::app::App;

const COMPACT_ACTIVE_POSITION_HEIGHT: u16 = 10;
const COMPACT_POSITION_SPLIT_WIDTH: u16 = 140;

// ============================================================================
// ROW 2: Active Position PnL + L2 Orderbook Depth Ladder (side by side)
// ============================================================================
pub fn render_position_and_book(f: &mut Frame, app: &App, area: Rect) {
    let position_percentage = if area.width < COMPACT_POSITION_SPLIT_WIDTH {
        60
    } else {
        50
    };
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(position_percentage),
            Constraint::Percentage(100 - position_percentage),
        ])
        .split(area);

    render_position_panel(f, app, chunks[0]);
    render_book_ladder(f, app, chunks[1]);
}

fn render_position_panel(f: &mut Frame, app: &App, area: Rect) {
    if !app.active_position.is_active() {
        crate::flat_readiness::render_flat_readiness(f, app, area);
        return;
    }
    if area.height < COMPACT_ACTIVE_POSITION_HEIGHT {
        render_compact_position_panel(f, app, area);
        return;
    }

    let metrics = position_panel_metrics(app);
    let mut text = position_panel_lines(app, &metrics);
    if let Some(lifecycle) = live_lifecycle_display(app) {
        text.push(Line::from(vec![Span::styled(lifecycle, app.theme.gold)]));
    }
    let block = Block::default()
        .title(" ACTIVE POSITION ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(metrics.direction_style);
    f.render_widget(Paragraph::new(text).block(block), area);
}

struct PositionPanelMetrics {
    direction: &'static str,
    direction_style: Style,
    leverage: f64,
    entry_price: f64,
    size: f64,
    mark_price: f64,
    target_display: String,
    exit_display: String,
    margin_pct: f64,
    peak_pct: f64,
    unrealized_pnl: f64,
    margin_bar: Vec<Span<'static>>,
    peak_bar: Vec<Span<'static>>,
    fee_display: String,
    exposure_display: String,
    liquidation_display: String,
}

fn position_panel_metrics(app: &App) -> PositionPanelMetrics {
    let pos = &app.active_position;
    let mark_price = active_mark_price(app);
    let (direction, direction_style) = position_direction(app);
    let (chart_target, target_display) = target_margin_display(app);
    let (margin_pct, peak_pct, unrealized_pnl) = position_returns(app, mark_price);
    let (margin_bar, peak_bar) = margin_bars(app, margin_pct, peak_pct, chart_target);
    PositionPanelMetrics {
        direction,
        direction_style,
        leverage: pos.leverage,
        entry_price: pos.entry_price,
        size: pos.size_btc,
        mark_price,
        target_display,
        exit_display: backend_exit_display(app),
        margin_pct,
        peak_pct,
        unrealized_pnl,
        margin_bar,
        peak_bar,
        fee_display: position_fee_display(app),
        exposure_display: position_exposure_display(app),
        liquidation_display: position_liquidation_display(app, mark_price),
    }
}

fn position_direction(app: &App) -> (&'static str, Style) {
    if app.active_position.direction == "LONG" {
        ("▲ LONG", app.theme.bull)
    } else {
        ("▼ SHORT", app.theme.bear)
    }
}

fn target_margin_display(app: &App) -> (f64, String) {
    let target = backend_number(&app.backend.strategy_params, "target_margin_pct");
    let chart_target = target.unwrap_or(100.0).max(0.01);
    let gross = app
        .backend
        .exits
        .get("target_basis")
        .and_then(serde_json::Value::as_str)
        == Some("gross_margin_return_before_fees_and_funding");
    let display = target
        .map(|value| match gross {
            true => format!("{value:.2}% GROSS"),
            false => format!("{value:.2}%"),
        })
        .unwrap_or_else(|| "n/a".to_string());
    (chart_target, display)
}

fn position_returns(app: &App, mark_price: f64) -> (f64, f64, f64) {
    let pos = &app.active_position;
    let margin = if pos.direction == "LONG" {
        (mark_price - pos.entry_price) / pos.entry_price * pos.leverage * 100.0
    } else {
        (pos.entry_price - mark_price) / pos.entry_price * pos.leverage * 100.0
    };
    let rounded_margin = (margin * 100.0).round() / 100.0;
    (
        rounded_margin,
        rounded_margin.max(pos.peak_margin_pct),
        app.paper_stats.unrealized_pnl,
    )
}

fn margin_bars(
    app: &App,
    margin_pct: f64,
    peak_pct: f64,
    chart_target: f64,
) -> (Vec<Span<'static>>, Vec<Span<'static>>) {
    let width = 40usize;
    let filled = ((margin_pct.abs() / chart_target).min(1.0) * width as f64) as usize;
    let peak_filled = ((peak_pct.abs() / chart_target).min(1.0) * width as f64) as usize;
    let mut margin_bar = Vec::with_capacity(width);
    let mut peak_bar = Vec::with_capacity(width);
    for index in 0..width {
        let zone = index as f64 / width as f64 * chart_target;
        let margin_char = if index < filled.min(width) {
            '█'
        } else {
            '░'
        };
        let peak_char = if index < peak_filled.min(width) {
            '▒'
        } else {
            ' '
        };
        margin_bar.push(Span::styled(
            margin_char.to_string(),
            Style::default().fg(animation::gradient_color(zone, app.tick_count)),
        ));
        peak_bar.push(Span::styled(
            peak_char.to_string(),
            Style::default().fg(animation::gradient_color(zone, 0)),
        ));
    }
    (margin_bar, peak_bar)
}

fn position_fee_display(app: &App) -> String {
    let pos = &app.active_position;
    let payment = if pos.funding_payment_usd.abs() < 0.005 {
        0.0
    } else {
        pos.funding_payment_usd
    };
    let funding = funding_cashflow_display(app, payment);
    if app.backend.is_source_follow() {
        format!(
            "ENTRY FEE PAID ${:.2}  |  {}  |  EST TP MAKER FEE ${:.2}",
            pos.entry_fee_usd, funding, pos.estimated_exit_fee_usd
        )
    } else {
        format!(
            "ENTRY FEE PAID ${:.2}  |  {}  |  EST EXIT FEE ${:.2}",
            pos.entry_fee_usd, funding, pos.estimated_exit_fee_usd
        )
    }
}

fn position_exposure_display(app: &App) -> String {
    let pos = &app.active_position;
    let notional = pos.entry_price * pos.size_btc;
    let margin = if pos.leverage > 0.0 {
        notional / pos.leverage
    } else {
        0.0
    };
    let target =
        active_target_price(app).map_or_else(|| "N/A".into(), |price| format!("${price:.2}"));
    format!("EXPOSURE MARGIN ${margin:.2} | NOTIONAL ${notional:.2} | TP {target} | ISOLATED")
}

fn position_liquidation_display(app: &App, mark_price: f64) -> String {
    let pos = &app.active_position;
    pos.liquidation_price.map_or_else(
        || "LIQ PRICE  UNAVAILABLE  |  SOURCE BACKEND TELEMETRY MISSING".to_string(),
        |price| {
            format!(
                "LIQ PRICE  ${price:.2}  |  LIQ DIST {}  |  SOURCE  BACKEND ISOLATED",
                liquidation_distance(&pos.direction, mark_price, price)
            )
        },
    )
}

fn position_panel_lines(app: &App, metrics: &PositionPanelMetrics) -> Vec<Line<'static>> {
    vec![
        position_identity_line(app, metrics),
        Line::from(vec![Span::raw("")]),
        position_margin_line(app, metrics),
        position_peak_line(app, metrics),
        position_summary_line(app, metrics),
        Line::from(vec![Span::styled(
            metrics.fee_display.clone(),
            app.theme.cyan,
        )]),
        Line::from(vec![Span::styled(
            metrics.exposure_display.clone(),
            app.theme.gold,
        )]),
        Line::from(vec![Span::styled(
            metrics.liquidation_display.clone(),
            app.theme.cyan,
        )]),
    ]
}

fn position_identity_line(app: &App, metrics: &PositionPanelMetrics) -> Line<'static> {
    Line::from(vec![
        Span::raw("SIZE  "),
        Span::styled(
            format!("{:.5} {}", metrics.size, app.symbol),
            app.theme.gold,
        ),
        Span::raw("  │  ENTRY  "),
        Span::styled(format!("${:.2}", metrics.entry_price), app.theme.title),
        Span::raw("  │  MARK  "),
        Span::styled(format!("${:.2}", metrics.mark_price), app.theme.gold),
        Span::raw("  "),
        Span::styled(metrics.direction, metrics.direction_style),
    ])
}

fn position_margin_line(app: &App, metrics: &PositionPanelMetrics) -> Line<'static> {
    let mut parts = vec![Span::raw("MARGIN  ")];
    parts.extend(metrics.margin_bar.clone());
    parts.push(Span::styled(
        format!("  {:.2}% / {}", metrics.margin_pct, metrics.target_display),
        app.theme.gold,
    ));
    Line::from(parts)
}

fn position_peak_line(app: &App, metrics: &PositionPanelMetrics) -> Line<'static> {
    let mut parts = vec![Span::raw("PEAK    ")];
    parts.extend(metrics.peak_bar.clone());
    parts.push(Span::styled(
        format!("  peak {:.2}%", metrics.peak_pct),
        app.theme.bar_ghost,
    ));
    Line::from(parts)
}

fn position_summary_line(app: &App, metrics: &PositionPanelMetrics) -> Line<'static> {
    let sign = if metrics.unrealized_pnl >= 0.0 {
        "+"
    } else {
        "-"
    };
    Line::from(vec![Span::styled(
        format!(
            "U/PNL {}{:.2}  │  TARGET {}  │  EXIT {}  │  {:.1}x LEV",
            sign,
            metrics.unrealized_pnl.abs(),
            metrics.target_display,
            metrics.exit_display,
            metrics.leverage,
        ),
        app.theme.muted,
    )])
}

fn render_compact_position_panel(f: &mut Frame, app: &App, area: Rect) {
    let pos = &app.active_position;
    let mark = active_mark_price(app);
    let target =
        active_target_price(app).map_or_else(|| "N/A".into(), |price| format!("${price:.2}"));
    let liquidation = pos.liquidation_price.map_or_else(
        || "N/A".into(),
        |price| {
            format!(
                "${price:.2} ({})",
                liquidation_distance(&pos.direction, mark, price)
            )
        },
    );
    let notional = pos.entry_price * pos.size_btc;
    let margin = if pos.leverage > 0.0 {
        notional / pos.leverage
    } else {
        0.0
    };
    let lines = vec![
        Line::from(format!(
            "{} {:.5} {} | ENTRY ${:.2} | MARK ${mark:.2} | {:.1}x",
            pos.direction, pos.size_btc, app.symbol, pos.entry_price, pos.leverage
        )),
        Line::from(format!(
            "U/PNL {:+.2} | TP {target} | LIQ {liquidation}",
            app.paper_stats.unrealized_pnl
        )),
        Line::from(format!(
            "MARGIN ${margin:.2} | NOTIONAL ${notional:.2} | FEES ${:.2} + EST ${:.2}",
            pos.entry_fee_usd, pos.estimated_exit_fee_usd
        )),
    ];
    let style = if pos.direction == "LONG" {
        app.theme.bull
    } else {
        app.theme.bear
    };
    let block = Block::default()
        .title(" ACTIVE POSITION ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(style);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn active_mark_price(app: &App) -> f64 {
    app.active_position
        .mark_price
        .or_else(|| app.backend.book.as_ref().map(|book| book.mid_price))
        .unwrap_or_else(|| app.current_snapshot().price)
}

fn active_target_price(app: &App) -> Option<f64> {
    app.backend
        .target_order_price
        .or_else(|| app.backend.active_target_prices.first().copied())
}

fn liquidation_distance(direction: &str, mark: f64, liquidation: f64) -> String {
    if mark <= 0.0 {
        return "N/A".into();
    }
    let distance = if direction == "LONG" {
        (mark - liquidation) / mark * 100.0
    } else {
        (liquidation - mark) / mark * 100.0
    };
    format!("{distance:.2}%")
}

fn funding_cashflow_display(app: &App, funding_payment: f64) -> String {
    let is_live_delta = app.backend.execution_mode.as_deref() == Some("live");
    let paid = if is_live_delta {
        funding_payment <= 0.0
    } else {
        funding_payment >= 0.0
    };
    if paid {
        format!("FUNDING PAID ${:.2}", funding_payment.abs())
    } else {
        format!("FUNDING RECEIVED ${:.2}", funding_payment.abs())
    }
}

fn live_lifecycle_display(app: &App) -> Option<String> {
    let state = app.backend.live_state.as_deref()?;
    let protection = target_lifecycle_display(app).unwrap_or_else(|| stop_lifecycle_display(app));
    let authority = app
        .backend
        .execution_authority
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let fault = app
        .backend
        .latest_fault
        .as_deref()
        .map_or_else(String::new, |value| format!("  │  FAULT {value}"));
    Some(format!(
        "LIFECYCLE {state}  │  {protection}  │  AUTH {authority}{fault}"
    ))
}

fn target_lifecycle_display(app: &App) -> Option<String> {
    match (
        app.backend.target_order_price,
        app.backend.target_order_oid,
        app.backend.target_order_status.as_deref(),
    ) {
        (Some(price), Some(oid), Some(status)) => {
            Some(format!("TARGET ${price:.2} OID {oid} {status}"))
        }
        (_, Some(oid), Some(status)) => Some(format!("TARGET OID {oid} {status}")),
        _ => None,
    }
}

fn stop_lifecycle_display(app: &App) -> String {
    match (
        app.backend.protective_stop_price,
        app.backend.protective_stop_oid,
        app.backend.protective_stop_status.as_deref(),
    ) {
        (Some(price), Some(oid), Some(status)) => {
            format!("STOP ${price:.2} OID {oid} {status}")
        }
        (_, Some(oid), Some(status)) => format!("STOP OID {oid} {status}"),
        _ => "STOP NOT CONFIRMED".to_string(),
    }
}
