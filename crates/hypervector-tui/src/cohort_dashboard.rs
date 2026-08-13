//! Responsive operational dashboard for the shared bidirectional cohort.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Paragraph, Row, Table},
};

use crate::app::App;
use crate::backend_cohort::CohortAssetSnapshot;
use crate::backend_telemetry::BackendConnectionState;
use crate::cohort_format::{
    money, number, optional_money, optional_signed_money, percent, signed_money,
};
use crate::cohort_widgets::{
    WIDE_WIDTH, execution_plan_label, page_label, panel, position_style, protection_label,
    protection_style, render_empty,
};

const PRIMARY_ASSET_COUNT: usize = 4;
const COMPACT_FULL_POSITION_HEIGHT: u16 = 15;
const TALL_FULL_POSITION_HEIGHT: u16 = 19;
const TALL_DASHBOARD_HEIGHT: u16 = 40;

/// Render capital, positions, and exact current-run fill evidence.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort_checkpoint.analysis_mode.as_deref() == Some("forward_observer") {
        crate::cohort_observer_dashboard::render(frame, app, area);
        return;
    }
    let complete_portfolio = app.backend.cohort.assets.len() > PRIMARY_ASSET_COUNT;
    let position_height = position_height(area.height, complete_portfolio);
    let checkpoint_height = if complete_portfolio { 3 } else { 5 };
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),
            Constraint::Length(checkpoint_height),
            Constraint::Length(position_height),
            Constraint::Min(0),
        ])
        .split(area);
    render_kpis(frame, app, sections[0]);
    crate::cohort_checkpoint_widget::render(frame, app, sections[1]);
    render_positions(frame, app, sections[2]);
    render_lower_dashboard(frame, app, sections[3]);
}

fn render_kpis(frame: &mut Frame, app: &App, area: Rect) {
    let Some(account) = app.backend.cohort.account.as_ref() else {
        render_empty(
            frame,
            app,
            area,
            " ACCOUNT RECONCILIATION ",
            "Awaiting the first backend-authored venue snapshot",
        );
        return;
    };
    crate::cohort_portfolio_scoreboard::render(frame, app, area, account);
}

fn render_lower_dashboard(frame: &mut Frame, app: &App, area: Rect) {
    if area.height < 6 {
        render_dashboard_strip(frame, app, area);
        return;
    }
    if area.width < 112 {
        crate::cohort_market_pulse::render(frame, app, area);
        return;
    }
    render_market_and_strategy(frame, app, area);
}

fn render_dashboard_strip(frame: &mut Frame, app: &App, area: Rect) {
    let eligible = app
        .backend
        .cohort
        .evaluations
        .iter()
        .filter(|evaluation| evaluation.eligible)
        .count();
    let faults = app
        .backend
        .cohort
        .assets
        .iter()
        .filter(|asset| asset.last_fault.is_some())
        .count();
    let line = Line::from(vec![
        Span::raw(format!(
            "SETUPS {}  ELIGIBLE {eligible}  OPEN {} / {}  FAULTS {faults}  //  ",
            app.backend.cohort.evaluations.len(),
            app.backend
                .cohort
                .account
                .as_ref()
                .map_or(0, |value| value.open_position_count),
            app.backend.cohort.maximum_concurrent_positions,
        )),
        Span::styled("[2] SETUPS  [5] TRADES  [6] JOURNAL", app.theme.cyan),
    ]);
    frame.render_widget(
        Paragraph::new(line).block(panel(" PORTFOLIO ROUTE PULSE ", app)),
        area,
    );
}

fn render_market_and_strategy(frame: &mut Frame, app: &App, area: Rect) {
    let columns =
        Layout::horizontal([Constraint::Percentage(54), Constraint::Percentage(46)]).split(area);
    crate::cohort_market_pulse::render(frame, app, columns[0]);
    crate::cohort_strategy_scoreboard::render(frame, app, columns[1]);
}

fn render_positions(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.assets.is_empty() {
        render_empty(
            frame,
            app,
            area,
            " LIVE POSITIONS ",
            "No asset snapshot reported",
        );
        return;
    }
    let total = app.backend.cohort.assets.len();
    let split = total.min(PRIMARY_ASSET_COUNT);
    if total <= PRIMARY_ASSET_COUNT {
        render_position_group(frame, app, area, 0, split);
        return;
    }
    let minimum_first_height = u16::try_from(split + 3).unwrap_or(area.height / 2);
    let first_height = if area.height > COMPACT_FULL_POSITION_HEIGHT {
        area.height / 2
    } else {
        minimum_first_height
    };
    let rows = Layout::vertical([Constraint::Length(first_height), Constraint::Min(1)]).split(area);
    render_position_group(frame, app, rows[0], 0, split);
    render_position_group(frame, app, rows[1], split, total);
}

fn render_position_group(frame: &mut Frame, app: &App, area: Rect, start: usize, end: usize) {
    let visible = start..end;
    let assets = app
        .backend
        .cohort
        .assets
        .get(visible.clone())
        .unwrap_or(&[]);
    let label = page_label(&visible, app.backend.cohort.assets.len());
    if area.width >= WIDE_WIDTH {
        render_wide_positions(frame, app, area, assets, &label);
    } else {
        render_compact_positions(frame, app, area, assets, &label);
    }
}

fn position_height(area_height: u16, complete_portfolio: bool) -> u16 {
    if !complete_portfolio {
        return 7;
    }
    if area_height >= TALL_DASHBOARD_HEIGHT {
        TALL_FULL_POSITION_HEIGHT
    } else {
        COMPACT_FULL_POSITION_HEIGHT
    }
}

fn render_compact_positions(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    assets: &[CohortAssetSnapshot],
    label: &str,
) {
    let rows = assets.iter().map(|asset| compact_asset_row(asset, app));
    let widths = [13, 6, 7, 11, 11, 9, 8, 11, 16, 15].map(Constraint::Length);
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(
            Row::new([
                "COIN",
                "POS",
                "STATE",
                "MARK",
                "ENTRY",
                "U/PNL",
                "LIQ DIST",
                "COSTS",
                "VENUE BRACKET",
                "PLAN/FAULT",
            ])
            .style(app.theme.header),
        )
        .block(panel(
            format!(" LIVE POSITIONS // ASSETS {label} // ONE PER ASSET "),
            app,
        ));
    frame.render_widget(table, area);
}

fn compact_asset_row<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Row<'a> {
    let position = asset
        .position_side
        .as_deref()
        .unwrap_or("flat")
        .to_uppercase();
    Row::new(vec![
        Cell::from(asset.symbol.as_str()).style(app.theme.title),
        Cell::from(position).style(position_style(asset, app)),
        Cell::from(asset.state.as_str()).style(position_style(asset, app)),
        Cell::from(number(asset.mark_price)),
        Cell::from(number(asset.entry_price)),
        Cell::from(signed_money(asset.unrealized_pnl_usd)).style(position_style(asset, app)),
        Cell::from(percent(asset.liquidation_distance_pct)),
        Cell::from(cost_label(asset)),
        Cell::from(protection_label(asset)).style(protection_style(asset, app)),
        fault_cell(asset, app),
    ])
}

fn render_wide_positions(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    assets: &[CohortAssetSnapshot],
    label: &str,
) {
    let rows = assets.iter().map(|asset| wide_asset_row(asset, app));
    let widths = [13, 6, 8, 10, 11, 11, 11, 9, 9, 10, 9, 12, 4, 20, 12].map(Constraint::Length);
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(
            Row::new([
                "COIN",
                "POS",
                "STATE",
                "SIZE",
                "MARK",
                "ENTRY",
                "LIQ",
                "LIQ DIST",
                "MARGIN",
                "NOTIONAL",
                "U/PNL",
                "FEES/FUND",
                "LEV",
                "VENUE BRACKET",
                "PLAN/FAULT",
            ])
            .style(app.theme.header),
        )
        .block(panel(
            format!(
                " LIVE POSITIONS // ASSETS {label} // {} ",
                position_source_label(app)
            ),
            app,
        ));
    frame.render_widget(table, area);
}

fn position_source_label(app: &App) -> &'static str {
    match app.backend.connection {
        BackendConnectionState::Connected => "BACKEND LIVE TELEMETRY",
        BackendConnectionState::Stale => "STALE BACKEND TELEMETRY",
        BackendConnectionState::Disconnected | BackendConnectionState::Error => {
            "BACKEND TELEMETRY UNAVAILABLE"
        }
    }
}

fn wide_asset_row<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Row<'a> {
    let position = asset
        .position_side
        .as_deref()
        .unwrap_or("flat")
        .to_uppercase();
    Row::new(vec![
        Cell::from(asset.symbol.as_str()).style(app.theme.title),
        Cell::from(position).style(position_style(asset, app)),
        Cell::from(asset.state.as_str()).style(position_style(asset, app)),
        Cell::from(format!("{:+.5}", asset.position_size_signed)),
        Cell::from(number(asset.mark_price)),
        Cell::from(number(asset.entry_price)),
        Cell::from(number(asset.liquidation_price)),
        Cell::from(percent(asset.liquidation_distance_pct)),
        Cell::from(money(asset.margin_used_usd)),
        Cell::from(money(asset.position_value_usd)),
        Cell::from(signed_money(asset.unrealized_pnl_usd)).style(position_style(asset, app)),
        Cell::from(cost_label(asset)),
        Cell::from(
            asset
                .leverage
                .map_or_else(|| "-".into(), |value| format!("{value}x")),
        ),
        Cell::from(protection_label(asset)).style(protection_style(asset, app)),
        fault_cell(asset, app),
    ])
}

fn cost_label(asset: &CohortAssetSnapshot) -> String {
    format!(
        "{} / {}",
        optional_money(asset.fees_net_usd),
        optional_signed_money(asset.funding_net_usd)
    )
}

fn fault_cell<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Cell<'a> {
    asset.last_fault.as_deref().map_or_else(
        || Cell::from(execution_plan_label(asset)).style(app.theme.cyan),
        |fault| Cell::from(fault).style(app.theme.gate_blocked),
    )
}
