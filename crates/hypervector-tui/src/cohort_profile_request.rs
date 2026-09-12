//! Identity-bound acknowledgement display for local restart-profile requests.

use std::borrow::Cow;

use crate::{app::App, backend_telemetry::BackendTelemetrySnapshot};

#[derive(Debug, Clone)]
pub(crate) struct ProfileRequest {
    request_id: String,
    run_id: String,
    profile_fingerprint: String,
}

impl ProfileRequest {
    pub(crate) fn from_backend(
        backend: &BackendTelemetrySnapshot,
        request_id: String,
    ) -> Option<Self> {
        Some(Self {
            request_id,
            run_id: backend.run_id.clone()?,
            profile_fingerprint: backend.profile_fingerprint.clone()?,
        })
    }
}

/// Display only the acknowledgement belonging to this run, profile and request.
pub(crate) fn notice<'a>(app: &'a App, default: &'a str) -> Cow<'a, str> {
    let local = app.cohort_notice.as_deref().unwrap_or(default);
    let Some(request) = app.cohort_profile_request.as_ref() else {
        return Cow::Borrowed(local);
    };
    if app.backend.run_id.as_deref() != Some(&request.run_id)
        || app.backend.profile_fingerprint.as_deref() != Some(&request.profile_fingerprint)
    {
        return Cow::Owned(format!(
            "PROFILE REQUEST {} // BACKEND IDENTITY CHANGED // RESULT UNAVAILABLE",
            request.request_id,
        ));
    }
    let event = app
        .backend
        .cohort
        .operator_events
        .iter()
        .rev()
        .find(|event| {
            event.request_id == request.request_id
                && event.action.as_deref() == Some("stage_profile")
        });
    let Some(event) = event else {
        return Cow::Borrowed(local);
    };
    Cow::Owned(format!(
        "PROFILE REQUEST {} // BACKEND {} // {}",
        event.request_id,
        event.status.to_uppercase(),
        event.reason.as_deref().unwrap_or("REASON UNREPORTED"),
    ))
}
