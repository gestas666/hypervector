//! Compact, backend-only source-follow risk and readiness presentation.

use ratatui::text::Line;
use serde_json::Value;

use crate::app::App;

/// Build responsive dashboard policy lines from authoritative backend identity.
pub(crate) fn policy_lines(app: &App, width: u16, height: u16) -> Vec<Line<'static>> {
    if width < 90 || height < 6 {
        return compact_policy_lines(app);
    }
    let action = action(app);
    vec![
        Line::from(risk_contract(app)),
        Line::from(format!(
            "ELIGIBLE SIDE {} | LAST ACTION {action}",
            execution_sides(app)
        )),
        Line::from(format!(
            "{} | NO FIXED STOP | ENTRY/TARGET MAKER | MAX-HOLD TAKER",
            target_contract(app)
        )),
        Line::from(evidence_contract(app)),
    ]
}

fn compact_policy_lines(app: &App) -> Vec<Line<'static>> {
    let target = smart_percent(app.backend.exits.get("target_margin_pct"));
    let price_bps = app
        .backend
        .exits
        .get("target_price_fraction")
        .and_then(Value::as_f64)
        .map_or_else(
            || "N/A".into(),
            |value| format!("{:.2}bps", value * 10_000.0),
        );
    let gaps = app
        .backend
        .runtime
        .get("active_book_gap_windows")
        .and_then(Value::as_u64)
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    vec![
        Line::from(format!(
            "RISK {} x {} = {} NOTIONAL | ISOLATED",
            percent(app.backend.risk.get("margin_fraction"), 100.0),
            multiple(app.backend.strategy_params.get("leverage")),
            multiple(app.backend.risk.get("notional_fraction")),
        )),
        Line::from(format!(
            "SIDES L+S | ACTION {} | TP {target} / {price_bps} | NO STOP",
            action(app)
        )),
        Line::from(format!("DEV ONLY | EXEC INCONCLUSIVE | BOOK GAPS {gaps}")),
    ]
}

/// Build the five chart diagnostics without inventing missing readiness values.
pub(crate) fn chart_lines(app: &App, levels: String) -> Vec<Line<'static>> {
    let snap = app.current_snapshot();
    vec![
        Line::from(format!(
            "5m SOURCE {} | {} | SIGNAL {}",
            snap.trend_5m,
            execution_sides(app),
            action(app)
        )),
        Line::from(readiness_contract(app)),
        Line::from(format!(
            "POSITION {} | U/PNL {:+.2} | ENTRY FEE ${:.2} | FUNDING ${:.2}",
            app.active_position.direction,
            app.paper_stats.unrealized_pnl,
            app.active_position.entry_fee_usd,
            app.active_position.funding_payment_usd
        )),
        Line::from(levels),
        Line::from(format!(
            "{} | NO FIXED STOP | MAX HOLD {}",
            target_contract(app),
            hours(app.backend.exits.get("maximum_hold_seconds"))
        )),
    ]
}

fn risk_contract(app: &App) -> String {
    format!(
        "RISK {} MARGIN x {} = {} EQUITY NOTIONAL | ISOLATED",
        percent(app.backend.risk.get("margin_fraction"), 100.0),
        multiple(app.backend.strategy_params.get("leverage")),
        multiple(app.backend.risk.get("notional_fraction")),
    )
}

fn target_contract(app: &App) -> String {
    format!(
        "TARGET {} GROSS MARGIN / {} PRICE",
        smart_percent(app.backend.exits.get("target_margin_pct")),
        bps(app.backend.exits.get("target_price_fraction")),
    )
}

fn readiness_contract(app: &App) -> String {
    format!(
        "CONF {} >= {} | RANGE {} IN [{}, {}]",
        confidence(app.backend.latest_regime_confidence),
        percent(app.backend.regime_policy.get("minimum_confidence"), 100.0),
        optional_bps(app.backend.source_follow_signal_range_bps),
        number_value(
            app.backend
                .regime_policy
                .get("minimum_completed_5m_range_bps")
        ),
        number_value(
            app.backend
                .regime_policy
                .get("maximum_completed_5m_range_bps")
        ),
    )
}

fn evidence_contract(app: &App) -> String {
    let status = app
        .backend
        .runtime
        .get("evidence_status")
        .and_then(Value::as_str)
        .map(|value| value.replace('_', " ").to_uppercase())
        .unwrap_or_else(|| "RESEARCH EVIDENCE NOT REPORTED".into());
    let economics: String = match app
        .backend
        .runtime
        .get("execution_economics_conclusive")
        .and_then(Value::as_bool)
    {
        Some(true) => "EXECUTION ECONOMICS CONCLUSIVE".into(),
        Some(false) => "EXECUTION ECONOMICS INCONCLUSIVE".into(),
        None => "EXECUTION ECONOMICS NOT REPORTED".into(),
    };
    let gaps = app
        .backend
        .runtime
        .get("active_book_gap_windows")
        .and_then(Value::as_u64)
        .map_or_else(
            || "ACTIVE BOOK GAPS NOT REPORTED".into(),
            |value| format!("{value} ACTIVE BOOK-GAP WINDOWS"),
        );
    format!("{status} | {economics} | {gaps}")
}

fn execution_sides(app: &App) -> &'static str {
    if app.backend.source_follow_is_bidirectional() {
        "LONG + SHORT"
    } else {
        "SHORT ONLY"
    }
}

fn action(app: &App) -> String {
    app.backend
        .latest_decision_action
        .as_deref()
        .unwrap_or("hold")
        .replace('_', " ")
        .to_uppercase()
}

fn confidence(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{:.1}%", number * 100.0))
}

fn percent(value: Option<&Value>, scale: f64) -> String {
    value
        .and_then(Value::as_f64)
        .map_or_else(|| "N/A".into(), |number| format!("{:.1}%", number * scale))
}

fn smart_percent(value: Option<&Value>) -> String {
    value.and_then(Value::as_f64).map_or_else(
        || "N/A".into(),
        |number| {
            if number.fract().abs() < 1e-9 {
                format!("{number:.1}%")
            } else {
                format!("{number:.2}%")
            }
        },
    )
}

fn multiple(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_f64)
        .map_or_else(|| "N/A".into(), |number| format!("{number:.2}x"))
}

fn bps(value: Option<&Value>) -> String {
    value.and_then(Value::as_f64).map_or_else(
        || "N/A".into(),
        |number| format!("{:.2} bps", number * 10_000.0),
    )
}

fn optional_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |number| format!("{number:.1} bps"))
}

fn number_value(value: Option<&Value>) -> String {
    value
        .and_then(Value::as_f64)
        .map_or_else(|| "N/A".into(), |number| format!("{number:.1}"))
}

fn hours(value: Option<&Value>) -> String {
    value.and_then(Value::as_f64).map_or_else(
        || "N/A".into(),
        |seconds| format!("{:.1}h", seconds / 3_600.0),
    )
}
