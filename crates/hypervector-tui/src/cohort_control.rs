//! Confirmed operator overrides routed through the backend command inbox.

use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    text::{Line, Span},
    widgets::{Cell, Clear, Paragraph, Row, Table, Wrap},
};

use crate::app::App;
use crate::backend_telemetry::BackendConnectionState;
use crate::cohort_application::cohort_backend_accepts_operator_requests;
use crate::cohort_operator::{CohortOperatorAction, CohortOperatorDraft};
use crate::cohort_widgets::{panel, provider_alias};

pub(crate) fn render(frame: &mut Frame, app: &App, area: Rect) {
    let sections = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4),
            Constraint::Length(13),
            Constraint::Length(4),
            Constraint::Min(8),
        ])
        .split(area);
    render_authority(frame, app, sections[0]);
    render_actions(frame, app, sections[1]);
    render_notice(frame, app, sections[2]);
    render_history(frame, app, sections[3]);
}

fn render_authority(frame: &mut Frame, app: &App, area: Rect) {
    let backend_armed = backend_is_armed(app);
    let channel_enabled = backend_armed && app.cohort_command_inbox.is_some();
    let status = if channel_enabled {
        "LIVE BACKEND ARMED // REQUEST CHANNEL ENABLED"
    } else if backend_armed {
        "LIVE BACKEND ARMED // REQUEST CHANNEL UNAVAILABLE"
    } else if app.backend.connection == BackendConnectionState::Stale {
        "BACKEND STALE // MANUAL REQUESTS DISABLED"
    } else if app.backend.connection != BackendConnectionState::Connected {
        "BACKEND NOT CONNECTED // MANUAL REQUESTS DISABLED"
    } else {
        "DISARMED // MANUAL REQUESTS DISABLED"
    };
    let style = if backend_armed {
        app.theme.bear
    } else {
        app.theme.gold
    };
    frame.render_widget(
        Paragraph::new(vec![
            Line::from(vec![
                Span::styled(status, style),
                Span::raw("  //  RUST HAS NO SDK, SIGNER, OR VENUE CLIENT"),
            ]),
            drain_authority_line(app),
        ])
        .block(panel(" OPERATOR AUTHORITY BOUNDARY ", app)),
        area,
    );
}

fn render_actions(frame: &mut Frame, app: &App, area: Rect) {
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(8), Constraint::Length(5)])
        .split(area);
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
        .split(rows[0]);
    render_entry(frame, app, columns[0]);
    render_close(frame, app, columns[1]);
    render_transition_drain(frame, app, rows[1]);
}

fn render_transition_drain(frame: &mut Frame, app: &App, area: Rect) {
    let selected = app.cohort_control_focus == 2;
    let title = if selected {
        " ▸ TRANSITION DRAIN "
    } else {
        " TRANSITION DRAIN "
    };
    frame.render_widget(
        Paragraph::new(transition_drain_card_lines(app, selected)).block(panel(title, app)),
        area,
    );
}

fn render_entry(frame: &mut Frame, app: &App, area: Rect) {
    let selected = app.cohort_control_focus == 0;
    let provider = app
        .selected_cohort_provider()
        .map_or("N/A", |value| provider_alias(&value.strategy_id));
    let symbol = app.selected_cohort_symbol().unwrap_or("N/A");
    let lines = vec![
        Line::from(vec![
            Span::raw("COIN "),
            Span::styled(symbol, app.theme.title),
        ]),
        Line::from(format!("PROVIDER {provider}")),
        Line::from(format!(
            "SIDE {}",
            app.selected_cohort_operator_side()
                .unwrap_or("N/A")
                .to_uppercase()
        )),
        Line::from("BYPASS: strategy prerequisites only"),
        Line::from("RETAIN: capacity, isolated risk, stop, venue checks"),
        Line::from(if selected {
            "SELECTED // [Enter] REVIEW"
        } else {
            "[↑] SELECT"
        }),
    ];
    let title = if selected {
        " ▸ MANUAL STRATEGY ENTRY "
    } else {
        " MANUAL STRATEGY ENTRY "
    };
    frame.render_widget(Paragraph::new(lines).block(panel(title, app)), area);
}

fn render_close(frame: &mut Frame, app: &App, area: Rect) {
    let selected = app.cohort_control_focus == 1;
    let symbol = app.selected_cohort_symbol().unwrap_or("N/A");
    let asset = app
        .backend
        .cohort
        .assets
        .iter()
        .find(|value| value.symbol == symbol);
    let position = asset.map_or_else(
        || "UNOBSERVED".into(),
        |value| {
            value
                .position_side
                .as_deref()
                .unwrap_or("FLAT")
                .to_uppercase()
        },
    );
    let lines = vec![
        Line::from(vec![
            Span::raw("COIN "),
            Span::styled(symbol, app.theme.title),
        ]),
        Line::from(format!("POSITION {position}")),
        Line::from("METHOD backend engine exit"),
        Line::from("ORDER reduce-only IOC after owned-stop cancel"),
        Line::from("VERIFY venue flat; no same-cycle auto re-entry"),
        Line::from(if selected {
            "SELECTED // [Enter] REVIEW"
        } else {
            "[↓] SELECT"
        }),
    ];
    let title = if selected {
        " ▸ MANUAL POSITION CLOSE "
    } else {
        " MANUAL POSITION CLOSE "
    };
    frame.render_widget(Paragraph::new(lines).block(panel(title, app)), area);
}

fn render_notice(frame: &mut Frame, app: &App, area: Rect) {
    let message = app.cohort_notice.as_deref().unwrap_or(
        "Choose an action, then review. Enter opens confirmation; no request is sent without [y].",
    );
    frame.render_widget(
        Paragraph::new(message)
            .style(app.theme.gold)
            .block(panel(" COMMAND STATUS ", app)),
        area,
    );
}

fn render_history(frame: &mut Frame, app: &App, area: Rect) {
    if app.backend.cohort.operator_events.is_empty() {
        let message = if backend_is_armed(app) {
            "NO MANUAL COMMANDS RECORDED // AUTO ROUTING CONTINUES"
        } else {
            "NO MANUAL COMMANDS RECORDED // BACKEND NOT LIVE"
        };
        frame.render_widget(
            Paragraph::new(message)
                .block(panel(" AUDITED COMMAND LIFECYCLE // BACKEND LEDGER ", app)),
            area,
        );
        return;
    }
    let rows = app
        .backend
        .cohort
        .operator_events
        .iter()
        .rev()
        .map(|event| {
            Row::new(vec![
                Cell::from(event.request_id.chars().take(8).collect::<String>()),
                Cell::from(event.status.to_uppercase()),
                Cell::from(event.action.as_deref().unwrap_or("N/A")),
                Cell::from(event.symbol.as_deref().unwrap_or("N/A")),
                Cell::from(event.side.as_deref().unwrap_or("N/A")),
                Cell::from(event.reason.as_deref().unwrap_or("N/A")),
            ])
        });
    let table = Table::new(
        rows,
        [
            Constraint::Length(10),
            Constraint::Length(11),
            Constraint::Length(18),
            Constraint::Length(6),
            Constraint::Length(7),
            Constraint::Min(30),
        ],
    )
    .header(
        Row::new([
            "REQUEST",
            "STATUS",
            "ACTION",
            "COIN",
            "SIDE",
            "BACKEND REASON",
        ])
        .style(app.theme.header),
    )
    .block(panel(" AUDITED COMMAND LIFECYCLE // BACKEND LEDGER ", app));
    frame.render_widget(table, area);
}

pub(crate) fn render_confirmation(frame: &mut Frame, app: &App, area: Rect) {
    let Some(draft) = app.cohort_confirmation.as_ref() else {
        return;
    };
    let modal = centered_rect(72, 55, area);
    frame.render_widget(Clear, modal);
    let lines = confirmation_lines(app, draft);
    frame.render_widget(
        Paragraph::new(lines)
            .wrap(Wrap { trim: true })
            .block(panel(" CONFIRM LIVE OPERATOR REQUEST ", app)),
        modal,
    );
}

fn confirmation_lines<'a>(app: &'a App, draft: &'a CohortOperatorDraft) -> Vec<Line<'a>> {
    if draft.action == CohortOperatorAction::TransitionDrain {
        return vec![
            Line::from(Span::styled("LIVE CONTROL-PLANE ACTION", app.theme.bear)),
            Line::from("ACTION TRANSITION DRAIN"),
            Line::from("SCOPE MULTI // NO DIRECT VENUE ORDER"),
            Line::from("The Python backend revalidates run identity and persists the drain."),
            Line::from("NEW ENTRY ADMISSION IS WITHHELD AFTER BACKEND ACCEPTANCE."),
            Line::from("EXITS AND VENUE PROTECTION CONTINUE."),
            Line::from("NO PROFILE IS ACTIVATED OR STARTED AUTOMATICALLY."),
            Line::from(""),
            Line::from(Span::styled("[y] CONFIRM AND SUBMIT", app.theme.bear)),
            Line::from(Span::styled("[n/Esc] CANCEL — NO REQUEST", app.theme.bull)),
        ];
    }
    let (action, detail) = match &draft.action {
        CohortOperatorAction::ManualEnter { provider, side } => (
            "MANUAL ENTRY",
            format!("{} via {}", side.to_uppercase(), provider_alias(provider)),
        ),
        CohortOperatorAction::ManualClose => (
            "MANUAL REDUCE-ONLY CLOSE",
            "backend exits the current position and verifies flat".into(),
        ),
        CohortOperatorAction::TransitionDrain => unreachable!("handled above"),
    };
    vec![
        Line::from(Span::styled("LIVE CAPITAL ACTION", app.theme.bear)),
        Line::from(format!("ACTION {action}")),
        Line::from(format!("COIN {}  //  {detail}", draft.symbol)),
        Line::from(
            "The Python backend will revalidate run identity, age, capacity, position state, and venue constraints.",
        ),
        Line::from(
            "Entry keeps configured isolated sizing and protective stop. Close remains reduce-only.",
        ),
        Line::from(""),
        Line::from(Span::styled("[y] CONFIRM AND SUBMIT", app.theme.bear)),
        Line::from(Span::styled("[n/Esc] CANCEL — NO REQUEST", app.theme.bull)),
    ]
}

fn drain_authority_line(app: &App) -> Line<'static> {
    Line::from(Span::styled(
        transition_drain_authority(app),
        app.theme.cyan,
    ))
}

fn transition_drain_authority(app: &App) -> &'static str {
    if app.backend.connection != BackendConnectionState::Connected {
        return "LAST DRAIN CHECKPOINT ONLY // BACKEND NOT LIVE";
    }
    match app
        .backend
        .cohort
        .transition_drain
        .as_ref()
        .map(|state| state.status.as_str())
    {
        None => "DRAIN UNKNOWN // BACKEND STATUS UNAVAILABLE",
        Some("inactive") => "DRAIN INACTIVE // READY",
        Some("active") => "DRAIN ACTIVE // ENTRY ADMISSION OFF",
        Some("completed") => "DRAIN COMPLETE // BACKEND STOPPING OR STOPPED",
        Some(_) => "DRAIN STATE INVALID // BACKEND TELEMETRY REJECTED",
    }
}

fn transition_drain_card_lines(app: &App, selected: bool) -> Vec<Line<'static>> {
    let selection = if selected {
        " // SELECTED [Enter] REVIEW"
    } else {
        " // [↓] SELECT"
    };
    let state = app.backend.cohort.transition_drain.as_ref();
    if app.backend.connection != BackendConnectionState::Connected {
        let status = state.map_or("UNAVAILABLE", |value| match value.status.as_str() {
            "inactive" => "INACTIVE",
            "active" => "ACTIVE",
            "completed" => "COMPLETED",
            _ => "INVALID",
        });
        return vec![
            Line::from(format!("LAST STATE {status} // BACKEND NOT LIVE")),
            Line::from("AUTOMATIC ROUTING NOT CLAIMED"),
            Line::from(format!("MANUAL REQUESTS DISABLED{selection}")),
        ];
    }
    let lines: (String, String, String) = match state.map(|value| value.status.as_str()) {
        None => (
            "STATE UNAVAILABLE // DO NOT INFER INACTIVE".into(),
            "NO BACKEND DRAIN STATUS WAS REPORTED".into(),
            format!("NO DRAIN REQUEST STATUS CLAIMED{selection}"),
        ),
        Some("inactive") => (
            "STATE INACTIVE // READY // DEFAULT-OFF".into(),
            "AUTOMATIC ENTRY + EXIT ROUTING ACTIVE".into(),
            format!("SELECT TO WITHHOLD NEW ENTRIES{selection}"),
        ),
        Some("active") => (
            format!(
                "STATE ACTIVE // NEW ENTRIES WITHHELD{}",
                recovery_indicator(state.expect("active state exists"))
            ),
            "EXITS + VENUE PROTECTION CONTINUE".into(),
            format!("NO PROFILE START // NO AUTO RESTART{selection}"),
        ),
        Some("completed") => (
            "STATE COMPLETED // FLAT + UNOWNED VERIFIED".into(),
            "BACKEND STOPPING OR STOPPED".into(),
            "ARCHIVE DRAIN EVIDENCE BEFORE NEXT START".into(),
        ),
        Some(_) => (
            "STATE INVALID // BACKEND TELEMETRY REJECTED".into(),
            "NO OPERATIONAL STATE INFERRED".into(),
            "INSPECT BACKEND LEDGER".into(),
        ),
    };
    vec![
        Line::from(lines.0),
        Line::from(lines.1),
        Line::from(lines.2),
    ]
}

fn recovery_indicator(state: &crate::backend_cohort::CohortTransitionDrainTelemetry) -> String {
    if state.resume_count == 0 {
        return String::new();
    }
    let origin = state
        .origin_run_id
        .as_deref()
        .unwrap_or("UNKNOWN")
        .chars()
        .take(20)
        .collect::<String>();
    format!(" // RECOVERY #{} // ORIGIN {origin}", state.resume_count)
}

fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let rows = Layout::vertical([
        Constraint::Percentage((100 - percent_y) / 2),
        Constraint::Percentage(percent_y),
        Constraint::Percentage((100 - percent_y) / 2),
    ])
    .split(area);
    Layout::horizontal([
        Constraint::Percentage((100 - percent_x) / 2),
        Constraint::Percentage(percent_x),
        Constraint::Percentage((100 - percent_x) / 2),
    ])
    .split(rows[1])[1]
}

fn backend_is_armed(app: &App) -> bool {
    cohort_backend_accepts_operator_requests(app)
}
