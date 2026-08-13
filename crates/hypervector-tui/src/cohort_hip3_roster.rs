//! Compact display of backend-authored HIP-3 research telemetry.

use ratatui::{
    Frame,
    layout::{Constraint, Rect},
    widgets::{Cell, Row, Table},
};

use crate::app::App;
use crate::backend_hip3_roster::{Hip3MarketTelemetry, Hip3RosterTelemetry};
use crate::cohort_widgets::{panel, render_empty};

/// Format one exact market row without inventing unavailable values.
pub fn market_row_values(market: &Hip3MarketTelemetry) -> [String; 7] {
    [
        market.symbol.clone(),
        format!("{:.4}", market.book.mid_price),
        format!("{:.3}", market.book.spread_bps),
        format!(
            "{:+.0}/{:+.0}",
            market.book.depth_5_pressure * 100.0,
            market.book.depth_20_pressure * 100.0,
        ),
        market
            .venue
            .taker_fee_rate
            .map_or_else(|| "UNRES".into(), |rate| format!("{:.3}", rate * 10_000.0)),
        market
            .venue
            .funding_rate_hourly
            .map_or_else(|| "N/A".into(), |rate| format!("{:+.3}", rate * 10_000.0)),
        position_label(market),
    ]
}

/// Build a concise title that exposes safety and WTI identity state.
pub fn roster_title(status: &Hip3RosterTelemetry) -> String {
    let poll = status
        .polls
        .map_or_else(|| "POLL N/A".into(), |value| format!("POLL {value}"));
    let wti = status.wti_alias.as_ref().map_or("WTI STATE N/A", |alias| {
        if alias.status == "historical_only" && !alias.equivalence_assumed {
            "WTI HIST != BRENT"
        } else {
            "WTI ID INVALID"
        }
    });
    let freshness = if status.stale {
        "STALE SNAPSHOT"
    } else {
        "CURRENT"
    };
    format!(" HIP-3 RESEARCH // REPORT ONLY // {freshness} // {wti} // {poll} ")
}

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let status = &app.backend.hip3_roster;
    if !status.configured {
        render_empty(
            frame,
            app,
            area,
            " HIP-3 RESEARCH // REPORT ONLY ",
            "Roster checkpoint not configured",
        );
        return;
    }
    if !status.available {
        render_empty(
            frame,
            app,
            area,
            " HIP-3 RESEARCH // UNAVAILABLE // NO LOCAL FALLBACK ",
            status
                .issue
                .as_deref()
                .unwrap_or("Backend roster unavailable"),
        );
        return;
    }
    let rows = status.markets.iter().map(|market| {
        let values = market_row_values(market);
        let style = if market.open_order_count > 0 || market.position_size_signed != 0.0 {
            app.theme.gold
        } else {
            app.theme.muted
        };
        Row::new(values.into_iter().map(Cell::from)).style(style)
    });
    let account_header = if status.stale { "LAST ACCT" } else { "ACCT" };
    let table = Table::new(
        rows,
        [
            Constraint::Length(13),
            Constraint::Length(9),
            Constraint::Length(6),
            Constraint::Length(7),
            Constraint::Length(8),
            Constraint::Length(8),
            Constraint::Min(5),
        ],
    )
    .column_spacing(1)
    .header(
        Row::new([
            "SYMBOL",
            "MID",
            "SPRD",
            "D5/D20",
            "TAKER bp",
            "FUND bp",
            account_header,
        ])
        .style(app.theme.header),
    )
    .block(panel(roster_title(status), app));
    frame.render_widget(table, area);
}

fn position_label(market: &Hip3MarketTelemetry) -> String {
    if market.position_size_signed > 0.0 {
        format!("L{:.2}", market.position_size_signed)
    } else if market.position_size_signed < 0.0 {
        format!("S{:.2}", market.position_size_signed.abs())
    } else if market.open_order_count > 0 {
        format!("{} ORD", market.open_order_count)
    } else {
        "FLAT".into()
    }
}
