//! Compact rendering for executable missed-opportunity research evidence.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_checkpoint::CohortObserverProviderEvidence;
use crate::backend_cohort_execution_opportunity_matrix::{
    CohortExecutionOpportunityComparison, CohortExecutionOpportunityMatrix,
    CohortExecutionOpportunityScope,
};
use crate::backend_cohort_forward_challenger::{
    CohortCandidatePortfolioJournal, CohortForwardOneBlockerChallenger,
};
use crate::cohort_opportunity_matrix_provenance::matrix_provenance_text;
use crate::cohort_research_forward_contract::{
    contract_text as forward_contract_text, summary_text as forward_contract_summary,
    timing_text as forward_contract_timing_text,
};
use crate::cohort_research_forward_format::{
    context_15m_text, entry_context_text,
    experiment_detail_title as forward_experiment_detail_title,
    experiment_title as forward_experiment_title, payoff_geometry_text,
};
use crate::cohort_router_format::human_token;
use crate::cohort_widgets::provider_alias;

/// Build the evidence-health summary line when a matrix is attached.
pub(crate) fn summary_line(app: &App) -> Option<Line<'static>> {
    let matrix = app
        .backend
        .cohort_checkpoint
        .execution_opportunity_matrix
        .as_ref()?;
    let broadest = matrix.broadest_all_cohort()?;
    Some(Line::from(vec![
        Span::styled("EXEC MISS MATRIX ", app.theme.cyan),
        Span::raw(format!(
            "{} // {} // {}C REPORT-ONLY, NON-ADDITIVE // BROADEST {} {} N{} {}/{} {:+.1}bps PF {} // L{}/S{}",
            matrix_provenance_text(matrix.provenance.as_ref()),
            hypothesis_scope_text(matrix.scope.as_ref(), matrix.hypotheses),
            matrix.comparisons,
            broadest.symbol,
            provider_alias(&broadest.strategy_id),
            broadest.resolved,
            broadest.wins,
            broadest.losses,
            broadest.total_net_return_bps,
            sampled_profit_factor(broadest.resolved, broadest.profit_factor),
            broadest.long_resolved,
            broadest.short_resolved,
        )),
    ]))
}

/// Build one explicit status line for every attached post-cutoff challenger.
pub(crate) fn forward_summary_lines(app: &App) -> Vec<Line<'static>> {
    let Some(matrix) = app
        .backend
        .cohort_checkpoint
        .execution_opportunity_matrix
        .as_ref()
    else {
        return Vec::new();
    };
    matrix
        .forward_challenger
        .iter()
        .chain(&matrix.supplemental_forward_challengers)
        .map(|forward| forward_summary_line(forward, app))
        .collect()
}

fn forward_summary_line(forward: &CohortForwardOneBlockerChallenger, app: &App) -> Line<'static> {
    let portfolio = forward.portfolio_journal.as_ref().map_or_else(
        || "FIT N/A".into(),
        |journal| {
            let performance = deployable_performance_text(journal)
                .map_or_else(String::new, |value| format!(" // {value}"));
            format!(
                "FIT {}/{}{}",
                journal.deployable, journal.attempts, performance
            )
        },
    );
    Line::from(vec![
        Span::styled(
            format!("{} ", forward_experiment_title(forward)),
            app.theme.gold,
        ),
        Span::raw(format!(
            "{} // {} // CAND {} SELECT {} PENDING {} // {} // L{}/S{} // {}",
            forward_contract_summary(&forward.execution_contract),
            human_token(&forward.state),
            forward.exact_candidates,
            forward.selected_non_overlapping,
            forward
                .selected_non_overlapping
                .saturating_sub(forward.resolved),
            mechanism_performance_text(
                forward.resolved,
                forward.wins,
                forward.losses,
                forward.total_net_return_bps,
                forward.profit_factor,
            ),
            forward.long_resolved,
            forward.short_resolved,
            portfolio,
        )),
    ])
}

/// Build provider-specific rows for the research inspector.
pub(crate) fn detail_lines(item: &CohortObserverProviderEvidence, app: &App) -> Vec<Line<'static>> {
    let Some(matrix) = &app.backend.cohort_checkpoint.execution_opportunity_matrix else {
        return Vec::new();
    };
    let rows = provider_rows(matrix, item);
    if rows.is_empty() {
        return Vec::new();
    }
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!(
                "EXECUTABLE MISSED SETUPS // {} // REPORT-ONLY 60M BBO // ROWS ARE NON-ADDITIVE",
                matrix_provenance_text(matrix.provenance.as_ref())
            ),
            app.theme.cyan,
        )),
    ];
    lines.extend(rows.into_iter().map(|row| {
        let concentration = row
            .largest_abs_contribution_fraction
            .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0));
        Line::from(format!(
            "{:>7}  {}  N{} {}/{} NET {:+.1}bps PF {} CONC {} STOP {} L{}/S{}",
            row.opi_cohort.to_uppercase(),
            human_token(&row.blocker),
            row.resolved,
            row.wins,
            row.losses,
            row.total_net_return_bps,
            sampled_profit_factor(row.resolved, row.profit_factor),
            concentration,
            row.stop_proxy_crosses,
            row.long_resolved,
            row.short_resolved,
        ))
    }));
    if let Some(forward) = matrix
        .forward_challenger
        .iter()
        .chain(&matrix.supplemental_forward_challengers)
        .find(|forward| observer_matches(forward, item))
    {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            format!(
                "{} // NO EXECUTION AUTHORITY",
                forward_experiment_detail_title(forward)
            ),
            app.theme.gold,
        )));
        lines.push(Line::from(forward_contract_text(
            &forward.execution_contract,
        )));
        lines.push(Line::from(forward_contract_timing_text(
            &forward.execution_contract,
        )));
        lines.push(Line::from(format!(
            "{} // CAND {} SELECT {} PENDING {} // {} STOP {} L{}/S{}",
            human_token(&forward.state),
            forward.exact_candidates,
            forward.selected_non_overlapping,
            forward
                .selected_non_overlapping
                .saturating_sub(forward.resolved),
            mechanism_performance_text(
                forward.resolved,
                forward.wins,
                forward.losses,
                forward.total_net_return_bps,
                forward.profit_factor,
            ),
            forward.stop_proxy_crosses,
            forward.long_resolved,
            forward.short_resolved,
        )));
        lines.push(Line::from(format!(
            "UPDATED {} // CONCENTRATION {}",
            forward.generated_at_utc,
            forward
                .largest_abs_contribution_fraction
                .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0),),
        )));
        if let Some(context) = &forward.entry_context_summary {
            lines.push(Line::from(Span::styled(
                entry_context_text(context),
                app.theme.cyan,
            )));
        }
        if let Some(context) = &forward.context_15m_summary {
            lines.push(Line::from(Span::styled(
                context_15m_text(context),
                app.theme.carry,
            )));
        }
        if let Some(geometry) = &forward.payoff_geometry {
            lines.push(Line::from(Span::styled(
                payoff_geometry_text(geometry),
                app.theme.bear,
            )));
        }
        lines.extend(portfolio_detail_lines(forward, app));
        if let Some(latest) = &forward.latest_execution {
            lines.push(Line::from(format!(
                "LAST {} {:.4} -> {:.4} // NET {:+.1}bps = GROSS {:+.1} - FEE {:.1} + FUND {:+.1}",
                latest.side.to_uppercase(),
                latest.entry_price,
                latest.exit_price,
                latest.net_return_bps,
                latest.gross_return_bps,
                latest.fee_bps,
                latest.funding_bps,
            )));
            lines.push(Line::from(format!(
                "PATH MFE {:+.1}bps / MAE {:+.1}bps // {} // ORIGIN {}",
                latest.mfe_bps,
                latest.mae_bps,
                human_token(&latest.exit_reason),
                latest.source_run_id,
            )));
        }
    }
    lines
}

fn portfolio_detail_lines(
    forward: &CohortForwardOneBlockerChallenger,
    app: &App,
) -> Vec<Line<'static>> {
    let Some(journal) = &forward.portfolio_journal else {
        return vec![Line::from(Span::styled(
            "INCREMENTAL PORTFOLIO // JOURNAL UNAVAILABLE",
            app.theme.bear,
        ))];
    };
    let mut lines = vec![portfolio_summary_line(journal, app)];
    if let Some(latest) = &journal.latest_attempt {
        let positions = latest.open_position_count.map_or_else(
            || "POS N/A / FREE N/A".into(),
            |open| {
                format!(
                    "POS {} / FREE {}",
                    open,
                    latest.available_position_slots.unwrap_or_default()
                )
            },
        );
        let outcome = latest.net_return_bps.map_or_else(
            || "OUTCOME PENDING".into(),
            |net| format!("NET {net:+.1}bps"),
        );
        lines.push(Line::from(format!(
            "LAST {} // {} // {} // {} // ROUTE A{}/W{}",
            latest.side.to_uppercase(),
            human_token(&latest.classification),
            positions,
            outcome,
            latest.same_cycle_action_count,
            latest.same_cycle_withheld_count,
        )));
        if let Some(line) = pending_entry_context_line(latest, app) {
            lines.push(line);
        }
        if let Some(line) = pending_path_line(latest, app) {
            lines.push(line);
        }
    }
    lines
}

fn pending_entry_context_line(
    latest: &crate::backend_cohort_forward_challenger::CohortCandidatePortfolioAttempt,
    app: &App,
) -> Option<Line<'static>> {
    let state_5m = human_token(latest.state_5m.as_deref()?);
    let structure = latest.structural_direction.as_deref()?.to_uppercase();
    let mut fields = Vec::new();
    if let Some(value) = latest.state_1m.as_deref() {
        fields.push(format!("1M {}", human_token(value)));
    }
    fields.push(format!("5M {state_5m}"));
    if let Some(value) = latest.context_15m.as_deref() {
        fields.push(format!("15M {}", human_token(value)));
    }
    if let Some(value) = latest.primary_regime.as_deref() {
        fields.push(format!("PRIMARY {}", human_token(value)));
    }
    fields.push(format!("STRUCT {structure}"));
    let mut context = fields.join(" // ");
    if let Some(value) = latest.breakout_volume_ratio {
        context.push_str(&format!(" // VOL {value:.2}x"));
    }
    if let Some(value) = latest.current_bbwp_percentile {
        context.push_str(&format!(" // BBWP {value:.1}"));
    }
    if let Some(value) = latest.regime_strength {
        context.push_str(&format!(" // STRENGTH {:.0}%", value * 100.0));
    }
    Some(Line::from(vec![
        Span::styled("ENTRY MTF ", app.theme.cyan),
        Span::raw(context),
    ]))
}

fn pending_path_line(
    latest: &crate::backend_cohort_forward_challenger::CohortCandidatePortfolioAttempt,
    app: &App,
) -> Option<Line<'static>> {
    let net = latest.current_estimated_net_return_bps?;
    let mfe = latest.mfe_bps?;
    let mae = latest.mae_bps?;
    let remaining = latest.remaining_ms? as f64 / 60_000.0;
    let capacity = if latest.current_exit_top_level_capacity? {
        "BBO EXIT CAP OK"
    } else {
        "BBO EXIT CAP SHORT"
    };
    Some(Line::from(vec![
        Span::styled("PENDING PATH ", app.theme.gold),
        Span::raw(format!(
            "MARK NET {net:+.1}bps // MFE {mfe:+.1} / MAE {mae:+.1}bps // {remaining:.1}m LEFT // {capacity}"
        )),
    ]))
}

fn portfolio_summary_line(journal: &CohortCandidatePortfolioJournal, app: &App) -> Line<'static> {
    let performance =
        deployable_performance_text(journal).unwrap_or_else(|| format!("RES {}", journal.resolved));
    Line::from(vec![
        Span::styled("INCREMENTAL PORTFOLIO ", app.theme.cyan),
        Span::raw(format!(
            "DEPLOYABLE {}/{} // {} // WAIT {} // CONFLICT POS {} CAP {} ROUTE {} UNKNOWN {}",
            journal.deployable,
            journal.attempts,
            performance,
            journal.pending,
            journal.existing_symbol_position,
            journal.portfolio_capacity,
            journal.same_cycle_symbol_action,
            journal.portfolio_state_unavailable,
        )),
    ])
}

fn deployable_performance_text(journal: &CohortCandidatePortfolioJournal) -> Option<String> {
    let mut text = format!(
        "INCR N{} {}/{} NET {:+.1}bps PF {}",
        journal.deployable_resolved?,
        journal.deployable_wins?,
        journal.deployable_losses?,
        journal.deployable_total_net_return_bps?,
        sampled_profit_factor(
            journal.deployable_resolved.unwrap_or_default(),
            journal.deployable_profit_factor,
        ),
    );
    if let Some(concentration) = journal.deployable_largest_abs_contribution_fraction {
        text.push_str(&format!(" CONC {:.0}%", concentration * 100.0));
    }
    Some(text)
}

fn mechanism_performance_text(
    resolved: usize,
    wins: usize,
    losses: usize,
    net_return_bps: f64,
    profit_factor_value: Option<f64>,
) -> String {
    format!(
        "MECH N{resolved} {wins}/{losses} NET {net_return_bps:+.1}bps PF {}",
        sampled_profit_factor(resolved, profit_factor_value),
    )
}

fn provider_rows<'a>(
    matrix: &'a CohortExecutionOpportunityMatrix,
    item: &CohortObserverProviderEvidence,
) -> Vec<&'a CohortExecutionOpportunityComparison> {
    matrix
        .results
        .iter()
        .filter(|row| row.strategy_id == item.strategy_id && row.symbol == item.symbol)
        .collect()
}

fn profit_factor(value: Option<f64>) -> String {
    value.map_or_else(|| "NO-LOSS".into(), |number| format!("{number:.2}"))
}

fn sampled_profit_factor(resolved: usize, value: Option<f64>) -> String {
    if resolved == 0 {
        "N/A".into()
    } else {
        profit_factor(value)
    }
}

fn hypothesis_scope_text(
    scope: Option<&CohortExecutionOpportunityScope>,
    hypotheses: usize,
) -> String {
    scope.map_or_else(
        || format!("EXEC HYP {hypotheses} // SCOPE UNAVAILABLE"),
        |value| {
            format!(
                "EXEC HYP {}/{} // OBSERVE-ONLY {}",
                value.executable_hypotheses,
                value.observed_hypotheses,
                value.excluded_non_executable_hypotheses,
            )
        },
    )
}

fn observer_matches(
    forward: &CohortForwardOneBlockerChallenger,
    item: &CohortObserverProviderEvidence,
) -> bool {
    forward.portfolio_journal.as_ref().is_some_and(|journal| {
        journal.source_strategy_id == item.strategy_id && journal.symbol == item.symbol
    })
}

#[cfg(test)]
#[path = "cohort_research_opportunity_matrix_tests.rs"]
mod tests;
