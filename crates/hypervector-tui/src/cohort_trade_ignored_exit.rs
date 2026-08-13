//! Closed-lifecycle view of provider exits ignored by the bound execution plan.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_ignored_provider_exit::{
    CohortClosedIgnoredProviderExit, CohortIgnoredProviderActualExit,
};
use crate::backend_cohort_open_path::CohortOpenPath;
use crate::cohort_format::{fill_time, signed_money};
use crate::cohort_router_format::human_token;

/// Format report-only ignored-exit evidence for the closed-trade inspector.
pub(crate) fn lines(outcome: &CohortClosedIgnoredProviderExit, app: &App) -> Vec<Line<'static>> {
    match outcome.status.as_str() {
        "observed" => observed_lines(outcome, app),
        "no_ignored_exit_observed" => vec![status_line(
            "PROVIDER EXIT REVIEW // POLICY IGNORE // NO IGNORED EXIT OBSERVED",
            app,
        )],
        "not_applicable_policy_honors" => vec![status_line(
            "PROVIDER EXIT REVIEW // POLICY HONOR // NOT APPLICABLE",
            app,
        )],
        "unavailable_bound_policy" => vec![status_line(
            "PROVIDER EXIT REVIEW // BOUND POLICY UNAVAILABLE",
            app,
        )],
        _ => vec![status_line("PROVIDER EXIT REVIEW // INVALID STATUS", app)],
    }
}

fn observed_lines(outcome: &CohortClosedIgnoredProviderExit, app: &App) -> Vec<Line<'static>> {
    let (Some(signal), Some(path), Some(gross_continuation_bps)) = (
        outcome.first_signal.as_ref(),
        outcome.path_from_first_signal_to_actual_exit.as_ref(),
        outcome.gross_continuation_from_signal_bps,
    ) else {
        return vec![status_line(
            "PROVIDER EXIT REVIEW // INCOMPLETE OBSERVED EVIDENCE",
            app,
        )];
    };
    let mut lines = vec![
        status_line(
            format!(
                "PROVIDER EXIT IGNORED // POLICY IGNORE // SIGNALS {}",
                outcome.ignored_signal_count
            ),
            app,
        ),
        Line::from(format!(
            "FIRST SIGNAL {} @ ${:.8} / {} // ENTRY RET {:+.2}bps",
            human_token(&signal.exit_reason),
            signal.reference_price,
            fill_time(signal.decision_time_ms),
            signal.entry_directional_return_bps,
        )),
        Line::from(format!(
            "SIGNAL→ACTUAL GROSS {:+.2}bps // {} BARS",
            gross_continuation_bps, path.completed_bars,
        )),
        path_excursion_line(path, app),
    ];
    lines.extend(actual_exit_lines(&outcome.actual_exit, app));
    lines
}

fn actual_exit_lines(actual: &CohortIgnoredProviderActualExit, app: &App) -> [Line<'static>; 3] {
    [
        Line::from(format!(
            "ACTUAL EXIT ${:.8} @ {} // {} // CTRL {}",
            actual.price,
            fill_time(actual.venue_timestamp_ms),
            actual
                .exit_reason
                .as_deref()
                .map_or_else(|| "N/A".into(), human_token),
            human_token(&actual.exit_controller_strategy_id),
        )),
        Line::from(format!(
            "ACTUAL NET ${} // FEES ${:.2} // FUNDING ${:+.4}",
            signed_money(actual.net_pnl_usd),
            actual.fees_usd,
            actual.funding_usd,
        )),
        Line::from(Span::styled(
            "COUNTERFACTUAL NET UNAVAILABLE // SIGNAL REFERENCE IS NOT A VENUE FILL",
            app.theme.muted,
        )),
    ]
}

fn path_excursion_line(path: &CohortOpenPath, app: &App) -> Line<'static> {
    match (
        path.maximum_favorable_excursion_bps,
        path.maximum_adverse_excursion_bps,
        path.peak_giveback_bps,
    ) {
        (Some(mfe), Some(mae), Some(giveback)) => Line::from(format!(
            "PATH MFE {mfe:+.2}bps // MAE {mae:.2}bps // GIVEBACK {giveback:.2}bps"
        )),
        _ => Line::from(Span::styled("PATH EXCURSION UNAVAILABLE", app.theme.muted)),
    }
}

fn status_line(text: impl Into<String>, app: &App) -> Line<'static> {
    Line::from(Span::styled(text.into(), app.theme.gold))
}
