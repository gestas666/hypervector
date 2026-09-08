//! Compact import status visible independently of the selected operator pane.

use ratatui::text::{Line, Span};

use crate::app::App;
use crate::backend_cohort_research_sync::{CohortResearchSync, ResearchSyncState};
use crate::cohort_format::eastern_time;

pub(crate) fn status_line(app: &App) -> Line<'static> {
    let Some(status) = &app.backend.cohort_checkpoint.research_sync else {
        return Line::from(Span::styled(" IMPORT UNREPORTED", app.theme.muted));
    };
    let stale = app.backend.cohort_checkpoint.publication_stale;
    let label = state_label(status);
    let prefix = if stale {
        "IMPORT STALE // WAS"
    } else {
        "IMPORT"
    };
    let style = if status.error.is_some() {
        app.theme.bear
    } else if stale {
        app.theme.gold
    } else {
        app.theme.cyan
    };
    let mut spans = vec![Span::styled(format!(" {prefix} {label}"), style)];
    if status.state == ResearchSyncState::Disabled {
        return Line::from(spans);
    }
    let last = status
        .last_success_at_utc
        .as_deref()
        .map(eastern_time)
        .unwrap_or_else(|| "N/A".into());
    let age = status
        .last_success_age_seconds
        .filter(|_| !stale)
        .map(|age| format!(" ({age:.0}s)"))
        .unwrap_or_default();
    spans.push(Span::raw(format!(" // LAST OK {last}{age}")));
    if let Some(error) = &status.error {
        let error = error
            .strip_prefix("research sync deferred: ")
            .unwrap_or(error);
        let safe: String = error
            .chars()
            .map(|c| if c.is_control() { ' ' } else { c })
            .collect();
        spans.push(Span::styled(format!(" // {safe}"), style));
    } else if let Some(count) = status.last_imported_events {
        spans.push(Span::raw(format!(" // {count} events")));
    }
    Line::from(spans)
}

fn state_label(status: &CohortResearchSync) -> &'static str {
    match status.state {
        ResearchSyncState::Disabled => "DISABLED",
        ResearchSyncState::Waiting => "WAITING",
        ResearchSyncState::Running if status.error.is_some() => "RETRYING",
        ResearchSyncState::Running => "RUNNING",
        ResearchSyncState::Ready => "OK",
        ResearchSyncState::Deferred => "DEFERRED",
        ResearchSyncState::Failed => "FAILED",
    }
}
