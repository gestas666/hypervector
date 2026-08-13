//! Screen 3 orchestration for backend-authored candles and strategy telemetry.

#[path = "chart_view_support.rs"]
mod support;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use crate::{
    app::App,
    chart_widgets::{
        CandlePane, RegimeTape, StrategyLevel, VolumePane, price_bounds, visible_candles,
    },
    model::RegimeSnapshot,
};
use support::{
    change_style, direction_label, level, level_line, optional_bps, optional_money,
    optional_number, optional_oid, optional_quantity, pine_state, pine_strategy_levels,
    position_style, previous_price, render_default_strategy_panel,
    render_hulk_smash_strategy_panel, render_source_follow_strategy_panel,
};

/// Render backend OHLCV candles with report-only Hypervelocity overlays.
pub fn render_backend_chart(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(9),
            Constraint::Length(5),
            Constraint::Length(3),
            Constraint::Length(7),
        ])
        .split(area);
    let candles = visible_candles(app, chunks[1].width);
    let levels = strategy_levels(app);
    render_market_summary(f, app, chunks[0]);
    f.render_widget(CandlePane::new(candles, &levels, &app.theme), chunks[1]);
    f.render_widget(VolumePane::new(candles, &app.theme), chunks[2]);
    if app.backend.is_apex_mm() {
        render_mm_state_tape(f, app, chunks[3]);
    } else {
        f.render_widget(RegimeTape::new(candles, &app.theme), chunks[3]);
    }
    render_strategy_panel(f, app, candles, chunks[4]);
}

fn render_market_summary(f: &mut Frame, app: &App, area: Rect) {
    if app.backend.is_apex_mm() {
        render_mm_market_summary(f, app, area);
        return;
    }
    if app.backend.is_pine_stack() {
        render_pine_market_summary(f, app, area);
        return;
    }
    let snap = app.current_snapshot();
    let previous = previous_price(app).unwrap_or(snap.price);
    let change_bps = if previous > 0.0 {
        (snap.price / previous - 1.0) * 10_000.0
    } else {
        0.0
    };
    let line = Line::from(vec![
        Span::styled(
            format!("{} {}  ", app.symbol, app.timeframe),
            app.theme.gold,
        ),
        Span::styled(
            format!("${:.2}  {change_bps:+.1} bps", snap.price),
            change_style(app, change_bps),
        ),
        Span::raw(format!(
            "  │  5m {}  │  15m {}  │  ",
            snap.trend_5m, snap.trend_15m
        )),
        Span::styled(app.active_position.direction.clone(), position_style(app)),
    ]);
    let block = Block::default()
        .title(" BACKEND CANDLE TAPE · READ ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(line).block(block), area);
}

fn render_pine_market_summary(f: &mut Frame, app: &App, area: Rect) {
    let snap = app.current_snapshot();
    let previous = previous_price(app).unwrap_or(snap.price);
    let change_bps = if previous > 0.0 {
        (snap.price / previous - 1.0) * 10_000.0
    } else {
        0.0
    };
    let pine = &app.backend.pine_stack;
    let line = Line::from(vec![
        Span::styled(format!("{} 30m  ", app.symbol), app.theme.gold),
        Span::styled(
            format!("${:.2}  {change_bps:+.1} bps", snap.price),
            change_style(app, change_bps),
        ),
        Span::raw(format!(
            "  │  CS {}  │  TREND {}  │  REGIME NOT CLASSIFIED  │  OBSERVE ONLY",
            pine_state(pine.cs_state),
            pine_state(pine.trend_state)
        )),
    ]);
    let block = Block::default()
        .title(" ETH 30m COMPLETED-BAR TAPE · BACKEND READ ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(line).block(block), area);
}

fn render_mm_market_summary(f: &mut Frame, app: &App, area: Rect) {
    let book = app.backend.book.as_ref();
    let line = Line::from(vec![
        Span::styled(format!("{} L2  ", app.symbol), app.theme.gold),
        Span::styled(
            book.map_or_else(
                || "MID N/A".into(),
                |value| format!("MID ${:.2}", value.mid_price),
            ),
            app.theme.cyan,
        ),
        Span::raw(book.map_or_else(
            || "  |  SPREAD N/A  |  PRESSURE N/A".into(),
            |value| {
                format!(
                    "  |  SPREAD {:.2} bps  |  PRESSURE {:+.2}",
                    value.spread_bps, value.opi
                )
            },
        )),
        Span::raw(format!("  |  INVENTORY {}", app.active_position.direction)),
    ]);
    let block = Block::default()
        .title(" LIVE L2 MIDPOINT TAPE · READ ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(line).block(block), area);
}

fn render_mm_state_tape(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let line = Line::from(format!(
        "REGIME NOT USED  |  QUOTES {}  |  STATE {}  |  BID #{}  |  ASK #{}",
        if mm.quote_active == Some(true) {
            "ACTIVE"
        } else {
            "WITHHELD"
        },
        app.backend.live_state.as_deref().unwrap_or("UNKNOWN"),
        mm.bid_oid
            .map_or_else(|| "-".into(), |value| value.to_string()),
        mm.ask_oid
            .map_or_else(|| "-".into(), |value| value.to_string())
    ));
    let block = Block::default()
        .title(" MM QUOTE STATE TAPE ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(line).block(block), area);
}

fn strategy_levels(app: &App) -> Vec<StrategyLevel> {
    if app.backend.is_apex_mm() {
        return mm_strategy_levels(app);
    }
    if app.backend.is_pine_stack() {
        return pine_strategy_levels(app);
    }
    let mut levels = Vec::new();
    if let Some(price) = app.backend.pending_maker_limit_price {
        levels.push(level("MAKER", price, app.theme.coiling));
    }
    if let Some(price) = app.backend.prior_range_high {
        levels.push(level("R-HI", price, app.theme.bear));
    }
    if let Some(price) = app.backend.prior_range_low {
        levels.push(level("R-LO", price, app.theme.carry));
    }
    if !app.active_position.is_active() {
        return levels;
    }
    levels.push(level(
        "ENTRY",
        app.active_position.entry_price,
        app.theme.gold,
    ));
    for (index, price) in app.backend.active_target_prices.iter().enumerate() {
        let label = if index == 0 {
            "TP".into()
        } else {
            format!("TP{}", index + 1)
        };
        levels.push(level(&label, *price, app.theme.cyan));
    }
    if let Some(price) = app.backend.protective_stop_price {
        levels.push(level("STOP", price, app.theme.bear));
    }
    if let Some(price) = app.active_position.liquidation_price {
        levels.push(level("LIQ", price, app.theme.bear));
    }
    levels
}

fn mm_strategy_levels(app: &App) -> Vec<StrategyLevel> {
    let mut levels = Vec::new();
    if let Some(price) = app.backend.apex_mm.bid_price {
        levels.push(level("MM-BID", price, app.theme.bull));
    }
    if let Some(price) = app.backend.apex_mm.ask_price {
        levels.push(level("MM-ASK", price, app.theme.bear));
    }
    if app.active_position.is_active() {
        levels.push(level(
            "ENTRY",
            app.active_position.entry_price,
            app.theme.gold,
        ));
        if let Some(price) = app.active_position.liquidation_price {
            levels.push(level("LIQ", price, app.theme.bear));
        }
    }
    levels
}

fn render_strategy_panel(f: &mut Frame, app: &App, candles: &[RegimeSnapshot], area: Rect) {
    if app.backend.is_apex_mm() {
        render_mm_strategy_panel(f, app, candles, area);
        return;
    }
    if app.backend.is_source_follow() {
        render_source_follow_strategy_panel(f, app, candles, area);
        return;
    }
    if app.backend.is_pine_stack() {
        render_pine_strategy_panel(f, app, candles, area);
        return;
    }
    if app.backend.is_hulk_smash() {
        render_hulk_smash_strategy_panel(f, app, candles, area);
        return;
    }
    if app
        .backend
        .strategy_name
        .as_deref()
        .is_some_and(|name| name.starts_with("sol_1h_sma10x30"))
    {
        render_sol_strategy_panel(f, app, candles, area);
        return;
    }
    render_default_strategy_panel(f, app, candles, area);
}

fn render_pine_strategy_panel(f: &mut Frame, app: &App, candles: &[RegimeSnapshot], area: Rect) {
    let pine = &app.backend.pine_stack;
    let action = app
        .backend
        .latest_decision_action
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let lines = vec![
        Line::from(format!(
            "CS {} │ TREND {} │ SENTIMENT {} / 100 │ SUPPORT {}/11",
            pine_state(pine.cs_state),
            pine_state(pine.trend_state),
            optional_number(pine.sentiment_score),
            pine.sentiment_support
                .map_or_else(|| "N/A".into(), |value| value.to_string())
        )),
        Line::from(level_line(&strategy_levels(app), price_bounds(candles))),
        Line::from(format!(
            "TP DENSITY {} │ POOL {} │ DENSITY MATCH, NOT PROBABILITY",
            optional_number(pine.tp_density_score),
            pine.tp_directional_pool
                .map_or_else(|| "N/A".into(), |value| value.to_string())
        )),
        Line::from(format!("ACTION {action} │ REGIME NOT CLASSIFIED")),
        Line::from("ZERO CAPITAL │ NO ORDERS │ PSEUDO-HOLDOUT FAILED │ BACKEND OBSERVATION ONLY"),
    ];
    let block = Block::default()
        .title(" PINE STACK · BACKEND OBSERVER ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn render_mm_strategy_panel(f: &mut Frame, app: &App, candles: &[RegimeSnapshot], area: Rect) {
    let mm = &app.backend.apex_mm;
    let lines = vec![
        Line::from(format!(
            "BID #{} {} x {}  |  ASK #{} {} x {}",
            optional_oid(mm.bid_oid),
            optional_money(mm.bid_price),
            optional_quantity(mm.bid_size),
            optional_oid(mm.ask_oid),
            optional_money(mm.ask_price),
            optional_quantity(mm.ask_size)
        )),
        Line::from(format!(
            "FAIR {}  |  FULL SPREAD {}  |  QUOTES {}",
            optional_money(mm.fair_value),
            optional_bps(mm.full_spread_bps),
            if mm.quote_active == Some(true) {
                "ACTIVE"
            } else {
                "WITHHELD"
            }
        )),
        Line::from(level_line(&strategy_levels(app), price_bounds(candles))),
        Line::from(format!(
            "INVENTORY {}  |  MARKOUT {}  |  SLIPPAGE {}  |  ACK {}",
            app.active_position.direction,
            optional_bps(mm.latest_markout_bps),
            optional_bps(mm.latest_slippage_bps),
            mm.latest_ack_latency_ms
                .map_or_else(|| "N/A".into(), |value| format!("{value}ms"))
        )),
        Line::from("REGIME NOT USED  |  SOURCE AUTHORITATIVE BACKEND ONLY"),
    ];
    let block = Block::default()
        .title(" APEX MM QUOTE LEVELS ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn render_sol_strategy_panel(f: &mut Frame, app: &App, candles: &[RegimeSnapshot], area: Rect) {
    let snap = app.current_snapshot();
    let direction = direction_label(app.backend.structural_direction.as_deref(), "NEUTRAL");
    let admission = if app.backend.regime_admitted == Some(true) {
        "ALLOWED"
    } else {
        "BLOCKED"
    };
    let action = app
        .backend
        .latest_decision_action
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let lines = vec![
        Line::from(format!(
            "1h SMA10/30  {direction}  │  5m REGIME {}  {admission}  │  SIGNAL {action}",
            snap.trend_5m
        )),
        Line::from(format!(
            "POSITION {}  │  U/PNL {:+.2}  │  ENTRY FEE ${:.2}  │  FUNDING ${:.2}",
            app.active_position.direction,
            app.paper_stats.unrealized_pnl,
            app.active_position.entry_fee_usd,
            app.active_position.funding_payment_usd
        )),
        Line::from(level_line(&strategy_levels(app), price_bounds(candles))),
        Line::from(format!(
            "DECISION {}  │  REASON {}",
            app.backend
                .latest_regime_feed_ts
                .as_deref()
                .unwrap_or("N/A"),
            app.backend
                .latest_regime_reason
                .as_deref()
                .unwrap_or("not reported")
        )),
        Line::from("SOURCE BACKEND ONLY · TUI READ ONLY"),
    ];
    let block = Block::default()
        .title(" SOL RANGE-ONSET · BACKEND ONLY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}
