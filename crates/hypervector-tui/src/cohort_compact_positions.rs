//! Small-terminal portfolio table with complete native stop identities.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    text::Line,
    widgets::{Cell, Paragraph, Row, Table},
};

use crate::{
    App,
    backend_cohort::CohortAssetSnapshot,
    cohort_format::{
        compact_number, money, number, optional_money, optional_signed_money, percent, signed_money,
    },
    cohort_widgets::{
        execution_plan_label, page_label, panel, position_style, protection_style, render_empty,
        selected_page,
    },
};

const SUMMARY_HEIGHT: u16 = 4;
const DETAIL_HEIGHT: u16 = 5;
const TABLE_CHROME: u16 = 3;

/// Keep every fitting asset and selected exact details available at the hard floor.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::vertical([
        Constraint::Length(SUMMARY_HEIGHT),
        Constraint::Min(TABLE_CHROME),
        Constraint::Length(DETAIL_HEIGHT),
    ])
    .split(area);
    render_summary(frame, app, sections[0]);
    let assets: Vec<_> = app.backend.cohort.assets.iter().collect();
    let selected = assets
        .iter()
        .position(|asset| Some(asset.symbol.as_str()) == app.selected_cohort_symbol())
        .unwrap_or(0);
    let capacity = usize::from(sections[1].height.saturating_sub(TABLE_CHROME));
    let (visible, _) = selected_page(assets.len(), selected, capacity);
    let label = page_label(&visible, assets.len());
    render_table(
        frame,
        app,
        sections[1],
        &assets[visible],
        &format!(" LIVE POSITIONS // ASSETS {label} // [←/→] SELECT "),
    );
    render_detail(frame, app, sections[2], assets.get(selected).copied());
}

/// Prefer open exposure when the trading workspace has fewer rows than assets.
pub(crate) fn render_tracker(frame: &mut Frame, app: &App, area: Rect) {
    let mut assets: Vec<_> = app.backend.cohort.assets.iter().collect();
    assets.sort_by_key(|asset| asset.position_side.is_none());
    let count = assets
        .len()
        .min(usize::from(area.height.saturating_sub(TABLE_CHROME)));
    let label = format!(
        " OPEN RISK // {count}/{} ASSETS // OPEN FIRST // [1] ALL + DETAILS ",
        assets.len()
    );
    render_table(frame, app, area, &assets[..count], &label);
}

fn render_summary(frame: &mut Frame, app: &App, area: Rect) {
    let Some(account) = app.backend.cohort.account.as_ref() else {
        render_empty(
            frame,
            app,
            area,
            " CAPITAL / RISK ",
            "Account reconciliation unavailable",
        );
        return;
    };
    let lines = vec![
        Line::from(format!(
            "USDC {}  FREE {}  OPEN {}/{}",
            money(account.account_value_usd),
            money(account.withdrawable_usd),
            account.open_position_count,
            app.backend.cohort.maximum_concurrent_positions
        )),
        Line::from(format!(
            "NOTIONAL {}  MARGIN {}  // [5] TRADES  [6] RESEARCH",
            money(account.total_notional_position_usd),
            money(account.total_margin_used_usd)
        )),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" CAPITAL / RISK // BACKEND ACCOUNT ", app)),
        area,
    );
}

fn render_table(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    assets: &[&CohortAssetSnapshot],
    title: &str,
) {
    let widths = [12, 5, 9, 9, 7, 16, 11, 18].map(Constraint::Length);
    let rows = assets.iter().map(|asset| asset_row(asset, app));
    let table = Table::new(rows, widths)
        .column_spacing(1)
        .header(
            Row::new([
                "COIN",
                "POS",
                "ENTRY~",
                "MARK~",
                "U/PNL",
                "MARGIN/NOTIONAL",
                "FEES/FUND",
                "VENUE STOP",
            ])
            .style(app.theme.header),
        )
        .block(panel(title.to_string(), app));
    frame.render_widget(table, area);
}

fn asset_row<'a>(asset: &'a CohortAssetSnapshot, app: &App) -> Row<'a> {
    Row::new(vec![
        Cell::from(asset.symbol.as_str()).style(app.theme.title),
        Cell::from(
            asset
                .position_side
                .as_deref()
                .unwrap_or("flat")
                .to_uppercase(),
        )
        .style(position_style(asset, app)),
        Cell::from(compact_number(asset.entry_price)),
        Cell::from(compact_number(asset.mark_price)),
        Cell::from(signed_money(asset.unrealized_pnl_usd)).style(position_style(asset, app)),
        Cell::from(format!(
            "{}/{}",
            money(asset.margin_used_usd),
            money(asset.position_value_usd)
        )),
        Cell::from(format!(
            "{}/{}",
            optional_money(asset.fees_net_usd),
            optional_signed_money(asset.funding_net_usd)
        )),
        Cell::from(stop_label(asset)).style(protection_style(asset, app)),
    ])
}

fn stop_label(asset: &CohortAssetSnapshot) -> String {
    if let Some(label) = crate::cohort_protective_progress::protection_override(asset) {
        return label.into();
    }
    match (asset.position_side.as_deref(), asset.stop_oid) {
        (None, _) => "FLAT".into(),
        (Some(_), Some(oid)) => format!("STOP #{oid}"),
        (Some(_), None) => "STOP MISSING".into(),
    }
}

fn render_detail(frame: &mut Frame, app: &App, area: Rect, asset: Option<&CohortAssetSnapshot>) {
    let Some(asset) = asset else {
        render_empty(
            frame,
            app,
            area,
            " SELECTED ASSET ",
            "No backend asset is available",
        );
        return;
    };
    let leverage = asset
        .leverage
        .map_or_else(|| "N/A".into(), |value| format!("{value}x"));
    let target = asset
        .target_oid
        .map_or_else(|| "NONE".into(), |oid| format!("#{oid}"));
    let lines = vec![
        Line::from(format!(
            "STATE {}  SIZE {:.8}  LEV {leverage}  TARGET {target}",
            asset.state, asset.position_size_signed
        )),
        Line::from(format!(
            "ENTRY {}  MARK {}  LIQ {} / {}",
            number(asset.entry_price),
            number(asset.mark_price),
            number(asset.liquidation_price),
            percent(asset.liquidation_distance_pct)
        )),
        Line::from(format!(
            "PLAN {}  FAULT {}",
            execution_plan_label(asset),
            asset.last_fault.as_deref().unwrap_or("NONE")
        )),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(
            crate::cohort_protective_progress::detail_title(asset),
            app,
        )),
        area,
    );
}
