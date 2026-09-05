//! Operator-readable timing, execution, and sizing for one configured route.

use chrono::DateTime;

use crate::backend_cohort::{
    CohortAssetConfig, CohortProvider, CohortProviderEvaluation, CohortProviderExecutionContract,
};
use crate::cohort_format::{eastern_time, fill_full_date_time};
use crate::cohort_router_format::human_token;

/// Format the configured entry, stop, target, timer, and exit-controller contract.
pub(crate) fn execution_label(
    evaluation: &CohortProviderEvaluation,
    providers: &[CohortProvider],
) -> String {
    let Some(execution) = provider(evaluation, providers).and_then(|row| row.execution.as_ref())
    else {
        return "PLAN UNAVAILABLE".into();
    };
    format!(
        "PLAN ENTRY {} · SL {} · TP {} · HOLD {} · RECIPE {} · LOCK {}",
        human_token(&execution.entry_liquidity).to_uppercase(),
        stop_label(execution),
        target_label(execution),
        hold_label(execution),
        execution.provider_recipe_exit_policy.to_uppercase(),
        lock_label(&execution.profit_lock_policy),
    )
}

/// Format configured route sizing, asset leverage, cadence, and entry-age limit.
pub(crate) fn risk_label(
    evaluation: &CohortProviderEvaluation,
    providers: &[CohortProvider],
    assets: &[CohortAssetConfig],
) -> String {
    let Some(provider) = provider(evaluation, providers) else {
        return "CONFIGURED RISK UNAVAILABLE".into();
    };
    let asset = assets.iter().find(|row| row.symbol == evaluation.symbol);
    let sizing = provider.sizing_overrides.get(&evaluation.symbol);
    let margin = sizing
        .map(|row| row.margin_fraction)
        .or(asset.map(|row| row.margin_fraction));
    let cap = sizing
        .map(|row| row.max_notional_usd)
        .or(asset.map(|row| row.max_notional_usd));
    let leverage = asset.map(|row| row.leverage);
    format!(
        "CONFIGURED RISK // MARGIN {} // NOTIONAL CAP {} // LEVERAGE {} // MAX SIGNAL AGE {}S // TIMEFRAME {}",
        margin.map_or_else(|| "N/A".into(), |value| format!("{:.1}%", value * 100.0)),
        cap.map_or_else(|| "N/A".into(), |value| format!("${value:.2}")),
        leverage.map_or_else(|| "N/A".into(), |value| format!("{value:.1}X")),
        provider.maximum_entry_delay_seconds,
        provider.timeframe.to_uppercase(),
    )
}

/// Format arrival time, full decision date, and measured decision age.
pub(crate) fn timing_label(evaluation: &CohortProviderEvaluation) -> String {
    format!(
        "ARRIVAL ET {} // DECISION ET {} // AGE {}",
        eastern_time(&evaluation.observed_at),
        fill_full_date_time(evaluation.decision_time_ms),
        age_label(evaluation),
    )
}

/// Format the elapsed time from the decision clock to its telemetry arrival.
pub(crate) fn age_label(evaluation: &CohortProviderEvaluation) -> String {
    let Some(arrival_ms) = DateTime::parse_from_rfc3339(&evaluation.observed_at)
        .ok()
        .map(|value| value.timestamp_millis())
    else {
        return "INVALID".into();
    };
    let Ok(decision_ms) = i64::try_from(evaluation.decision_time_ms) else {
        return "INVALID".into();
    };
    let Some(age_ms) = arrival_ms
        .checked_sub(decision_ms)
        .filter(|value| *value >= 0)
    else {
        return "CLOCK ERR".into();
    };
    duration_label(u64::try_from(age_ms / 1_000).unwrap_or(u64::MAX))
}

fn provider<'a>(
    evaluation: &CohortProviderEvaluation,
    providers: &'a [CohortProvider],
) -> Option<&'a CohortProvider> {
    providers.iter().find(|row| {
        row.strategy_id == evaluation.strategy_id && row.symbols.contains(&evaluation.symbol)
    })
}

fn stop_label(execution: &CohortProviderExecutionContract) -> String {
    match execution.stop_policy.as_str() {
        "fixed_bps" => bps(execution.stop_bps),
        "structural_clamped_bps" => {
            range_bps(execution.minimum_stop_bps, execution.maximum_stop_bps)
        }
        "none" => "NONE".into(),
        value => human_token(value).to_uppercase(),
    }
}

fn target_label(execution: &CohortProviderExecutionContract) -> String {
    match execution.target_policy.as_str() {
        "fixed_bps" => bps(execution.target_bps),
        "reward_risk" => execution
            .target_r_multiple
            .map_or_else(|| "INVALID".into(), |value| format!("{value:.2}R")),
        "none" => "NONE".into(),
        value => human_token(value).to_uppercase(),
    }
}

fn hold_label(execution: &CohortProviderExecutionContract) -> String {
    let soft = duration_label(execution.maximum_hold_seconds);
    if execution.maximum_hold_policy == "fixed" {
        return soft;
    }
    execution.hard_maximum_hold_seconds.map_or_else(
        || format!("{soft}→?"),
        |hard| format!("{soft}→{}", extended_hold_label(hard)),
    )
}

fn extended_hold_label(seconds: u64) -> String {
    if seconds >= 3_600 && seconds.is_multiple_of(3_600) {
        return format!("{}H", seconds / 3_600);
    }
    duration_label(seconds)
}

fn bps(value: Option<f64>) -> String {
    value.map_or_else(|| "INVALID".into(), |number| format!("{number:.0}BPS"))
}

fn range_bps(minimum: Option<f64>, maximum: Option<f64>) -> String {
    match (minimum, maximum) {
        (Some(minimum), Some(maximum)) => format!("{minimum:.0}-{maximum:.0}BPS"),
        _ => "INVALID".into(),
    }
}

fn lock_label(policy: &str) -> String {
    match policy {
        "none" => "OFF".into(),
        "btc_hulk_delayed_component_exit_v2" => "FLOOR/REVERSAL".into(),
        value => human_token(value).to_uppercase(),
    }
}

fn duration_label(seconds: u64) -> String {
    let days = seconds / 86_400;
    let hours = (seconds % 86_400) / 3_600;
    let minutes = (seconds % 3_600) / 60;
    if days > 0 {
        return match (hours, minutes) {
            (0, 0) => format!("{days}D"),
            (hours, 0) => format!("{days}D{hours}H"),
            (0, minutes) => format!("{days}D{minutes}M"),
            (hours, minutes) => format!("{days}D{hours}H{minutes}M"),
        };
    }
    if hours > 0 && minutes > 0 {
        return format!("{hours}H{minutes}M");
    }
    if hours > 0 {
        return format!("{hours}H");
    }
    if minutes > 0 {
        return format!("{minutes}M");
    }
    format!("{seconds}S")
}
