//! Order execution and cost configuration rows.

use super::config_view_format::{ConfigMenuRow, json_row, money_row, number_row};
use crate::backend_telemetry::BackendTelemetrySnapshot;

pub(super) fn execution_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    if backend.is_apex_mm() {
        return apex_mm_execution_rows(backend);
    }
    let mut rows = standard_order_rows(backend);
    rows.extend(standard_reentry_rows(backend));
    rows
}

fn standard_order_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Orders",
            "Order type",
            &backend.execution_policy,
            "order_type",
            "execution",
        ),
        json_row(
            "Orders",
            "Time in force",
            &backend.execution_policy,
            "time_in_force",
            "execution",
        ),
        number_row(
            "Orders",
            "Entry TTL",
            &backend.execution_policy,
            "entry_ttl_seconds",
            "execution",
            "s",
            1.0,
        ),
    ]
}

fn standard_reentry_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Orders",
            "Expired entry re-arm",
            &backend.execution_policy,
            "expired_entry_rearm_policy",
            "execution",
        ),
        json_row(
            "Orders",
            "Same-side re-entry",
            &backend.execution_policy,
            "same_direction_reentry_policy",
            "execution",
        ),
        number_row(
            "Orders",
            "Re-entry cooldown",
            &backend.execution_policy,
            "reentry_cooldown_bars",
            "execution",
            " bars",
            1.0,
        ),
        json_row(
            "Orders",
            "Maximum-hold exit",
            &backend.execution_policy,
            "maximum_hold_exit",
            "execution",
        ),
    ]
}

fn apex_mm_execution_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    let mut rows = apex_mm_order_rows(backend);
    rows.extend(apex_mm_telemetry_rows(backend));
    rows
}

fn apex_mm_order_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Orders",
            "Order type",
            &backend.execution_policy,
            "order_type",
            "execution",
        ),
        json_row(
            "Orders",
            "Submission transport",
            &backend.execution_policy,
            "submission_transport",
            "execution",
        ),
        money_row(
            "Orders",
            "Venue min order",
            &backend.execution_policy,
            "minimum_order_notional_usd",
            "execution",
        ),
        number_row(
            "Orders",
            "Quote refresh",
            &backend.execution_policy,
            "quote_refresh_ms",
            "execution",
            "ms",
            1.0,
        ),
    ]
}

fn apex_mm_telemetry_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Orders",
            "Book freshness",
            &backend.execution_policy,
            "maximum_book_age_ms",
            "execution",
            "ms",
            1.0,
        ),
        number_row(
            "Telemetry",
            "Markout horizon",
            &backend.execution_policy,
            "markout_horizon_ms",
            "execution",
            "ms",
            1.0,
        ),
        number_row(
            "Order book",
            "L2 depth",
            &backend.execution_policy,
            "depth_levels",
            "execution",
            " levels",
            1.0,
        ),
        json_row(
            "Lifecycle",
            "Stop behavior",
            &backend.execution_policy,
            "stop_behavior",
            "execution",
        ),
    ]
}

pub(super) fn cost_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Costs",
            "Maker fee",
            &backend.costs,
            "maker_fee_rate",
            "costs",
            "bps",
            10_000.0,
        ),
        number_row(
            "Costs",
            "Taker fee",
            &backend.costs,
            "taker_fee_rate",
            "costs",
            "bps",
            10_000.0,
        ),
        json_row(
            "Costs",
            "Funding source",
            &backend.costs,
            "funding_source",
            "costs",
        ),
    ]
}
