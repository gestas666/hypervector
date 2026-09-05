//! Strategy qualification and exact live-sample detail lines.

use std::collections::BTreeMap;

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_allocation::CohortAllocationChallenger;
use crate::backend_cohort_repeatability::CohortRepeatabilityEvidence;
use crate::backend_cohort_trade_performance::CohortTradePerformanceSummary;
use crate::cohort_observer_evidence::CohortObserverProviderEvidence;
use crate::cohort_route_authority::provider_route_label;
use crate::cohort_router_format::human_token;

pub(crate) fn scorecard_lines<'a>(
    item: &'a CohortObserverProviderEvidence,
    app: &App,
) -> Vec<Line<'a>> {
    let route = provider_route_label(
        &app.backend.cohort.providers,
        &item.strategy_id,
        &item.symbol,
        app.backend.live_armed,
    );
    let state = item
        .research_state
        .as_deref()
        .map_or_else(|| "NOT REPORTED BY THIS RUN".into(), human_token);
    let confidence = item.confidence.as_deref().unwrap_or("N/A").to_uppercase();
    let assessment = item
        .forward_assessment
        .as_deref()
        .map_or_else(|| "NOT REPORTED BY THIS RUN".into(), human_token);
    let mut lines = vec![
        Line::from(format!("FROZEN SOURCE {state} // CONFIDENCE {confidence}")),
        Line::from(format!(
            "SOURCE CADENCE {}",
            item.historical_cadence.as_deref().unwrap_or("NOT REPORTED")
        )),
        Line::from(format!("FORWARD {assessment}")),
        Line::from(format!(
            "HISTORY {}",
            item.historical_summary.as_deref().unwrap_or("NOT REPORTED")
        )),
        Line::from(format!(
            "SOURCE {}",
            item.evidence_source.as_deref().unwrap_or("NOT REPORTED")
        )),
        Line::from(Span::styled(
            format!("ROUTE {route} // RESEARCH REPORT ONLY // NO AUTO FILTER OR SIZE"),
            app.theme.gold,
        )),
    ];
    lines.extend(directional_lines(item, app));
    if let Some(performance) = &item.execution_performance {
        lines.push(Line::from(Span::styled(
            "FROZEN OUTCOME LABEL // RESOLVED LIVE RESULTS BELOW",
            app.theme.cyan,
        )));
        lines.push(Line::from(""));
        lines.extend(execution_performance_lines(
            performance,
            &item.execution_performance_by_side,
            item.execution_performance_scope.as_deref(),
            app,
        ));
    }
    if let Some(repeatability) = &item.repeatability_evidence {
        lines.push(Line::from(""));
        lines.extend(repeatability_lines(repeatability, app));
    }
    if let Some(allocation) = allocation_for(item, app) {
        lines.push(Line::from(""));
        lines.extend(allocation_lines(allocation, app));
    }
    lines
}

fn repeatability_lines<'a>(value: &CohortRepeatabilityEvidence, app: &App) -> Vec<Line<'a>> {
    let summary = &value.summary;
    let cadence = summary.trades_per_24h_observed.map_or_else(
        || "CADENCE NOT ESTABLISHED".into(),
        |rate| format!("{rate:.2}/DAY OBSERVED"),
    );
    let concentration = summary
        .largest_winner_share_of_gross_profit_pct
        .map_or_else(
            || "NO GROSS WINNER IN SAMPLE // DESCRIPTIVE".into(),
            |share| format!("LARGEST WINNER {share:.1}% OF GROSS PROFIT // DESCRIPTIVE"),
        );
    let leave_best = summary
        .net_pnl_excluding_largest_winner_usd
        .map_or_else(|| "N/A".into(), signed_usd);
    vec![
        Line::from(Span::styled(
            format!(
                "REPEATABILITY // {} CLOSED OVER {:.1}H // {cadence}",
                summary.closed_trades, summary.observation_span_hours,
            ),
            app.theme.carry,
        )),
        Line::from(format!(
            "MEAN {} // MEDIAN {} // LEAVE-BEST {leave_best}",
            signed_usd(summary.mean_net_pnl_usd),
            signed_usd(summary.median_net_pnl_usd),
        )),
        Line::from(concentration),
        Line::from(Span::styled(
            "NO FORECAST // NO TRADE-COUNT OR BALANCE GATE",
            app.theme.cyan,
        )),
    ]
}

fn allocation_for<'a>(
    item: &CohortObserverProviderEvidence,
    app: &'a App,
) -> Option<&'a CohortAllocationChallenger> {
    let value = app
        .backend
        .cohort_checkpoint
        .allocation_challenger
        .as_ref()?;
    let key = format!("{}|{}", item.strategy_id, item.symbol);
    (value.target_provider_symbol == key).then_some(value)
}

fn allocation_lines<'a>(value: &CohortAllocationChallenger, app: &App) -> Vec<Line<'a>> {
    let sample = &value.execution_sample;
    let sample_line = match (sample.closed_trades, sample.net_pnl_usd) {
        (Some(closed), Some(net)) => format!(
            "LINKED LIVE SAMPLE {closed} CLOSED // NET {} // PF {}",
            signed_usd(net),
            optional_number(sample.profit_factor),
        ),
        _ => "LINKED LIVE SAMPLE NOT YET RESOLVED".into(),
    };
    let mut lines = vec![
        Line::from(Span::styled(
            "ALLOCATION CHALLENGER // CANDIDATE NOT ACTIVE",
            app.theme.gold,
        )),
        Line::from(format!(
            "CAP ${:.2} -> ${:.2} // MARGIN ${:.2} -> ${:.2}",
            value.current.planned_notional_usd,
            value.candidate.planned_notional_usd,
            value.current.planned_margin_usd,
            value.candidate.planned_margin_usd,
        )),
        Line::from(format!(
            "PORTFOLIO MAX MARGIN {:.2}% -> {:.2}% ({:+.2}pp)",
            value.portfolio.current_maximum_margin_fraction * 100.0,
            value.portfolio.candidate_maximum_margin_fraction * 100.0,
            value.portfolio.change_percentage_points,
        )),
        Line::from(sample_line),
    ];
    if let Some(capacity) = &value.visible_depth_capacity {
        lines.extend(capacity_lines(capacity));
    }
    lines.extend([
        Line::from(format!(
            "ACCOUNT ${:.2} IS A SIZING INPUT // NOT A BALANCE GATE",
            value.account_value_usd,
        )),
        Line::from(Span::styled(
            if value.effective_change {
                "NO PROFIT FORECAST // EXPLICIT CONFIG RESTART REQUIRED"
            } else {
                "CAP INERT AT CURRENT BALANCE // STILL NOT A BALANCE GATE"
            },
            app.theme.cyan,
        )),
    ]);
    lines
}

fn capacity_lines(
    value: &crate::backend_cohort_allocation::CohortAllocationCapacity,
) -> [Line<'static>; 2] {
    let long_p95 = optional_number(value.long.p95_impact_bps);
    let short_p95 = optional_number(value.short.p95_impact_bps);
    [
        Line::from(format!(
            "LIVE L2 {} SNAP // ${:.0} IOC LONG {:.1}% BBO {:.1}% P95 {long_p95}bp",
            value.snapshot_count,
            value.candidate_notional_usd,
            value.long.complete_rate * 100.0,
            value.long.bbo_fill_rate * 100.0,
        )),
        Line::from(format!(
            "SHORT {:.1}% BBO {:.1}% P95 {short_p95}bp // MIN BBO ${:.0}/${:.0}",
            value.short.complete_rate * 100.0,
            value.short.bbo_fill_rate * 100.0,
            value.long.minimum_bbo_notional_usd,
            value.short.minimum_bbo_notional_usd,
        )),
    ]
}

fn directional_lines<'a>(item: &'a CohortObserverProviderEvidence, app: &App) -> Vec<Line<'a>> {
    let mut lines = Vec::new();
    for side in ["long", "short"] {
        let Some(evidence) = item.directional_research.get(side) else {
            continue;
        };
        let style = if side == "long" {
            app.theme.bull
        } else {
            app.theme.bear
        };
        lines.push(Line::from(Span::styled(
            format!(
                "{} {} // CONFIDENCE {} // {}",
                side.to_uppercase(),
                human_token(&evidence.research_state),
                evidence.confidence.to_uppercase(),
                evidence.cadence,
            ),
            style,
        )));
        lines.push(Line::from(format!(
            "{} NOTE {}",
            side.to_uppercase(),
            evidence.summary
        )));
    }
    lines
}

fn execution_performance_lines<'a>(
    value: &CohortTradePerformanceSummary,
    sides: &BTreeMap<String, CohortTradePerformanceSummary>,
    scope: Option<&str>,
    app: &App,
) -> Vec<Line<'a>> {
    let heading = if scope == Some("provider_execution_contract_history") {
        "LIVE CONFIG-CONTRACT SAMPLE // RESOLVED VENUE LIFECYCLES"
    } else {
        "LIVE PROFILE SAMPLE // RESOLVED VENUE LIFECYCLES"
    };
    let mut lines = vec![
        Line::from(Span::styled(heading, app.theme.cyan)),
        Line::from(format!(
            "CLOSED {} // W/L/BE {}/{}/{} // WR {}",
            value.closed_trades,
            value.wins,
            value.losses,
            value.breakeven,
            optional_pct(value.win_rate_pct, 1),
        )),
        Line::from(format!(
            "NET {} // RETURN {} // PF {}",
            signed_usd(value.net_pnl_usd),
            optional_signed_pct(value.net_return_on_margin_pct),
            optional_number(value.profit_factor),
        )),
        Line::from(format!(
            "FEES ${:.2} // FUNDING {} // DESCRIPTIVE ONLY",
            value.fees_usd,
            signed_usd(value.funding_usd),
        )),
    ];
    lines.extend(side_performance_lines(sides, app));
    lines
}

fn side_performance_lines<'a>(
    sides: &BTreeMap<String, CohortTradePerformanceSummary>,
    app: &App,
) -> Vec<Line<'a>> {
    ["long", "short"]
        .into_iter()
        .filter_map(|side| {
            let value = sides.get(side)?;
            let style = if side == "long" {
                app.theme.bull
            } else {
                app.theme.bear
            };
            Some(Line::from(Span::styled(
                format!(
                    "{} {}  {}W/{}L/{}BE  NET {}  PF {}",
                    side.to_uppercase(),
                    value.closed_trades,
                    value.wins,
                    value.losses,
                    value.breakeven,
                    signed_usd(value.net_pnl_usd),
                    optional_number(value.profit_factor),
                ),
                style,
            )))
        })
        .collect()
}

fn optional_pct(value: Option<f64>, precision: usize) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.precision$}%"))
}

fn optional_signed_pct(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2}%"))
}

fn optional_number(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}"))
}

fn signed_usd(value: f64) -> String {
    if value.is_sign_negative() {
        format!("-${:.2}", value.abs())
    } else {
        format!("+${value:.2}")
    }
}
