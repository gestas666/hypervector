//! Shared formatting for open-lifecycle path evidence.

use crate::app::App;

pub(crate) fn compact_bps(value: Option<f64>, signed: bool) -> String {
    value.map_or_else(
        || "N/A".into(),
        |number| {
            if signed {
                format!("{number:+.1}")
            } else {
                format!("{number:.1}")
            }
        },
    )
}

pub(crate) fn path_style(app: &App, status: &str) -> ratatui::style::Style {
    if status == "observed" {
        app.theme.carry
    } else {
        app.theme.muted
    }
}

pub(crate) fn signed_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |bps| format!("{bps:+.1}bps"))
}

pub(crate) fn unsigned_bps(value: Option<f64>) -> String {
    value.map_or_else(|| "N/A".into(), |bps| format!("{bps:.1}bps"))
}
