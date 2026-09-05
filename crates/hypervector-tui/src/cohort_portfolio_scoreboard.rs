//! Summary-first capital, performance, and risk cards for the cohort dashboard.

use ratatui::{
    Frame,
    layout::{Constraint, Layout, Rect},
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
};

use crate::app::App;
use crate::backend_cohort::CohortAccount;
use crate::backend_cohort_checkpoint::CohortVenuePortfolio;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;
use crate::cohort_format::money;
use crate::cohort_open_concentration::{largest_open_cluster, open_cluster_label};
use crate::cohort_sizing_evidence::portfolio_capacity_line;
use crate::cohort_widgets::{panel, provider_alias, safe_ratio};

/// Render the dashboard's high-signal portfolio scorecards.
pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect, account: &CohortAccount) {
    let cards = Layout::horizontal([
        Constraint::Percentage(44),
        Constraint::Percentage(28),
        Constraint::Percentage(28),
    ])
    .split(area);
    render_performance(frame, app, cards[0]);
    render_capital(frame, app, cards[1], account);
    render_risk(frame, app, cards[2], account);
}

fn render_performance(frame: &mut Frame, app: &App, area: Rect) {
    let Some(performance) = app.backend.cohort_checkpoint.trade_performance.as_ref() else {
        crate::cohort_widgets::render_empty(
            frame,
            app,
            area,
            " PORTFOLIO SCORECARD ",
            "Awaiting backend lifecycle performance",
        );
        return;
    };
    if performance
        .current_run
        .as_ref()
        .is_some_and(|run| app.backend.run_id.as_deref() != Some(run.run_id.as_str()))
    {
        crate::cohort_widgets::render_empty(
            frame,
            app,
            area,
            " PORTFOLIO PERFORMANCE // LIVE LEDGER ",
            "Current-run performance identity mismatch",
        );
        return;
    }
    let (scope_label, current) = performance.current_run.as_ref().map_or_else(
        || {
            performance
                .current_profile
                .as_ref()
                .map_or(("CURRENT SCOPE", &performance.total), |profile| {
                    ("CURRENT PROFILE", &profile.total)
                })
        },
        |run| ("THIS RUN", &run.total),
    );
    let history = app
        .backend
        .cohort_checkpoint
        .all_time_performance()
        .map_or(&performance.total, |value| &value.total);
    let lines = vec![
        scope_counts(scope_label, current, app),
        scope_metrics(current, app),
        scope_counts("ALL-TIME", history, app),
        scope_metrics(history, app),
        cost_line("RUN", current),
        cost_line("ALL", history),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" PORTFOLIO PERFORMANCE // LIVE LEDGER ", app)),
        area,
    );
}

fn scope_counts<'a>(label: &'a str, value: &CohortTradePerformanceSummary, app: &App) -> Line<'a> {
    Line::from(vec![
        Span::raw(format!("{label} {} CLOSED  ", value.closed_trades)),
        Span::styled(format!("W{}", value.wins), app.theme.bull),
        Span::raw(" "),
        Span::styled(format!("L{}", value.losses), app.theme.bear),
        Span::raw(format!(" BE{}", value.breakeven)),
    ])
}

fn scope_metrics<'a>(value: &CohortTradePerformanceSummary, app: &App) -> Line<'a> {
    let pnl_style = signed_style(value.net_pnl_usd, app);
    let win_rate = value
        .win_rate_pct
        .map_or_else(|| "N/A".into(), |number| format!("{number:.1}%"));
    Line::from(vec![
        Span::raw(format!("  WR {win_rate}  NET ")),
        Span::styled(signed_dollars(value.net_pnl_usd), pnl_style),
        Span::raw("  PF "),
        Span::styled(profit_factor(value), app.theme.gold),
    ])
}

fn cost_line<'a>(label: &'a str, value: &CohortTradePerformanceSummary) -> Line<'a> {
    Line::from(format!(
        "{label} CLOSED FEES {}  FUND {}  CASH DRAG {}",
        money(value.fees_usd),
        signed_funding(value.funding_usd),
        signed_dollars(value.fees_usd - value.funding_usd),
    ))
}

fn render_capital(frame: &mut Frame, app: &App, area: Rect, account: &CohortAccount) {
    let path = app.backend.cohort_checkpoint.portfolio.as_ref();
    let venue = app.backend.cohort_checkpoint.venue_portfolio.as_ref();
    let run_change = path.map(|value| signed_dollars(value.equity_change_usd));
    let lines = vec![
        metric_line(
            "PORTFOLIO",
            displayed_portfolio_value(venue).map_or_else(|| "N/A".into(), money),
            venue.map_or(app.theme.gate_blocked, |_| app.theme.cyan),
        ),
        metric_line(
            "USDC COLL",
            venue.map_or_else(
                || money(account.account_value_usd),
                |value| money(value.execution_collateral_value_usd),
            ),
            app.theme.gold,
        ),
        available_line(account, app),
        spot_and_vault_line(venue, app),
        metric_line(
            "RUN Δ",
            run_change.unwrap_or_else(|| "N/A".into()),
            path.map_or(app.theme.muted, |value| {
                signed_style(value.equity_change_usd, app)
            }),
        ),
        Line::from(format!(
            "SOURCE {}",
            balance_source(account.account_balance_source.as_deref())
        )),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" CAPITAL PATH ", app)),
        area,
    );
}

fn available_line<'a>(account: &CohortAccount, app: &App) -> Line<'a> {
    let ratio = safe_ratio(account.withdrawable_usd, account.account_value_usd).unwrap_or(0.0);
    let filled = (ratio * 6.0).round() as usize;
    Line::from(vec![
        Span::raw("FREE "),
        Span::styled(money(account.withdrawable_usd), app.theme.bull),
        Span::raw(" "),
        Span::styled("━".repeat(filled.min(6)), app.theme.bull),
        Span::styled(
            "─".repeat(6usize.saturating_sub(filled)),
            app.theme.bar_ghost,
        ),
        Span::raw(format!(" {:.1}%", ratio * 100.0)),
    ])
}

fn spot_and_vault_line<'a>(value: Option<&CohortVenuePortfolio>, app: &App) -> Line<'a> {
    let Some(value) = value else {
        return Line::from(Span::styled("OTHER SPOT N/A", app.theme.gate_blocked));
    };
    Line::from(vec![
        Span::raw("OTHER SPOT "),
        Span::styled(money(value.non_usdc_spot_value_usd), app.theme.carry),
        Span::raw("  VAULT "),
        Span::styled(money(value.vault_equity_usd), app.theme.cyan),
    ])
}

fn displayed_portfolio_value(venue: Option<&CohortVenuePortfolio>) -> Option<f64> {
    venue.map(|value| value.portfolio_value_usd)
}

fn render_risk(frame: &mut Frame, app: &App, area: Rect, account: &CohortAccount) {
    let maximum = app.backend.cohort.maximum_concurrent_positions;
    let path = app.backend.cohort_checkpoint.portfolio.as_ref();
    let margin_ratio = safe_ratio(account.total_margin_used_usd, account.account_value_usd);
    let lines = vec![
        Line::from(format!(
            "OPEN {} / {maximum}  //  ONE PER COIN // PROTECTED",
            account.open_position_count
        )),
        Line::from(format!(
            "NOTIONAL {}  MARGIN {} // ISO",
            money(account.total_notional_position_usd),
            money(account.total_margin_used_usd),
        )),
        ratio_meter("MARGIN UTIL", margin_ratio, app, app.theme.gold),
        Line::from(format!(
            "MAX DD {}  PEAK POS {}",
            path.map_or_else(
                || "N/A".into(),
                |value| { format!("{:.2}%", value.maximum_drawdown_pct) }
            ),
            path.map_or_else(
                || "N/A".into(),
                |value| value.maximum_open_positions.to_string()
            ),
        )),
        open_cluster_line(app),
        portfolio_capacity_line(app),
    ];
    frame.render_widget(
        Paragraph::new(lines).block(panel(" RISK ENVELOPE ", app)),
        area,
    );
}

fn open_cluster_line<'a>(app: &'a App) -> Line<'a> {
    let trades = &app.backend.cohort_checkpoint.open_trade_reflections;
    let Some(cluster) = largest_open_cluster(trades) else {
        return Line::from(Span::styled("CLUSTER FLAT", app.theme.muted));
    };
    let style = match cluster.side.as_str() {
        "long" => app.theme.bull,
        "short" => app.theme.bear,
        _ => app.theme.gold,
    };
    Line::from(Span::styled(
        open_cluster_label(&cluster, provider_alias(&cluster.strategy_id)),
        style,
    ))
}

fn ratio_meter<'a>(label: &'a str, ratio: Option<f64>, app: &App, style: Style) -> Line<'a> {
    let Some(value) = ratio else {
        return Line::from(Span::styled(
            format!("{label} UNAVAILABLE"),
            app.theme.gate_blocked,
        ));
    };
    let filled = (value * 8.0).round() as usize;
    Line::from(vec![
        Span::raw(format!("{label} ")),
        Span::styled("━".repeat(filled.min(8)), style),
        Span::styled(
            "─".repeat(8usize.saturating_sub(filled)),
            app.theme.bar_ghost,
        ),
        Span::raw(format!(" {:.2}%", value * 100.0)),
    ])
}

fn metric_line<'a>(label: &'a str, value: String, style: Style) -> Line<'a> {
    Line::from(vec![
        Span::raw(format!("{label} ")),
        Span::styled(value, style),
    ])
}

fn signed_style(value: f64, app: &App) -> Style {
    if value > 0.0 {
        app.theme.bull
    } else if value < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

fn signed_dollars(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

fn signed_funding(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.4}")
    } else {
        format!("-${:.4}", value.abs())
    }
}

fn profit_factor(value: &CohortTradePerformanceSummary) -> String {
    if value.closed_trades == 0 {
        return "N/A".into();
    }
    value
        .profit_factor
        .map_or_else(|| "NO LOSSES".into(), |number| format!("{number:.2}"))
}

fn balance_source(value: Option<&str>) -> &'static str {
    match value {
        Some("spot_clearinghouse_state") => "UNIFIED SPOT",
        Some("perp_clearinghouse_state") => "PERP CLEARINGHOUSE",
        _ => "NOT REPORTED",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn venue_portfolio() -> CohortVenuePortfolio {
        CohortVenuePortfolio {
            portfolio_value_usd: 507.08,
            execution_collateral_value_usd: 504.11,
            non_usdc_spot_value_usd: 2.97,
            vault_equity_usd: 0.0,
            valued_spot_assets: Vec::new(),
            observed_at_utc: "2026-08-04T09:00:00+00:00".into(),
            valuation_source: "spot_midpoints_plus_vault_equity".into(),
        }
    }

    #[test]
    fn unified_portfolio_uses_atomic_venue_total_instead_of_mixed_timestamps() {
        let observed = displayed_portfolio_value(Some(&venue_portfolio()));
        assert_eq!(observed, Some(507.08));
    }

    #[test]
    fn standard_account_keeps_atomic_checkpoint_total() {
        assert_eq!(
            displayed_portfolio_value(Some(&venue_portfolio())),
            Some(507.08),
        );
    }

    #[test]
    fn empty_performance_sample_is_not_rendered_as_a_rate_or_profit_factor() {
        let app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        let line = scope_metrics(&CohortTradePerformanceSummary::default(), &app);
        let text = line
            .spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<String>();

        assert!(text.contains("WR N/A"), "{text}");
        assert!(text.contains("PF N/A"), "{text}");
        assert!(!text.contains("0.0%"), "{text}");
        assert!(!text.contains("NO LOSSES"), "{text}");
    }

    #[test]
    fn lifecycle_cost_line_does_not_imply_open_fill_costs_are_missing() {
        let line = cost_line(
            "RUN",
            &CohortTradePerformanceSummary {
                fees_usd: 0.42,
                funding_usd: 0.07,
                ..CohortTradePerformanceSummary::default()
            },
        );
        let text = line
            .spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<String>();

        assert_eq!(
            text,
            "RUN CLOSED FEES $0.42  FUND +$0.0700  CASH DRAG +$0.35"
        );
    }
}
