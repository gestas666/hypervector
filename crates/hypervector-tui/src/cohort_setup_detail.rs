//! Full backend-authored evidence for the selected strategy setup.

use std::collections::BTreeMap;

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
};
use serde_json::Value;

use crate::app::App;
use crate::backend_cohort::CohortProviderEvaluation;
use crate::cohort_route_authority::provider_route_label;
use crate::cohort_route_contract::{execution_label, risk_label, timing_label};
use crate::cohort_widgets::{provider_alias, provider_identity_label};

const HULK_STRATEGY_ID: &str = "hulk_expansion_bidirectional_tuned_v2";
const HULK_ENTRY_CONTRACT: &str = "hulk_expansion_moderate_adx_v1";

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let Some(setup) = app
        .backend
        .cohort
        .evaluations
        .get(app.selected_cohort_setup_index)
    else {
        return;
    };
    let modal = centered_rect(88, 78, area);
    crate::cohort_detail_scroll::render(
        frame,
        app,
        modal,
        " SETUP INSPECTOR // EXACT DECISION EVIDENCE ",
        setup_lines(setup, app),
    );
}

fn setup_lines<'a>(setup: &'a CohortProviderEvaluation, app: &'a App) -> Vec<Line<'a>> {
    let mut lines = identity_lines(setup, app);
    lines.extend(configured_contract_lines(setup, app));
    lines.extend(research_lines(setup, app));
    lines.extend(regime_lines(setup));
    lines.extend(hype_entry_attribution_lines(setup, app));
    lines.extend(readiness_lines(setup, app));
    lines
}

fn configured_contract_lines<'a>(setup: &CohortProviderEvaluation, app: &'a App) -> Vec<Line<'a>> {
    vec![
        Line::from(execution_label(setup, &app.backend.cohort.providers)),
        Line::from(risk_label(
            setup,
            &app.backend.cohort.providers,
            &app.backend.cohort.asset_configs,
        )),
    ]
}

fn research_lines<'a>(setup: &CohortProviderEvaluation, app: &'a App) -> Vec<Line<'a>> {
    let evidence =
        app.backend.cohort.strategy_evidence.iter().find(|record| {
            record.strategy_id == setup.strategy_id && record.symbol == setup.symbol
        });
    let Some(record) = evidence else {
        return vec![Line::from(Span::styled(
            "RESEARCH STATE NOT REPORTED BY THIS RUN",
            app.theme.muted,
        ))];
    };
    let route = provider_route_label(
        &app.backend.cohort.providers,
        &setup.strategy_id,
        &setup.symbol,
        app.backend.live_armed,
    );
    vec![
        Line::from(format!(
            "RESEARCH STATE {}  //  CONFIDENCE {}",
            crate::cohort_router_format::human_token(&record.research_state),
            record.confidence.to_uppercase(),
        )),
        Line::from(format!("CADENCE {}", record.cadence)),
        Line::from(format!("SUMMARY {}", record.summary)),
        Line::from(format!("SOURCE {}", record.evidence_source)),
        Line::from(Span::styled(
            format!("ROUTE {route} // RESEARCH REPORT ONLY // DOES NOT GATE EXECUTION"),
            app.theme.gold,
        )),
    ]
}

fn identity_lines<'a>(setup: &'a CohortProviderEvaluation, app: &App) -> Vec<Line<'a>> {
    let mut lines = vec![
        Line::from(vec![
            Span::styled(provider_alias(&setup.strategy_id), app.theme.title),
            Span::raw(format!(
                "  //  {}  //  {}",
                setup.symbol,
                side(setup.side.as_deref())
            )),
        ]),
        Line::from(provider_identity_label(&setup.strategy_id)),
        Line::from(format!(
            "{} // REFERENCE {:.8}",
            timing_label(setup),
            setup.reference_price,
        )),
        Line::from(format!(
            "DECISION {}  //  ELIGIBLE {}  //  REASON {}",
            setup.decision_action.to_uppercase(),
            yes_no(setup.eligible),
            setup.reason,
        )),
    ];
    if let Some(reason) = setup.backend_non_action_reason.as_deref() {
        lines.push(Line::from(Span::styled(
            format!(
                "BACKEND ACTION NONE  //  {}",
                crate::cohort_router_format::human_token(reason)
            ),
            app.theme.gold,
        )));
    }
    lines
}

fn regime_lines(setup: &CohortProviderEvaluation) -> Vec<Line<'static>> {
    vec![
        Line::from(format!(
            "REGIME 1M {}  //  PRIMARY 5M {}  //  CONTEXT 15M {}",
            optional(setup.state_1m.as_deref()),
            optional(
                setup
                    .state_5m
                    .as_deref()
                    .or(setup.primary_regime.as_deref())
            ),
            optional(setup.context_15m.as_deref()),
        )),
        Line::from(format!(
            "CONFIDENCE {}  //  SCORE {}  //  TRIGGER {}",
            setup
                .confidence
                .map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0)),
            match (setup.score, setup.minimum_score) {
                (Some(score), Some(minimum)) => format!("{score}/{minimum}"),
                _ => "N/A".into(),
            },
            optional(setup.trigger.as_deref()),
        )),
    ]
}

fn readiness_lines<'a>(setup: &'a CohortProviderEvaluation, app: &App) -> Vec<Line<'a>> {
    let readiness = &setup.readiness;
    vec![
        Line::from(readiness_summary(setup)),
        Line::from(""),
        Line::from(Span::styled("LIVE INDICATORS", app.theme.cyan)),
        Line::from(if readiness.indicators.is_empty() {
            "N/A".into()
        } else {
            readiness.indicators.join("  ·  ")
        }),
        Line::from(""),
        Line::from(Span::styled(readiness_gap_heading(setup), app.theme.gold)),
        Line::from(if readiness.blockers.is_empty() {
            "NONE REPORTED".into()
        } else {
            readiness
                .blockers
                .iter()
                .map(|value| crate::cohort_router_format::human_token(value))
                .collect::<Vec<_>>()
                .join("  ·  ")
        }),
        Line::from(""),
        Line::from(Span::styled(
            "BACKEND EVIDENCE ONLY  //  [Enter/Esc] CLOSE",
            app.theme.muted,
        )),
    ]
}

fn readiness_summary(setup: &CohortProviderEvaluation) -> String {
    let readiness = &setup.readiness;
    if let (Some(score), Some(minimum)) = (setup.score, setup.minimum_score)
        && has_exact_hulk_entry_contract(setup)
    {
        return format!(
            "ENTRY CONTRACT {:.1}%  //  EXACT CONDITIONS {}/{}  //  SIGNAL SCORE {score}/{minimum}  //  NOT A WIN PROBABILITY",
            readiness.readiness_fraction * 100.0,
            readiness.conditions_met,
            readiness.conditions_required,
        );
    }
    if let (Some(score), Some(minimum)) = (setup.score, setup.minimum_score)
        && setup.strategy_id == HULK_STRATEGY_ID
    {
        return format!(
            "SUPPORT COVERAGE {:.1}%  //  CONTEXT CONDITIONS {}/{}  //  SIGNAL SCORE {score}/{minimum}  //  NOT A WIN PROBABILITY",
            readiness.readiness_fraction * 100.0,
            readiness.conditions_met,
            readiness.conditions_required,
        );
    }
    format!(
        "READINESS {:.1}%  //  CONDITIONS {}/{}  //  NOT A WIN PROBABILITY",
        readiness.readiness_fraction * 100.0,
        readiness.conditions_met,
        readiness.conditions_required,
    )
}

fn readiness_gap_heading(setup: &CohortProviderEvaluation) -> &'static str {
    if setup.strategy_id != HULK_STRATEGY_ID {
        return "BLOCKERS TO NEXT STATE";
    }
    if has_exact_hulk_entry_contract(setup) && setup.eligible {
        "ENTRY CONTRACT SATISFIED"
    } else if has_exact_hulk_entry_contract(setup) {
        "UNMET EXACT ENTRY CONDITIONS"
    } else if setup.readiness.blockers.is_empty() {
        "SUPPORT CONDITIONS SATISFIED"
    } else {
        "MISSING SUPPORT"
    }
}

fn has_exact_hulk_entry_contract(setup: &CohortProviderEvaluation) -> bool {
    setup.strategy_id == HULK_STRATEGY_ID
        && text_metric(&setup.readiness.metrics, "entry_contract") == Some(HULK_ENTRY_CONTRACT)
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

fn optional(value: Option<&str>) -> &str {
    value
        .filter(|item| !item.trim().is_empty())
        .unwrap_or("N/A")
}

fn side(value: Option<&str>) -> String {
    optional(value).to_uppercase()
}

fn yes_no(value: bool) -> &'static str {
    if value { "YES" } else { "NO" }
}

fn hype_entry_attribution_lines<'a>(
    setup: &CohortProviderEvaluation,
    app: &'a App,
) -> Vec<Line<'a>> {
    let texts = hype_entry_attribution_texts(&setup.readiness.metrics);
    if texts.is_empty() {
        return Vec::new();
    }
    let mut lines = vec![Line::from("")];
    lines.push(Line::from(Span::styled(texts[0].clone(), app.theme.cyan)));
    lines.extend(texts.into_iter().skip(1).map(Line::from));
    lines
}

fn hype_entry_attribution_texts(metrics: &BTreeMap<String, Value>) -> Vec<String> {
    if text_metric(metrics, "entry_feature_authority") != Some("report_only") {
        return Vec::new();
    }
    let status = text_metric(metrics, "entry_feature_status")
        .unwrap_or("unavailable")
        .to_uppercase();
    let heading = match text_metric(metrics, "candidate_authority") {
        Some("automatic_execution") => {
            format!("ETH TRANSFER FILTER // AUTOMATIC EXECUTION INPUT // {status}")
        }
        Some(_) => format!("ETH TRANSFER FILTER // REPORT ONLY // {status}"),
        None => {
            format!("HYPE 1M ATTRIBUTION // REPORT ONLY // NOT EXECUTION TRIGGER // {status}")
        }
    };
    vec![
        heading,
        format!(
            "1M BODY {}bps // CLEAR {}bps // RANGE {}bps",
            signed_metric(metrics, "directional_bar_body_bps", 2),
            signed_metric(metrics, "breakout_clearance_20m_bps", 2),
            plain_metric(metrics, "bar_range_bps", 2),
        ),
        format!(
            "1M VOL20 {}x // BK VOL {}x",
            plain_metric(metrics, "volume_ratio_20m", 2),
            plain_metric(metrics, "breakout_volume_ratio", 2),
        ),
        format!(
            "PRE-BBWP MIN {} // <25 {}/15 // NOW {} // STRENGTH {}",
            plain_metric(metrics, "prior_bbwp_min_15m", 1),
            plain_metric(metrics, "prior_bbwp_below25_count_15m", 0),
            plain_metric(metrics, "current_bbwp_percentile", 1),
            percent_metric(metrics, "regime_strength"),
        ),
        format!(
            "RET 5/15/60 {}/{}/{}bps // 1M/15M ALIGN {}/{}",
            signed_metric(metrics, "directional_return_5m_bps", 2),
            signed_metric(metrics, "directional_return_15m_bps", 2),
            signed_metric(metrics, "directional_return_60m_bps", 2),
            alignment_metric(metrics, "state_1m_alignment"),
            alignment_metric(metrics, "context_15m_alignment"),
        ),
        format!(
            "SMA/EMA {}/{}bps // RSI DIST {}",
            signed_metric(metrics, "sma_gap_directional_bps", 2),
            signed_metric(metrics, "ema_gap_directional_bps", 2),
            signed_metric(metrics, "rsi_directional_distance", 2),
        ),
    ]
}

fn text_metric<'a>(metrics: &'a BTreeMap<String, Value>, name: &str) -> Option<&'a str> {
    metrics.get(name).and_then(Value::as_str)
}

fn number_metric(metrics: &BTreeMap<String, Value>, name: &str) -> Option<f64> {
    metrics.get(name).and_then(Value::as_f64)
}

fn plain_metric(metrics: &BTreeMap<String, Value>, name: &str, precision: usize) -> String {
    number_metric(metrics, name)
        .map_or_else(|| "N/A".into(), |value| format!("{value:.precision$}"))
}

fn signed_metric(metrics: &BTreeMap<String, Value>, name: &str, precision: usize) -> String {
    number_metric(metrics, name)
        .map_or_else(|| "N/A".into(), |value| format!("{value:+.precision$}"))
}

fn percent_metric(metrics: &BTreeMap<String, Value>, name: &str) -> String {
    number_metric(metrics, name)
        .map_or_else(|| "N/A".into(), |value| format!("{:.0}%", value * 100.0))
}

fn alignment_metric(metrics: &BTreeMap<String, Value>, name: &str) -> &'static str {
    number_metric(metrics, name).map_or("N/A", |value| if value >= 0.5 { "YES" } else { "NO" })
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use serde_json::{Value, json};

    use super::hype_entry_attribution_texts;

    #[test]
    fn hype_entry_attribution_is_compact_and_explicitly_report_only() {
        let metrics: BTreeMap<String, Value> = serde_json::from_value(json!({
            "entry_feature_authority": "report_only",
            "entry_feature_status": "measured",
            "directional_bar_body_bps": -4.25,
            "breakout_clearance_20m_bps": 8.5,
            "volume_ratio_20m": 1.75,
            "breakout_volume_ratio": 2.6,
            "prior_bbwp_min_15m": 12.0,
            "prior_bbwp_below25_count_15m": 4.0,
            "current_bbwp_percentile": 88.0,
            "regime_strength": 0.72,
            "directional_return_5m_bps": 6.0,
            "directional_return_15m_bps": 14.0,
            "directional_return_60m_bps": 31.0,
            "state_1m_alignment": 1.0,
            "context_15m_alignment": 0.0,
            "sma_gap_directional_bps": 18.0,
            "ema_gap_directional_bps": 9.0,
            "rsi_directional_distance": 7.5,
            "bar_range_bps": 22.0
        }))
        .expect("metrics fixture");

        let lines = hype_entry_attribution_texts(&metrics);

        assert_eq!(
            lines[0],
            "HYPE 1M ATTRIBUTION // REPORT ONLY // NOT EXECUTION TRIGGER // MEASURED"
        );
        assert_eq!(
            lines[1],
            "1M BODY -4.25bps // CLEAR +8.50bps // RANGE 22.00bps"
        );
        assert_eq!(lines[2], "1M VOL20 1.75x // BK VOL 2.60x");
        assert_eq!(
            lines[3],
            "PRE-BBWP MIN 12.0 // <25 4/15 // NOW 88.0 // STRENGTH 72%"
        );
        assert_eq!(
            lines[4],
            "RET 5/15/60 +6.00/+14.00/+31.00bps // 1M/15M ALIGN YES/NO"
        );
        assert_eq!(lines[5], "SMA/EMA +18.00/+9.00bps // RSI DIST +7.50");
    }

    #[test]
    fn eth_transfer_attribution_labels_automatic_execution_inputs() {
        let metrics: BTreeMap<String, Value> = serde_json::from_value(json!({
            "candidate_authority": "automatic_execution",
            "entry_policy_authority": "automatic_execution",
            "entry_feature_authority": "report_only",
            "entry_feature_status": "measured",
            "directional_bar_body_bps": -4.25,
            "breakout_clearance_20m_bps": 8.5,
            "volume_ratio_20m": 1.75,
            "breakout_volume_ratio": 2.6,
            "prior_bbwp_min_15m": 12.0,
            "prior_bbwp_below25_count_15m": 4.0,
            "current_bbwp_percentile": 88.0,
            "regime_strength": 0.72,
            "directional_return_5m_bps": 6.0,
            "directional_return_15m_bps": 14.0,
            "directional_return_60m_bps": 31.0,
            "state_1m_alignment": 1.0,
            "context_15m_alignment": 0.0,
            "sma_gap_directional_bps": 18.0,
            "ema_gap_directional_bps": 9.0,
            "rsi_directional_distance": 7.5,
            "bar_range_bps": 22.0
        }))
        .expect("metrics fixture");

        let lines = hype_entry_attribution_texts(&metrics);

        assert_eq!(
            lines[0],
            "ETH TRANSFER FILTER // AUTOMATIC EXECUTION INPUT // MEASURED"
        );
    }
}
