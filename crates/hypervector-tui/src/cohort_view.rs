//! Modern nine-screen operator shell for the shared bidirectional cohort.

use ratatui::{
    Frame,
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Paragraph, Tabs},
};

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::cohort_format::{connection_label, connection_style, eastern_time};
use crate::cohort_widgets::{MIN_HEIGHT, MIN_WIDTH, panel};

/// Render backend-authored cohort telemetry without strategy or order authority.
pub fn render(frame: &mut Frame, app: &App) {
    if frame.area().width < MIN_WIDTH || frame.area().height < MIN_HEIGHT {
        render_resize_notice(frame, app);
        return;
    }
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4),
            Constraint::Min(12),
            Constraint::Length(3),
        ])
        .split(frame.area());
    render_header(frame, app, sections[0]);
    match app.active_tab {
        0 => crate::cohort_dashboard::render(frame, app, sections[1]),
        1 => crate::cohort_router::render(frame, app, sections[1]),
        2 => crate::cohort_chart::render(frame, app, sections[1]),
        3 => crate::cohort_depth::render(frame, app, sections[1]),
        4 => crate::cohort_trades::render(frame, app, sections[1]),
        5 => crate::cohort_research::render(frame, app, sections[1]),
        6 => crate::cohort_control::render(frame, app, sections[1]),
        7 => crate::cohort_regime::render(frame, app, sections[1]),
        _ => crate::cohort_config::render(frame, app, sections[1]),
    }
    render_footer(frame, app, sections[2]);
    if app.show_cohort_setup_modal {
        crate::cohort_setup_detail::render(frame, app, frame.area());
    }
    if app.show_cohort_chart_modal {
        crate::cohort_chart_detail::render(frame, app, frame.area());
    }
    if app.show_cohort_fill_modal {
        crate::cohort_trades::render_detail(frame, app, frame.area());
    }
    if app.show_cohort_journal_modal {
        crate::cohort_research::render_detail(frame, app, frame.area());
    }
    if app.cohort_confirmation.is_some() {
        crate::cohort_control::render_confirmation(frame, app, frame.area());
    }
}

fn render_header(frame: &mut Frame, app: &App, area: Rect) {
    let block = panel(" HYPERVECTOR // SHARED COHORT ", app);
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Length(1)])
        .split(inner);
    frame.render_widget(Paragraph::new(status_line(app)), rows[0]);
    render_navigation(frame, app, rows[1]);
}

fn status_line(app: &App) -> Line<'static> {
    let sync = app
        .backend
        .cohort
        .last_observed_at
        .as_deref()
        .map(eastern_time)
        .unwrap_or_else(|| "N/A".into());
    let pulse = ["·", "∙", "●", "∙"][(app.tick_count % 4) as usize];
    let stopped = clean_stopped_snapshot(app);
    let (authority, authority_style) = match (
        stopped,
        app.backend.connection,
        app.backend.live_armed == Some(true),
    ) {
        (true, _, _) => ("STOPPED SNAPSHOT", app.theme.cyan),
        (false, BackendConnectionState::Connected, true) => {
            ("LIVE EXECUTION ARMED", app.theme.bear)
        }
        (false, BackendConnectionState::Connected, false) => ("EXECUTION DISARMED", app.theme.gold),
        (false, _, true) => ("LAST CHECKPOINT ARMED", app.theme.gold),
        (false, _, false) => ("BACKEND NOT LIVE", app.theme.gold),
    };
    let mut spans = vec![
        Span::styled(format!(" {pulse} "), connection_style(app)),
        Span::styled(connection_label(app), connection_style(app)),
        Span::raw("  //  SYNC "),
        Span::styled(sync, app.theme.cyan),
        Span::raw("  //  "),
        Span::styled(authority, authority_style),
    ];
    if let Some(acceptance) = &app.backend.cohort_checkpoint.poststart_acceptance {
        spans.push(Span::raw("  //  "));
        let verdict = if stopped {
            "RUN STOPPED"
        } else if acceptance.accepted {
            "CHECK PASS"
        } else {
            "CHECK FAIL"
        };
        spans.push(Span::styled(
            format!("{} {verdict}", acceptance.version),
            if stopped || acceptance.accepted {
                app.theme.bull
            } else {
                app.theme.gate_blocked
            },
        ));
    }
    if app.detached_lifecycle {
        spans.push(Span::raw("  //  "));
        spans.push(Span::styled("BACKEND PERSISTS ON QUIT", app.theme.cyan));
    }
    Line::from(spans)
}

fn clean_stopped_snapshot(app: &App) -> bool {
    matches!(
        app.backend.cohort_checkpoint.lifecycle_state.as_deref(),
        Some("stale_running_heartbeat_after_asset_stop" | "stopped_consistent")
    ) && !app.backend.cohort_checkpoint.asset_states.is_empty()
        && app
            .backend
            .cohort_checkpoint
            .asset_states
            .values()
            .all(|state| state == "STOPPED")
}

fn render_navigation(frame: &mut Frame, app: &App, area: Rect) {
    const SPACED_NAVIGATION_WIDTH: u16 = 117;
    let compact = area.width < SPACED_NAVIGATION_WIDTH;
    let padding = if compact { "" } else { " " };
    let tabs = Tabs::new([
        "[1] PORT",
        "[2] SETUP",
        "[3] CHART",
        "[4] DEPTH",
        "[5] TRADE",
        "[6] LOG",
        "[7] OPS",
        "[8] REGIME",
        "[9] CFG",
    ])
    .select(app.active_tab)
    .divider(if compact { "│" } else { " │ " })
    .padding(padding, padding)
    .style(app.theme.muted)
    .highlight_style(app.theme.highlight);
    frame.render_widget(tabs, area);
}

fn render_footer(frame: &mut Frame, app: &App, area: Rect) {
    let text = Line::from(vec![
        Span::styled(" [1-9]", app.theme.gold),
        Span::raw(" Views  "),
        Span::styled("[Tab]", app.theme.gold),
        Span::raw(" Next  "),
        Span::styled("[q]", app.theme.gold),
        Span::raw(context_help(app)),
    ]);
    frame.render_widget(
        Paragraph::new(text).block(panel(" OPERATOR CONTROLS ", app)),
        area,
    );
}

fn context_help(app: &App) -> String {
    if app.detached_lifecycle && app.active_tab == 0 {
        return format!(
            " Quit leaves backend running  //  All {} configured assets visible",
            app.backend.cohort.enabled_symbols.len(),
        );
    }
    let help = match app.active_tab {
        0 => " Quit  //  All assets visible  //  Backend-authored telemetry",
        1 => " Quit  //  [↑/↓] Select setup  [Enter] Full backend evidence",
        2 => " Quit  //  [←/→] Select coin  [Enter] Strategy + timeframe detail",
        3 => " Quit  //  [←/→] Select coin  //  Backend-authored L2 only",
        4 => " Quit  //  [←/→] Focus journal  [↑/↓] Select  [Enter] Exact details",
        5 => " Quit  //  [↑/↓] Select evidence  [Enter] Signal vs setup paths",
        6 => " Quit  //  [←/→] Coin [p/P] Provider [d] Side [↑/↓] Action [Enter] Review",
        7 => " Quit  //  [←/→] Coin [PgUp/PgDn] All panes // Backend labels + causal evidence",
        8 => " Quit  //  [←/→] Coin [p/P] Provider [↑/↓] Row [+/-] Adjust [Enter] Action",
        _ => " Quit  //  Backend-authored telemetry  //  Lifecycle follows launcher",
    };
    help.to_string()
}

fn render_resize_notice(frame: &mut Frame, app: &App) {
    let message = vec![
        Line::from(Span::styled("TERMINAL TOO SMALL", app.theme.gate_blocked)),
        Line::from("MINIMUM 100x28  //  Recommended 120x36 or wider"),
        Line::from(format!(
            "CURRENT {}x{}  //  Resize to restore truthful operational telemetry",
            frame.area().width,
            frame.area().height,
        )),
    ];
    frame.render_widget(
        Paragraph::new(message)
            .alignment(Alignment::Center)
            .block(panel(" HYPERVECTOR // DISPLAY REQUIREMENT ", app)),
        frame.area(),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::backend_cohort_checkpoint::CohortPoststartAcceptance;

    #[test]
    fn stopped_label_requires_complete_terminal_asset_evidence() {
        let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        app.backend.cohort_checkpoint.lifecycle_state = Some("stopped_consistent".into());
        assert!(!clean_stopped_snapshot(&app));
        app.backend.cohort_checkpoint.asset_states = [
            ("BTC".into(), "STOPPED".into()),
            ("ETH".into(), "OPEN".into()),
        ]
        .into();
        assert!(!clean_stopped_snapshot(&app));
    }

    #[test]
    fn stopped_checkpoint_is_not_presented_as_armed_or_failed() {
        let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
        app.backend.connection = BackendConnectionState::Stale;
        app.backend.live_armed = Some(true);
        app.backend.cohort_checkpoint.asset_states = [
            ("BTC".into(), "STOPPED".into()),
            ("ETH".into(), "STOPPED".into()),
        ]
        .into();
        app.backend.cohort_checkpoint.poststart_acceptance = Some(CohortPoststartAcceptance {
            version: "V80".into(),
            accepted: false,
            reasons: vec!["runtime_not_fresh_and_healthy".into()],
            expected_routes: 9,
            evaluated_routes: 9,
            routes_with_metrics: 9,
            open_positions: 0,
            fills: 0,
            costed_fills: 0,
            closed_trades: 0,
        });

        for state in [
            "stale_running_heartbeat_after_asset_stop",
            "stopped_consistent",
        ] {
            app.backend.cohort_checkpoint.lifecycle_state = Some(state.into());
            let rendered = status_line(&app)
                .spans
                .iter()
                .map(|span| span.content.as_ref())
                .collect::<String>();

            assert!(rendered.contains("STOPPED SNAPSHOT"), "{state}: {rendered}");
            assert!(rendered.contains("V80 RUN STOPPED"));
            assert!(!rendered.contains("LAST CHECKPOINT ARMED"));
            assert!(!rendered.contains("CHECK FAIL"));
        }
    }
}
