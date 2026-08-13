//! Read-only Hulk Smash signal-engine screen.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Row, Table},
};

use crate::app::App;

/// Render scored completed-bar decisions without inventing a regime model.
pub fn render_signal_engine(f: &mut Frame, app: &App, area: Rect) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),
            Constraint::Length(8),
            Constraint::Length(8),
            Constraint::Min(8),
        ])
        .split(area);
    render_signal_contract(f, app, chunks[0]);
    render_evidence(f, app, chunks[1]);
    render_execution_contract(f, app, chunks[2]);
    render_decision_audit(f, app, chunks[3]);
}

fn render_signal_contract(f: &mut Frame, app: &App, area: Rect) {
    let hulk = &app.backend.hulk_smash;
    let action = app
        .backend
        .latest_decision_action
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    let lines = vec![
        Line::from(vec![
            Span::styled("SCORE ", app.theme.cyan),
            Span::styled(score_pair(hulk.score, hulk.minimum_score), app.theme.gold),
            Span::raw(" │ ACTION "),
            Span::styled(action, app.theme.title),
        ]),
        Line::from(format!(
            "TRIGGER {} │ CANDIDATE {}",
            label(hulk.trigger.as_deref()),
            label(hulk.candidate.as_deref())
        )),
        Line::from(format!(
            "AUTHORITY SHORT ONLY │ COMPLETED BARS ONLY │ NEXT 30m BAR EXECUTION │ MAX ENTRY AGE {}s",
            number(
                &app.backend.execution_policy,
                "maximum_entry_delay_seconds",
                0
            )
        )),
        Line::from("NO REGIME CLASSIFICATION │ NO 1m/5m/15m ALIGNMENT CLAIM"),
        Line::from(format!(
            "LAST BAR {} │ REASON {}",
            app.backend
                .latest_regime_feed_ts
                .as_deref()
                .unwrap_or("N/A"),
            label(app.backend.latest_regime_reason.as_deref())
        )),
    ];
    render_panel(f, app, area, " HULK SMASH 30m SIGNAL ENGINE ", lines);
}

fn render_evidence(f: &mut Frame, app: &App, area: Rect) {
    let hulk = &app.backend.hulk_smash;
    let evidence = if hulk.evidence.is_empty() {
        "NOT REPORTED".to_string()
    } else {
        hulk.evidence
            .iter()
            .map(|value| value.to_uppercase())
            .collect::<Vec<_>>()
            .join(" │ ")
    };
    let lines = vec![
        Line::from(evidence),
        Line::from(format!(
            "MIN SCORE {} │ PIVOT {} bars │ ADX USABLE {} │ ADX TRENDING {}",
            number(&app.backend.strategy_params, "minimum_score", 0),
            number(&app.backend.strategy_params, "pivot_bars", 0),
            number(&app.backend.strategy_params, "adx_usable", 1),
            number(&app.backend.strategy_params, "adx_trending", 1),
        )),
        Line::from(format!(
            "SUPERTREND {}/{} │ ADX PERIOD {} │ SQUEEZE PERIOD {}",
            number(&app.backend.strategy_params, "supertrend_period", 0),
            number(&app.backend.strategy_params, "supertrend_multiplier", 1),
            number(&app.backend.strategy_params, "adx_period", 0),
            number(&app.backend.strategy_params, "squeeze_period", 0),
        )),
        Line::from("EVIDENCE IS A SCORE CONTRIBUTION, NOT AN INDEPENDENT TRADE GATE"),
    ];
    render_panel(f, app, area, " CAUSAL SIGNAL EVIDENCE ", lines);
}

fn render_execution_contract(f: &mut Frame, app: &App, area: Rect) {
    let hulk = &app.backend.hulk_smash;
    let state = app.backend.live_state.as_deref().unwrap_or("FLAT");
    let arm = if app.backend.live_armed == Some(true) {
        "LIVE ARMED"
    } else {
        "DISARMED"
    };
    let lines = vec![
        Line::from(format!(
            "STATE {state} │ AUTHORITY {arm} │ 5x ISOLATED │ ONE BTC POSITION"
        )),
        Line::from(format!(
            "STOP {} │ TARGET {} │ {}",
            money(hulk.planned_stop_price),
            money(hulk.planned_target_price),
            r_multiple(hulk.planned_target_r_multiple)
        )),
        Line::from(format!(
            "STOP CLAMP {}-{} bps │ STRUCTURAL ANCHOR {}",
            number(&app.backend.exits, "minimum_stop_bps", 1),
            number(&app.backend.exits, "maximum_stop_bps", 1),
            money(hulk.stop_anchor)
        )),
        Line::from(format!(
            "MAX HOLD {} bars │ RISK {}% EQUITY │ VENUE FUNDING + FEES RECORDED",
            number(&app.backend.exits, "maximum_hold_bars", 0),
            scaled(&app.backend.risk, "risk_fraction", 100.0, 3)
        )),
        Line::from(format!(
            "ACK {} │ SLIPPAGE {} │ {} │ LIQ DIST {}",
            milliseconds(hulk.latest_ack_latency_ms),
            bps(hulk.latest_slippage_bps),
            markout_summary(
                hulk.latest_markout_horizon_ms,
                hulk.latest_markout_target_ms,
                hulk.latest_markout_lateness_ms,
                hulk.latest_markout_recovered_after_restart,
                hulk.latest_markout_bps,
            ),
            percent(hulk.liquidation_distance_pct),
        )),
    ];
    render_panel(f, app, area, " RECONCILED EXECUTION PLAN ", lines);
}

fn render_decision_audit(f: &mut Frame, app: &App, area: Rect) {
    let rows = app
        .backend
        .hulk_smash
        .recent_decisions
        .iter()
        .rev()
        .map(|event| {
            Row::new(vec![
                event.timestamp.clone(),
                event
                    .score
                    .map_or_else(|| "N/A".into(), |value| value.to_string()),
                event.action.replace('_', " ").to_uppercase(),
                event.reason.replace('_', " ").to_uppercase(),
            ])
        });
    let table = Table::new(
        rows,
        [
            Constraint::Length(26),
            Constraint::Length(8),
            Constraint::Length(20),
            Constraint::Min(20),
        ],
    )
    .header(Row::new(["BAR TIME", "SCORE", "ACTION", "REASON"]))
    .block(
        Block::default()
            .title(" COMPLETED-BAR DECISION AUDIT ")
            .title_style(app.theme.title)
            .borders(Borders::ALL)
            .border_style(app.theme.border),
    );
    f.render_widget(table, area);
}

fn render_panel(f: &mut Frame, app: &App, area: Rect, title: &str, lines: Vec<Line<'static>>) {
    let block = Block::default()
        .title(title)
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_style(app.theme.border);
    f.render_widget(Paragraph::new(lines).block(block), area);
}

fn score_pair(score: Option<u64>, minimum: Option<u64>) -> String {
    format!(
        "{} / {}",
        score.map_or_else(|| "N/A".into(), |value| value.to_string()),
        minimum.map_or_else(|| "N/A".into(), |value| value.to_string())
    )
}

fn label(value: Option<&str>) -> String {
    value
        .map(|text| text.replace('_', " ").to_uppercase())
        .unwrap_or_else(|| "NOT REPORTED".into())
}

fn money(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("${number:.2}"))
}

fn r_multiple(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1}R"))
}

fn number(value: &serde_json::Value, key: &str, precision: usize) -> String {
    value
        .get(key)
        .and_then(serde_json::Value::as_f64)
        .map_or_else(|| "N/A".into(), |number| format!("{number:.precision$}"))
}

fn scaled(value: &serde_json::Value, key: &str, factor: f64, precision: usize) -> String {
    value
        .get(key)
        .and_then(serde_json::Value::as_f64)
        .map_or_else(
            || "N/A".into(),
            |number| format!("{:.precision$}", number * factor),
        )
}

fn milliseconds(value: Option<u64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number}ms"))
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:+.2} bps"))
}

fn percent(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.2}%"))
}

fn markout_summary(
    horizon_ms: Option<u64>,
    target_ms: Option<u64>,
    lateness_ms: Option<u64>,
    recovered_after_restart: Option<bool>,
    markout_bps: Option<f64>,
) -> String {
    let Some(markout) = markout_bps else {
        return "MARKOUT N/A".into();
    };
    let mut result = format!("{} MARKOUT {markout:+.2} bps", duration(horizon_ms));
    if let Some(target) = target_ms {
        let restart = if recovered_after_restart == Some(true) {
            " · RESTART"
        } else {
            ""
        };
        let late =
            lateness_ms.map_or_else(String::new, |value| format!(" +{}", duration(Some(value))));
        result.push_str(&format!(
            " [TARGET {}{restart}{late}]",
            duration(Some(target))
        ));
    }
    result
}

fn duration(value: Option<u64>) -> String {
    value.map_or_else(
        || "N/A".into(),
        |milliseconds| {
            if milliseconds % 1_000 == 0 {
                format!("{}s", milliseconds / 1_000)
            } else if milliseconds > 1_000 {
                format!("{:.1}s", milliseconds as f64 / 1_000.0)
            } else {
                format!("{milliseconds}ms")
            }
        },
    )
}
