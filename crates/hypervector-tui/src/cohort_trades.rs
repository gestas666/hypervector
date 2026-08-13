//! Exact fill, cost, latency, slippage, and markout workspace.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    widgets::{Cell, Row, Table, TableState},
};

use crate::app::App;
use crate::backend_cohort::{CohortAssetSnapshot, CohortFill};
use crate::cohort_format::{
    compact_number, fill_date_time, fill_time, markout, money, number, optional_bps,
    optional_money, optional_signed_money, percent, signed_money,
};
use crate::cohort_trade_selection::CohortTradeFocus;
use crate::cohort_widgets::{
    execution_plan_label, panel, position_style, protection_label, provider_alias, render_empty,
};

const HIP3_SYMBOL_COLUMN_WIDTH: u16 = 12;

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    crate::cohort_trade_screen::render(frame, app, area);
}

pub(crate) fn render_position_tracker(frame: &mut Frame, app: &App, area: Rect) {
    if area.width >= 160 {
        render_wide_position_tracker(frame, app, area);
    } else {
        render_compact_position_tracker(frame, app, area);
    }
}

fn render_compact_position_tracker(frame: &mut Frame, app: &App, area: Rect) {
    let rows = app
        .backend
        .cohort
        .assets
        .iter()
        .map(|asset| compact_position_row(asset, app));
    let table = Table::new(
        rows,
        [
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(6),
            Constraint::Length(10),
            Constraint::Length(10),
            Constraint::Length(8),
            Constraint::Length(15),
            Constraint::Length(4),
            Constraint::Length(17),
            Constraint::Length(12),
            Constraint::Min(18),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new([
            "COIN",
            "POS",
            "ENTRY",
            "MARK",
            "U/PNL",
            "MARGIN/NOTIONAL",
            "LEV",
            "LIQ PX / DIST",
            "FEES / FUND",
            "VENUE BRACKET",
        ])
        .style(app.theme.header),
    )
    .block(panel(position_panel_title(app), app));
    frame.render_widget(table, area);
}

fn compact_position_row<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Row<'a> {
    let position = asset
        .position_side
        .as_deref()
        .unwrap_or("flat")
        .to_uppercase();
    Row::new(vec![
        Cell::from(asset.symbol.as_str()).style(app.theme.title),
        Cell::from(position).style(position_style(asset, app)),
        Cell::from(compact_number(asset.entry_price)),
        Cell::from(compact_number(asset.mark_price)),
        Cell::from(signed_money(asset.unrealized_pnl_usd)).style(position_style(asset, app)),
        Cell::from(format!(
            "{}/{}",
            money(asset.margin_used_usd),
            money(asset.position_value_usd),
        )),
        Cell::from(
            asset
                .leverage
                .map_or_else(|| "-".into(), |value| format!("{value}x")),
        ),
        Cell::from(format!(
            "{} / {}",
            compact_number(asset.liquidation_price),
            percent(asset.liquidation_distance_pct),
        )),
        Cell::from(format!(
            "{}/{}",
            optional_money(asset.fees_net_usd),
            optional_signed_money(asset.funding_net_usd),
        )),
        Cell::from(protection_label(asset)),
    ])
}

fn render_wide_position_tracker(frame: &mut Frame, app: &App, area: Rect) {
    let rows = app
        .backend
        .cohort
        .assets
        .iter()
        .map(|asset| position_row(asset, app));
    let table = Table::new(
        rows,
        [
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(7),
            Constraint::Length(11),
            Constraint::Length(11),
            Constraint::Length(10),
            Constraint::Length(9),
            Constraint::Length(11),
            Constraint::Length(5),
            Constraint::Length(11),
            Constraint::Length(9),
            Constraint::Length(11),
            Constraint::Length(11),
            Constraint::Length(12),
            Constraint::Min(16),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new([
            "COIN",
            "POS",
            "ENTRY",
            "MARK",
            "U/PNL",
            "MARGIN",
            "NOTIONAL",
            "LEV",
            "LIQ PX",
            "LIQ DIST",
            "FEES",
            "FUNDING",
            "PLAN",
            "VENUE BRACKET",
        ])
        .style(app.theme.header),
    )
    .block(panel(position_panel_title(app), app));
    frame.render_widget(table, area);
}

fn position_row<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Row<'a> {
    let position = asset
        .position_side
        .as_deref()
        .unwrap_or("flat")
        .to_uppercase();
    Row::new(vec![
        Cell::from(asset.symbol.as_str()).style(app.theme.title),
        Cell::from(position).style(position_style(asset, app)),
        Cell::from(number(asset.entry_price)),
        Cell::from(number(asset.mark_price)),
        Cell::from(signed_money(asset.unrealized_pnl_usd)).style(position_style(asset, app)),
        Cell::from(money(asset.margin_used_usd)),
        Cell::from(money(asset.position_value_usd)),
        Cell::from(
            asset
                .leverage
                .map_or_else(|| "-".into(), |value| format!("{value}x")),
        ),
        Cell::from(number(asset.liquidation_price)),
        Cell::from(percent(asset.liquidation_distance_pct)),
        Cell::from(optional_money(asset.fees_net_usd)),
        Cell::from(optional_signed_money(asset.funding_net_usd)),
        Cell::from(execution_plan_label(asset)),
        Cell::from(protection_label(asset)),
    ])
}

fn position_panel_title(app: &App) -> &'static str {
    let profile_history = !app.backend.cohort.assets.is_empty()
        && app
            .backend
            .cohort
            .assets
            .iter()
            .all(|asset| asset.cost_scope.as_deref() == Some("compatible_profile_history"));
    if profile_history {
        " OPEN RISK // PROFILE-HISTORY COSTS // MARGIN/NOTIONAL + LIQUIDATION "
    } else {
        " OPEN RISK TRACKER // VENUE POSITION + COST + LIQUIDATION "
    }
}

pub(crate) fn render_fill_journal(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.fills.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " VENUE FILL LEGS // NOT COMPLETED TRADES ",
            "No fills reported for this compatible execution profile",
        );
        return;
    }
    if area.width >= 160 {
        render_wide_fill_journal(frame, app, area);
    } else {
        render_compact_fill_journal(frame, app, area);
    }
}

fn render_compact_fill_journal(frame: &mut Frame, app: &App, area: Rect) {
    let title = fill_journal_title(app);
    let rows = app
        .backend
        .cohort
        .fills
        .iter()
        .rev()
        .map(|fill| compact_fill_row(fill, app));
    let table = Table::new(
        rows,
        [
            Constraint::Length(12),
            Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
            Constraint::Length(13),
            Constraint::Length(18),
            Constraint::Length(15),
            Constraint::Length(12),
            Constraint::Length(10),
            Constraint::Length(11),
            Constraint::Min(11),
        ],
    )
    .header(
        Row::new([
            "TIME ET",
            "COIN",
            "DIRECTION",
            "PROVIDER",
            "PRICE",
            "SIZE",
            "FEE",
            "SLIPPAGE",
            "MARKOUT",
        ])
        .style(app.theme.header),
    )
    .row_highlight_style(app.theme.highlight)
    .highlight_symbol("▸ ")
    .block(panel(title.as_str(), app));
    let selected = app
        .selected_cohort_fill_index
        .min(app.backend.cohort.fills.len().saturating_sub(1));
    let focused = app.effective_cohort_trade_focus() == CohortTradeFocus::Fills;
    let mut state = TableState::default().with_selected(focused.then_some(selected));
    frame.render_stateful_widget(table, area, &mut state);
}

fn compact_fill_row<'a>(fill: &'a CohortFill, app: &App) -> Row<'a> {
    Row::new(vec![
        Cell::from(fill_time(fill.venue_timestamp_ms)),
        Cell::from(fill.symbol.as_str()).style(app.theme.title),
        Cell::from(fill.direction.as_str()),
        Cell::from(provider_alias(&fill.strategy_id)),
        Cell::from(format!("{:.8}", fill.price)),
        Cell::from(format!("{:.6}", fill.size)),
        Cell::from(money(fill.fee_usd)),
        Cell::from(optional_bps(fill.slippage_bps)),
        Cell::from(optional_bps(fill.markout_bps)),
    ])
}

fn render_wide_fill_journal(frame: &mut Frame, app: &App, area: Rect) {
    let full_ids = area.width >= 180;
    let title = fill_journal_title(app);
    let rows = app
        .backend
        .cohort
        .fills
        .iter()
        .rev()
        .map(|fill| wide_fill_row(fill, app, full_ids));
    let table = Table::new(rows, wide_fill_widths(full_ids))
        .column_spacing(1)
        .header(wide_fill_header(app, full_ids))
        .row_highlight_style(app.theme.highlight)
        .highlight_symbol("▸ ")
        .block(panel(title.as_str(), app));
    let selected = app
        .selected_cohort_fill_index
        .min(app.backend.cohort.fills.len().saturating_sub(1));
    let focused = app.effective_cohort_trade_focus() == CohortTradeFocus::Fills;
    let mut state = TableState::default().with_selected(focused.then_some(selected));
    frame.render_stateful_widget(table, area, &mut state);
}

fn fill_journal_title(app: &App) -> String {
    let current = app.backend.run_id.as_deref().map_or(0, |run_id| {
        app.backend
            .cohort
            .fills
            .iter()
            .filter(|fill| fill.origin_run_id.as_deref() == Some(run_id))
            .count()
    });
    let focus = app.effective_cohort_trade_focus() == CohortTradeFocus::Fills;
    format!(
        " VENUE FILL LEGS // NOT COMPLETED TRADES // {} // CURRENT RUN {current} HISTORY {} // [←/→] FOCUS ",
        if focus { "ACTIVE" } else { "VIEW" },
        app.backend.cohort.fills.len().saturating_sub(current),
    )
}

fn wide_fill_widths(full_ids: bool) -> Vec<Constraint> {
    let mut widths = vec![
        Constraint::Length(if full_ids { 16 } else { 12 }),
        Constraint::Length(HIP3_SYMBOL_COLUMN_WIDTH),
        Constraint::Length(11),
        Constraint::Length(16),
    ];
    if full_ids {
        widths.push(Constraint::Length(17));
    }
    widths.extend([
        Constraint::Length(14),
        Constraint::Length(12),
        Constraint::Length(10),
        Constraint::Length(7),
        Constraint::Length(10),
        Constraint::Length(10),
        Constraint::Length(8),
        Constraint::Length(20),
        Constraint::Min(14),
    ]);
    widths
}

fn wide_fill_header(app: &App, full_ids: bool) -> Row<'static> {
    let timestamp = if full_ids { "DATE/TIME ET" } else { "TIME ET" };
    let mut labels = vec![timestamp, "COIN", "DIRECTION", "PROVIDER"];
    if full_ids {
        labels.push("TRADE ID");
    }
    labels.extend([
        "ORDER ID",
        "PRICE",
        "SIZE",
        "FEE",
        "FILL GROSS",
        "SLIPPAGE",
        "ACK",
        "MARKOUT",
        "EXIT",
    ]);
    Row::new(labels).style(app.theme.header)
}

fn wide_fill_row<'a>(fill: &'a CohortFill, app: &App, full_ids: bool) -> Row<'a> {
    let mut cells = vec![
        Cell::from(if full_ids {
            fill_date_time(fill.venue_timestamp_ms)
        } else {
            fill_time(fill.venue_timestamp_ms)
        }),
        Cell::from(fill.symbol.as_str()).style(app.theme.title),
        Cell::from(fill.direction.as_str()),
        Cell::from(provider_alias(&fill.strategy_id)),
    ];
    if full_ids {
        cells.push(Cell::from(fill.trade_id.to_string()));
    }
    cells.extend([
        Cell::from(fill.oid.to_string()),
        Cell::from(format!("{:.8}", fill.price)),
        Cell::from(format!("{:.6}", fill.size)),
        Cell::from(money(fill.fee_usd)),
        Cell::from(signed_money(fill.closed_pnl_usd)),
        Cell::from(optional_bps(fill.slippage_bps)),
        Cell::from(
            fill.acknowledgement_latency_ms
                .map_or_else(|| "N/A".into(), |value| format!("{value}ms")),
        ),
        Cell::from(markout(fill.markout_bps, fill.markout_horizon_ms)),
        Cell::from(fill.exit_reason.as_deref().unwrap_or("-")),
    ]);
    Row::new(cells)
}

pub(crate) fn render_detail(frame: &mut Frame, app: &App, area: Rect) {
    match app.effective_cohort_trade_focus() {
        CohortTradeFocus::Lifecycles => {
            crate::cohort_trade_history::render_detail(frame, app, area);
        }
        CohortTradeFocus::Fills => crate::cohort_fill_detail::render(frame, app, area),
    }
}
