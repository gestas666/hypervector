//! Position, risk, exit, and strategy-specific configuration rows.

use serde_json::Value;

use super::config_view_format::{
    ConfigMenuRow, json_row, money_row, number_row, precise_number_row,
};
use crate::backend_telemetry::BackendTelemetrySnapshot;
use crate::config_hulk_smash::hulk_smash_strategy_rows;

pub(super) fn strategy_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    if backend.is_apex_mm() {
        return apex_mm_strategy_rows(backend);
    }
    if backend.is_hulk_smash() {
        return hulk_smash_strategy_rows(backend);
    }
    let mut rows = standard_position_rows(backend);
    rows.extend(standard_exposure_rows(backend));
    rows.extend(standard_risk_cap_rows(backend));
    rows.extend(standard_exit_rows(backend));
    rows
}

fn standard_position_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Position",
            "Position mode",
            &backend.position_policy,
            "position_mode",
            "position_policy",
        ),
        json_row(
            "Position",
            "Max per symbol",
            &backend.position_policy,
            "max_positions_per_symbol",
            "position_policy",
        ),
    ]
}

fn standard_exposure_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Risk",
            "Leverage",
            &backend.strategy_params,
            "leverage",
            "strategy_params",
            "x",
            1.0,
        ),
        number_row(
            "Risk",
            "Margin allocation",
            &backend.risk,
            "margin_fraction",
            "risk",
            "%",
            100.0,
        ),
        precise_number_row(
            "Risk",
            "Gross notional / equity",
            &backend.risk,
            "notional_fraction",
            "risk",
            "x",
            1.0,
        ),
    ]
}

fn standard_risk_cap_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        money_row(
            "Risk",
            "Max notional",
            &backend.risk,
            "max_notional_usd",
            "risk",
        ),
        protective_stop_row(backend),
    ]
}

fn standard_exit_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        number_row(
            "Exit",
            "Take-profit target",
            &backend.exits,
            "target_margin_pct",
            "exits",
            "%",
            1.0,
        ),
        number_row(
            "Exit",
            "Target price move",
            &backend.exits,
            "target_price_fraction",
            "exits",
            " bps",
            10_000.0,
        ),
        json_row(
            "Exit",
            "Target basis",
            &backend.exits,
            "target_basis",
            "exits",
        ),
        json_row(
            "Exit",
            "Range policy",
            &backend.exits,
            "range_policy",
            "exits",
        ),
        number_row(
            "Exit",
            "Maximum hold",
            &backend.exits,
            "maximum_hold_seconds",
            "exits",
            "h",
            1.0 / 3_600.0,
        ),
    ]
}

fn apex_mm_strategy_rows(backend: &BackendTelemetrySnapshot) -> Vec<ConfigMenuRow> {
    vec![
        json_row(
            "Position",
            "Position mode",
            &backend.position_policy,
            "position_mode",
            "position_policy",
        ),
        json_row(
            "Position",
            "Max per symbol",
            &backend.position_policy,
            "max_positions_per_symbol",
            "position_policy",
        ),
        number_row(
            "Risk",
            "Leverage",
            &backend.strategy_params,
            "leverage",
            "strategy_params",
            "x",
            1.0,
        ),
        money_row(
            "Risk",
            "Base quote",
            &backend.strategy_params,
            "base_order_notional_usd",
            "strategy_params",
        ),
        money_row(
            "Risk",
            "Max inventory",
            &backend.risk,
            "max_inventory_notional_usd",
            "risk",
        ),
        money_row(
            "Risk",
            "Reserved margin cap",
            &backend.risk,
            "maximum_reserved_margin_usd",
            "risk",
        ),
    ]
}

fn protective_stop_row(backend: &BackendTelemetrySnapshot) -> ConfigMenuRow {
    if backend
        .exits
        .get("stop_bps")
        .and_then(Value::as_f64)
        .is_some()
    {
        number_row(
            "Exit",
            "Protective stop",
            &backend.exits,
            "stop_bps",
            "exits",
            " bps",
            1.0,
        )
    } else {
        json_row(
            "Exit",
            "Protective stop",
            &backend.exits,
            "fixed_stop",
            "exits",
        )
    }
}
