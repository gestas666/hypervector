//! Backend strategy command bar and status telemetry.

use ratatui::{
    Frame,
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Paragraph},
};

use super::effective_backend_leverage;
use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::model::RegimeState;

// ============================================================================
// ROW 1: Backend strategy decision and status
// ============================================================================
pub fn render_command_bar(f: &mut Frame, app: &App, area: Rect) {
    let block = command_bar_block(app);
    f.render_widget(Paragraph::new(command_bar_lines(app)).block(block), area);
}

fn command_bar_lines(app: &App) -> Vec<Line<'static>> {
    let leverage = effective_backend_leverage(app)
        .map(|value| format!("{value:.0}x"))
        .unwrap_or_else(|| "n/a".to_string());
    vec![
        Line::from(vec![
            Span::styled(
                format!("█ {} {leverage} █", strategy_title(app)),
                app.theme.gold,
            ),
            Span::raw("  "),
            Span::styled(strategy_state_label(app), strategy_state_style(app)),
        ]),
        Line::from(vec![Span::styled(
            strategy_context_line(app),
            strategy_context_style(app),
        )]),
        Line::from(vec![entry_decision_span(app)]),
        Line::from(vec![backend_status_span(app)]),
    ]
}

fn entry_decision_span(app: &App) -> Span<'static> {
    if app.backend.is_apex_mm() {
        Span::styled(
            format!(
                "BACKEND QUOTE POLICY: {} ({})",
                if app.backend.apex_mm.quote_active == Some(true) {
                    "ACTIVE"
                } else {
                    "WITHHELD"
                },
                app.backend
                    .apex_mm
                    .quote_reason
                    .as_deref()
                    .unwrap_or("not reported")
            ),
            app.theme.cyan,
        )
    } else if app.backend.is_pine_stack() {
        Span::styled(
            format!(
                "BACKEND OBSERVER ACTION: {}",
                backend_action(app, "NO COMPLETED DECISION")
            ),
            app.theme.cyan,
        )
    } else if app.backend.entry_allowed == Some(true) {
        let direction = app.backend.entry_direction.as_deref().unwrap_or("unknown");
        Span::styled(
            format!("BACKEND ENTRY ELIGIBLE: {}", direction.to_uppercase()),
            app.theme.bull,
        )
    } else {
        Span::styled(
            format!(
                "BACKEND DECISION: {}",
                backend_action(app, "NO ENTRY SIGNAL")
            ),
            app.theme.muted,
        )
    }
}

fn command_bar_block(app: &App) -> Block<'static> {
    Block::default()
        .title(" BACKEND STRATEGY TELEMETRY ")
        .title_style(app.theme.title)
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(
            if app.backend.connection == BackendConnectionState::Connected {
                app.theme.bull
            } else {
                app.theme.border_active
            },
        )
}

fn backend_action(app: &App, fallback: &str) -> String {
    app.backend
        .latest_decision_action
        .as_deref()
        .unwrap_or(fallback)
        .replace('_', " ")
        .to_uppercase()
}

fn strategy_state_label(app: &App) -> &'static str {
    if app.backend.is_apex_mm() {
        "TWO-SIDED MM"
    } else if app.backend.is_pine_stack() {
        "OBSERVER ONLY"
    } else {
        app.current_snapshot().state.display_name()
    }
}

fn strategy_state_style(app: &App) -> Style {
    match app.current_snapshot().state {
        RegimeState::BullMomentum => app.theme.bull,
        RegimeState::BearMomentum => app.theme.bear,
        RegimeState::VolatilityCoiling => app.theme.coiling,
        RegimeState::FundingCarry => app.theme.carry,
        RegimeState::RangeChop | RegimeState::Unknown => app.theme.chop,
    }
}

fn strategy_context_style(app: &App) -> Style {
    match app.current_snapshot().trend_5m.as_str() {
        "TREND_UP" | "BULL" => app.theme.bull,
        "TREND_DOWN" | "BEAR" => app.theme.bear,
        _ => app.theme.chop,
    }
}

fn strategy_title(app: &App) -> String {
    match app.backend.strategy_name.as_deref() {
        Some("apex_regime_mm_v2") => "BTC MARKET MAKER".into(),
        Some(name) if name.starts_with("sol_1h_sma10x30") => "SOL RANGE-ONSET".into(),
        Some(name) => name.replace('_', " ").to_uppercase(),
        None => "BACKEND STRATEGY".into(),
    }
}

fn strategy_context_line(app: &App) -> String {
    let snap = app.current_snapshot();
    if app.backend.is_apex_mm() {
        return "TWO-SIDED POST-ONLY BTC QUOTES | NO DIRECTION FORECAST | REGIME NOT USED".into();
    }
    if app.backend.is_source_follow() {
        return source_follow_context(app);
    }
    if app.backend.is_pine_stack() {
        return "ETH 30m FOUR-PINE OBSERVER | ZERO CAPITAL | REGIME NOT CLASSIFIED | PSEUDO-HOLDOUT FAILED".into();
    }
    if app.backend.is_hulk_smash() {
        return hulk_context(app);
    }
    if is_sol_range_onset(app) {
        return sol_range_context(app);
    }
    format!(
        "5m PRIMARY [{}] | 15m CONTEXT [{}]",
        snap.trend_5m, snap.trend_15m
    )
}

fn source_follow_context(app: &App) -> String {
    let execution = if app.backend.source_follow_is_bidirectional() {
        "LONG + SHORT EXEC"
    } else {
        "SHORT EXEC"
    };
    format!(
        "5m SOURCE [{}] | {execution} | {} | ACTION {} | 1m/15m NOT CLASSIFIED",
        app.current_snapshot().trend_5m,
        source_long_observer_label(app),
        backend_action(app, "hold"),
    )
}

fn hulk_context(app: &App) -> String {
    let hulk = &app.backend.hulk_smash;
    let score = hulk
        .score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let minimum = hulk
        .minimum_score
        .map_or_else(|| "N/A".into(), |value| value.to_string());
    let trigger = hulk
        .trigger
        .as_deref()
        .unwrap_or("not reported")
        .replace('_', " ")
        .to_uppercase();
    format!("30m SCORE {score}/{minimum} | SHORT ONLY | TRIGGER {trigger} | REGIME NOT CLASSIFIED")
}

fn is_sol_range_onset(app: &App) -> bool {
    app.backend
        .strategy_name
        .as_deref()
        .is_some_and(|name| name.starts_with("sol_1h_sma10x30"))
}

fn sol_range_context(app: &App) -> String {
    let snap = app.current_snapshot();
    let direction = app
        .backend
        .structural_direction
        .as_deref()
        .unwrap_or("neutral")
        .to_uppercase();
    let admission = if app.backend.regime_admitted == Some(true) {
        "ALLOWED"
    } else {
        "BLOCKED"
    };
    format!(
        "1h SMA10/30 [{direction}] | 5m [{} {admission}] | 15m CONTEXT [{}]",
        snap.trend_5m, snap.trend_15m
    )
}

fn source_long_observer_label(app: &App) -> String {
    if let Some(observer) = app.backend.source_long_observer.as_ref() {
        let recipe = observer
            .get("recipe_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("UNKNOWN");
        let identity = app
            .backend
            .source_long_observer_signal_time
            .as_ref()
            .map(|signal| format!("{signal}|{recipe}"));
        let matches_projection = app
            .backend
            .source_long_forward
            .as_ref()
            .is_some_and(|outcome| Some(&outcome.observation_id) == identity.as_ref());
        if !matches_projection {
            return format!("LONG OBS {} SIGNAL", recipe.to_uppercase());
        }
    }
    if let Some(outcome) = app.backend.source_long_forward.as_ref() {
        let status = match outcome.status.as_str() {
            "awaiting_evidence" => "WAIT",
            "entry_pending" => "ENTRY PENDING",
            "open" => "OPEN",
            "no_fill" => "NO FILL",
            "target_completed" => "TP",
            "time_exited" => "TIME EXIT",
            "liquidated" => "LIQUIDATED",
            _ => "UNKNOWN",
        };
        let quality = if outcome.evidence_complete {
            "VALID"
        } else {
            "GAP"
        };
        let delta = outcome.final_equity_usd - outcome.initial_equity_usd;
        return format!(
            "LONG OBS {} {status} Δ${delta:+.2} {quality}",
            outcome.recipe_id.to_uppercase()
        );
    }
    app.backend
        .source_long_observer
        .as_ref()
        .and_then(|observer| observer.get("recipe_id"))
        .and_then(serde_json::Value::as_str)
        .map(|recipe| format!("LONG OBS {}", recipe.to_uppercase()))
        .unwrap_or_else(|| "LONG OBS STANDBY".to_string())
}

fn backend_status_span(app: &App) -> Span<'static> {
    let state = match app.backend.connection {
        BackendConnectionState::Connected => "CONNECTED",
        BackendConnectionState::Stale => "STALE",
        BackendConnectionState::Disconnected => "DISCONNECTED",
        BackendConnectionState::Error => "ERROR",
    };
    let probability = app
        .backend
        .latest_metalabel_p
        .map(|value| format!("{value:.4}"))
        .unwrap_or_else(|| "n/a".to_string());
    Span::styled(
        format!(
            "BACKEND {state} | run={} | profile={} | strategy={} | model={} p={} source={}",
            app.backend.run_id.as_deref().unwrap_or("unknown"),
            app.backend.profile_id.as_deref().unwrap_or("unreported"),
            app.backend.strategy_name.as_deref().unwrap_or("unknown"),
            app.backend.metalabel_mode.as_deref().unwrap_or("off"),
            probability,
            app.backend
                .latest_conviction_source
                .as_deref()
                .unwrap_or("n/a"),
        ),
        app.theme.cyan,
    )
}
