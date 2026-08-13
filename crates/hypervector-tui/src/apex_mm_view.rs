//! Apex market-maker views backed exclusively by authoritative ledger events.

use crate::{
    apex_mm_format::{
        bps, compact_bps, connection_label, horizon_label, json_number, money, owned_quote,
        percent_fraction, quote_status,
    },
    apex_mm_panels,
    app::App,
    backend_apex_mm::BackendApexMMEvent,
    backend_telemetry::BackendConnectionState,
    hypervelocity,
};
use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Clear, Paragraph, Row, Table},
};

/// Render the execution-measurement dashboard without directional trade semantics.
pub(crate) fn render_dashboard(f: &mut Frame, app: &App, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(12),
            Constraint::Length(4),
            Constraint::Length(12),
            Constraint::Length(7),
            Constraint::Min(8),
        ])
        .split(area);
    render_policy(f, app, rows[0]);
    render_identity(f, app, rows[1]);
    let middle = horizontal(rows[2], 51, 49);
    apex_mm_panels::render_inventory(f, app, middle[0]);
    hypervelocity::render_book_ladder(f, app, middle[1]);
    apex_mm_panels::render_measurements(f, app, rows[3]);
    render_events(f, app, rows[4]);
}

/// Render market-maker microstructure in place of an unused regime detector.
pub(crate) fn render_microstructure(f: &mut Frame, app: &App, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4),
            Constraint::Length(11),
            Constraint::Length(7),
            Constraint::Min(8),
        ])
        .split(area);
    render_microstructure_banner(f, app, rows[0]);
    let middle = horizontal(rows[1], 50, 50);
    render_book_metrics(f, app, middle[0]);
    render_quote_metrics(f, app, middle[1]);
    apex_mm_panels::render_measurements(f, app, rows[2]);
    render_events(f, app, rows[3]);
}

/// Render help for the active market-maker measurement strategy.
pub(crate) fn render_help(f: &mut Frame, app: &App, area: Rect) {
    let modal = centered_rect(68, 65, area);
    f.render_widget(Clear, modal);
    let lines = vec![
        Line::from(vec![Span::styled(
            "APEX MM EXECUTION MEASUREMENT HELP",
            app.theme.title,
        )]),
        Line::from(""),
        Line::from(
            "PURPOSE: measure mainnet quote, fill, fee, funding, latency, and markout friction",
        ),
        Line::from("STRATEGY TYPE: two-sided BTC market maker; not Hypervelocity"),
        Line::from("DIRECTION: no long/short forecast; first fill creates temporary inventory"),
        Line::from("REGIME: not used for quote decisions; book midpoint history is display only"),
        Line::from("POSITION: isolated one-way net inventory; at most one position per symbol"),
        Line::from(format!(
            "ORDERS: {}; backend owns placement and cancellation",
            quote_transport_description(app)
        )),
        Line::from("TUI AUTHORITY: read only; it never constructs an execution client"),
        Line::from(
            "EDGE STATUS: not demonstrated; this canary measures execution, not profitability",
        ),
        Line::from(""),
        Line::from("[1] Dashboard: inventory, lifecycle, fills, costs, quality, recent events"),
        Line::from("[2] Microstructure: L2 pressure, paired quotes, execution measurements"),
        Line::from("[3] Chart: backend midpoint tape with owned quote levels"),
        Line::from("[4] Config: effective backend contract and masked credential presence"),
        Line::from(""),
        Line::from("[Space] Play/pause  [Left/Right] Scrub  [?] Help  [q/Esc] Close/quit"),
    ];
    let block = Block::default()
        .title(" APEX MM HELP · BACKEND AUTHORITY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Double)
        .border_style(app.theme.border_active);
    f.render_widget(
        Paragraph::new(lines)
            .block(block)
            .alignment(Alignment::Left),
        modal,
    );
}

fn horizontal(area: Rect, left: u16, right: u16) -> std::rc::Rc<[Rect]> {
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(left), Constraint::Percentage(right)])
        .split(area)
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);
    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(vertical[1])[1]
}

fn render_policy(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let max_inventory = json_number(&app.backend.risk, "max_inventory_notional_usd");
    let lines = vec![
        Line::from(format!("NOW: {}", strategy_now(app))),
        Line::from(format!(
            "PURPOSE: BTC MARKET MAKER {:.0}x EXECUTION FRICTION TEST; PROFIT EDGE UNPROVEN",
            app.active_position.leverage
        )),
        Line::from(
            "INPUT: LIVE BTC L2 BOOK + RECENT MIDPOINT VOLATILITY | REGIME NOT USED | ML NOT USED",
        ),
        Line::from("DECISION: NO DIRECTION CALL / NO LONG/SHORT FORECAST; QUOTE BOTH SIDES"),
        Line::from(format!(
            "ORDERS: {}; RESTING QUOTES ARE NOT FILLED TRADES",
            quote_transport_description(app).to_ascii_uppercase()
        )),
        Line::from(format!(
            "PRICES: fair value {}  |  BUY {}  |  SELL {}  |  SPREAD {}",
            money(mm.fair_value),
            owned_quote(mm.bid_oid, mm.bid_price, None),
            owned_quote(mm.ask_oid, mm.ask_price, None),
            bps(mm.full_spread_bps)
        )),
        Line::from("FIRST FILL: BUY -> TEMP LONG | SELL -> TEMP SHORT"),
        Line::from(format!(
            "EXIT/RISK: SKEW QUOTES TOWARD FLAT | NO TP/SL | {} INVENTORY CAP",
            money(max_inventory)
        )),
        Line::from(strategy_next(app)),
        Line::from(format!(
            "BACKEND {}  |  ENGINE {}  |  INV {}  |  {} {}",
            connection_label(app.backend.connection),
            app.backend.live_state.as_deref().unwrap_or("UNKNOWN"),
            money(mm.inventory_notional_usd),
            horizon_label(mm.markout_horizon_ms),
            compact_bps(mm.latest_markout_bps)
        )),
    ];
    render_paragraph(
        f,
        app,
        area,
        " LIVE BTC MARKET-MAKING CANARY · NOT HYPERVELOCITY ",
        lines,
    );
}

fn strategy_now(app: &App) -> String {
    if app.backend.connection != BackendConnectionState::Connected {
        return "TUI CANNOT CONFIRM LIVE STATE — backend telemetry is not current".into();
    }
    let mm = &app.backend.apex_mm;
    let state = app.backend.live_state.as_deref().unwrap_or("UNKNOWN");
    let position = mm.position_size_signed.unwrap_or(0.0);
    match state {
        "STOPPED" => "STOPPED — no live orders are managed by this run".into(),
        "FAULT" => "FAULTED — new quotes stopped; cleanup must verify flat".into(),
        "STARTING" => "STARTING — validating venue state before quoting".into(),
        _ if position > 0.0 => {
            "LONG INVENTORY — the bid filled first; favoring a sell-side exit".into()
        }
        _ if position < 0.0 => {
            "SHORT INVENTORY — the ask filled first; favoring a buy-side exit".into()
        }
        _ if mm.quote_active == Some(false) => format!(
            "WITHHOLDING QUOTES — {}",
            mm.quote_reason
                .as_deref()
                .unwrap_or("backend reason unreported")
        ),
        _ if mm.bid_oid.is_some() || mm.ask_oid.is_some() => {
            "QUOTING BOTH SIDES — flat now; waiting for one maker order to fill".into()
        }
        _ => "CALCULATING QUOTES — flat, with no confirmed resting order yet".into(),
    }
}

fn quote_transport_description(app: &App) -> &str {
    match app
        .backend
        .execution_policy
        .get("submission_transport")
        .and_then(serde_json::Value::as_str)
    {
        Some("single_bulk_orders_action") => "one batched post-only buy + sell action",
        Some(value) => value,
        None => "submission transport not reported",
    }
}

fn strategy_next(app: &App) -> String {
    let mm = &app.backend.apex_mm;
    let state = app.backend.live_state.as_deref().unwrap_or("UNKNOWN");
    let position = mm.position_size_signed.unwrap_or(0.0);
    match state {
        "STOPPED" => "NEXT: remain flat until the backend is explicitly armed again".into(),
        "FAULT" => "NEXT: cancel quotes, flatten inventory, and prove the venue is flat".into(),
        _ if app.backend.connection != BackendConnectionState::Connected => {
            "NEXT: rely on backend fail-closed cleanup; this TUI remains read only".into()
        }
        _ if position > 0.0 => {
            "NEXT: reduce new buys and strengthen the sell quote until inventory is flat".into()
        }
        _ if position < 0.0 => {
            "NEXT: reduce new sells and strengthen the buy quote until inventory is flat".into()
        }
        _ => "NEXT: keep current order IDs until calculated quote prices materially change".into(),
    }
}

fn render_identity(f: &mut Frame, app: &App, area: Rect) {
    let identity = Line::from(format!(
        "STRATEGY {}  |  PROFILE {}  |  RUN {}  |  MODE {}  |  AUTHORITY {}  |  TUI READ ONLY",
        app.backend.strategy_name.as_deref().unwrap_or("unreported"),
        app.backend.profile_id.as_deref().unwrap_or("unreported"),
        app.backend.run_id.as_deref().unwrap_or("unreported"),
        app.backend
            .execution_mode
            .as_deref()
            .unwrap_or("unreported"),
        app.backend
            .execution_authority
            .as_deref()
            .unwrap_or("unreported")
    ));
    let account = Line::from(format!(
        "ACCOUNT EQUITY ${:.2}  |  REALIZED {:+.4} USD  |  UNREALIZED {:+.4} USD  |  BACKEND {}",
        app.paper_stats.current_equity,
        app.paper_stats.realized_pnl,
        app.paper_stats.unrealized_pnl,
        connection_label(app.backend.connection)
    ));
    render_paragraph(
        f,
        app,
        area,
        " AUTHORITATIVE BACKEND RUN & ACCOUNT ",
        vec![identity, account],
    );
}

fn render_microstructure_banner(f: &mut Frame, app: &App, area: Rect) {
    let lines = vec![
        Line::from(vec![
            Span::styled("APEX MM MICROSTRUCTURE TELEMETRY", app.theme.title),
            Span::raw("  |  "),
            Span::styled("NO DIRECTIONAL REGIME AUTHORITY", app.theme.gold),
        ]),
        Line::from("Backend L2, paired orders, fills, fees, funding, latency, and markouts only."),
    ];
    render_paragraph(f, app, area, " MM BACKEND VIEW ", lines);
}

fn render_book_metrics(f: &mut Frame, app: &App, area: Rect) {
    let lines = if let Some(book) = app.backend.book.as_ref() {
        vec![
            Line::from(format!(
                "MID ${:.2}  |  SPREAD {:.2} bps  |  ORDER PRESSURE {:+.2}",
                book.mid_price, book.spread_bps, book.opi
            )),
            Line::from(format!(
                "BID DEPTH RATIO {:.2}  |  BIDS {}  |  ASKS {}",
                book.bid_depth_ratio,
                book.bid_levels.len(),
                book.ask_levels.len()
            )),
            Line::from(format!(
                "SOURCE {}  |  EXCHANGE TS {}",
                book.source,
                book.exchange_ts_ms
                    .map_or_else(|| "N/A".into(), |value| format!("{value:.0}"))
            )),
            Line::from(format!(
                "RECEIVE TS {:.0}  |  TUI TRANSFORMS: NONE",
                book.recv_ts_ms
            )),
        ]
    } else {
        vec![Line::from("Backend book observation not reported")]
    };
    render_paragraph(f, app, area, " LIVE L2 MICROSTRUCTURE ", lines);
}

fn render_quote_metrics(f: &mut Frame, app: &App, area: Rect) {
    let mm = &app.backend.apex_mm;
    let lines = vec![
        Line::from(format!(
            "STATUS {}  |  REASON {}",
            quote_status(mm.quote_active),
            mm.quote_reason.as_deref().unwrap_or("not reported")
        )),
        Line::from(format!(
            "BID {}",
            owned_quote(mm.bid_oid, mm.bid_price, mm.bid_size)
        )),
        Line::from(format!(
            "ASK {}",
            owned_quote(mm.ask_oid, mm.ask_price, mm.ask_size)
        )),
        Line::from(format!(
            "FAIR {}  |  FULL SPREAD {}  |  UTIL {}",
            money(mm.fair_value),
            bps(mm.full_spread_bps),
            percent_fraction(mm.inventory_utilization)
        )),
    ];
    render_paragraph(f, app, area, " PAIRED QUOTES ", lines);
}

fn render_events(f: &mut Frame, app: &App, area: Rect) {
    let events = app.backend.apex_mm.recent_events.iter().rev();
    let rows = events.map(event_row);
    let table = Table::new(
        rows,
        [
            Constraint::Length(14),
            Constraint::Length(24),
            Constraint::Min(40),
        ],
    )
    .header(
        Row::new(["Time (ET)", "Backend event", "Strategy-attributed detail"])
            .style(app.theme.header),
    )
    .block(
        Block::default()
            .title(" RECENT MM EXECUTION EVENTS ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border_active),
    );
    f.render_widget(table, area);
}

fn event_row(event: &BackendApexMMEvent) -> Row<'static> {
    Row::new([
        crate::ui::format_time_display(&event.timestamp),
        event.kind.clone(),
        event.detail.clone(),
    ])
}

pub(crate) fn render_paragraph(
    f: &mut Frame,
    app: &App,
    area: Rect,
    title: &str,
    lines: Vec<Line<'static>>,
) {
    let block = Block::default()
        .title(title.to_string())
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(app.theme.border_active);
    f.render_widget(Paragraph::new(lines).block(block), area);
}
