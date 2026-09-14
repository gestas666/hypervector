//! Display current venue coverage independently of a persisted stop identity.

use crate::backend_cohort::CohortAssetSnapshot;

pub(crate) fn protection_override(asset: &CohortAssetSnapshot) -> Option<&'static str> {
    match (
        asset.stop_protection.as_deref(),
        asset.protective_exit_pending,
    ) {
        (Some("flat"), _) => Some("FLAT"),
        (Some("missing"), Some(true)) => Some("EXIT DUE / NO STOP"),
        (Some("missing"), _) => Some("STOP MISSING"),
        (Some("covering"), Some(true)) => Some("EXIT DUE / STOP"),
        (_, Some(true)) => Some("EXIT DUE / UNKNOWN"),
        _ => None,
    }
}

pub(crate) fn detail_title(asset: &CohortAssetSnapshot) -> String {
    if asset.partial_exit_fill_count.is_none() {
        return format!(" SELECTED {} // PRICES ABOVE ~ ROUNDED ", asset.symbol);
    }
    let opened = asset
        .opened_at_ms
        .and_then(chrono::DateTime::from_timestamp_millis)
        .map_or_else(
            || "N/A".into(),
            |value| value.format("%m-%d %H:%M:%SZ").to_string(),
        );
    let partial = match (asset.partial_exit_fill_count, asset.partial_exit_size) {
        (Some(count), Some(size)) => format!("{count}/{size:.5}"),
        _ => "N/A".into(),
    };
    format!(
        " SELECTED {} // OPENED {opened}  PARTIAL {partial} ",
        asset.symbol
    )
}
