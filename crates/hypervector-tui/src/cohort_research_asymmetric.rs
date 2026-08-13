//! Compact rendering for the predeclared asymmetric portfolio observer.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_asymmetric_forward::{
    CohortAsymmetricEconomics, CohortAsymmetricForwardObserver,
};

pub(crate) fn line_count(evidence: Option<&CohortAsymmetricForwardObserver>) -> u16 {
    if evidence.is_some() { 3 } else { 0 }
}

pub(crate) fn lines(evidence: &CohortAsymmetricForwardObserver, app: &App) -> Vec<Line<'static>> {
    let texts = summary_texts(evidence);
    vec![
        Line::from(vec![
            Span::styled(texts[0].clone(), app.theme.title),
            Span::styled(" // REPORT ONLY", app.theme.gold),
        ]),
        Line::from(vec![
            Span::styled(
                candidate_text(&evidence.candidate),
                economics_style(app, &evidence.candidate),
            ),
            Span::raw(" // "),
            Span::styled(
                control_text(&evidence.excluded_symmetric_sides),
                economics_style(app, &evidence.excluded_symmetric_sides),
            ),
        ]),
        Line::from(Span::styled(texts[2].clone(), app.theme.muted)),
    ]
}

pub(crate) fn summary_texts(evidence: &CohortAsymmetricForwardObserver) -> [String; 3] {
    [
        format!(
            "ASYM PORTFOLIO {} // CUT {}",
            human_state(&evidence.evidence_state),
            evidence.predeclared_at_utc
        ),
        format!(
            "{} // {}",
            candidate_text(&evidence.candidate),
            control_text(&evidence.excluded_symmetric_sides)
        ),
        format!(
            "SOURCE POST CAND {} CTRL {} // PRE-CUT {} // PROFILE MISMATCH {} // UNRELATED {}",
            evidence.source_counts.candidate_post_cutoff,
            evidence.source_counts.excluded_symmetric_post_cutoff,
            evidence.source_counts.pre_cutoff_in_scope,
            evidence.source_counts.profile_mismatch_in_scope,
            evidence.source_counts.unrelated,
        ),
    ]
}

fn candidate_text(value: &CohortAsymmetricEconomics) -> String {
    format!("CAND {}", economics_text(value))
}

fn control_text(value: &CohortAsymmetricEconomics) -> String {
    format!("CTRL {}", economics_text(value))
}

fn economics_text(value: &CohortAsymmetricEconomics) -> String {
    format!(
        "T{} {}W/{}L NET {} PF {}",
        value.closed_trades,
        value.wins,
        value.losses,
        usd(value.net_pnl_usd),
        value
            .profit_factor
            .map_or_else(|| "N/A".into(), |factor| format!("{factor:.2}")),
    )
}

fn economics_style(app: &App, value: &CohortAsymmetricEconomics) -> ratatui::style::Style {
    if value.net_pnl_usd > 0.0 {
        app.theme.bull
    } else if value.net_pnl_usd < 0.0 {
        app.theme.bear
    } else {
        app.theme.muted
    }
}

fn human_state(value: &str) -> String {
    value.replace('_', " ").to_uppercase()
}

fn usd(value: f64) -> String {
    if value >= 0.0 {
        format!("+${value:.2}")
    } else {
        format!("-${:.2}", value.abs())
    }
}

#[cfg(test)]
mod tests {
    use super::summary_texts;
    use crate::backend_cohort_asymmetric_forward::{
        CohortAsymmetricEconomics, CohortAsymmetricForwardObserver, CohortAsymmetricSourceCounts,
    };

    #[test]
    fn awaiting_observer_is_explicit_about_zero_evidence() {
        let evidence = observer(0, 0, "awaiting_post_cutoff_resolution");

        let lines = summary_texts(&evidence);

        assert!(lines[0].contains("AWAITING POST CUTOFF RESOLUTION"));
        assert!(lines[1].contains("CAND T0"));
        assert!(lines[1].contains("CTRL T0"));
    }

    #[test]
    fn resolved_observer_separates_candidate_from_symmetric_control() {
        let evidence = observer(2, 1, "prospective_resolutions_observed");

        let lines = summary_texts(&evidence);

        assert!(lines[1].contains("CAND T2 1W/1L NET +$0.50 PF 2.00"));
        assert!(lines[1].contains("CTRL T1 0W/1L NET -$1.00 PF 0.00"));
        assert!(lines[2].contains("PRE-CUT 3"));
        assert!(lines[2].contains("PROFILE MISMATCH 0"));
    }

    fn observer(
        candidate_trades: usize,
        control_trades: usize,
        state: &str,
    ) -> CohortAsymmetricForwardObserver {
        CohortAsymmetricForwardObserver {
            evidence_state: state.into(),
            predeclared_at_utc: "2026-08-09T06:02:47Z".into(),
            entry_cutoff_timestamp_ms: 1_786_255_367_000,
            candidate: economics(candidate_trades, 0.5, Some(2.0)),
            excluded_symmetric_sides: economics(control_trades, -1.0, Some(0.0)),
            source_counts: CohortAsymmetricSourceCounts {
                candidate_post_cutoff: candidate_trades,
                excluded_symmetric_post_cutoff: control_trades,
                pre_cutoff_in_scope: 3,
                profile_mismatch_in_scope: 0,
                unrelated: 4,
            },
        }
    }

    fn economics(
        closed_trades: usize,
        net_pnl_usd: f64,
        profit_factor: Option<f64>,
    ) -> CohortAsymmetricEconomics {
        CohortAsymmetricEconomics {
            closed_trades,
            wins: usize::from(closed_trades > 1),
            losses: usize::from(closed_trades > 0),
            breakeven: 0,
            net_pnl_usd,
            fees_usd: 0.2,
            funding_usd: -0.02,
            profit_factor,
            median_return_on_margin_pct: Some(1.0),
            net_pnl_excluding_largest_winner_usd: Some(-0.5),
        }
    }
}
