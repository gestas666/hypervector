//! Read-only labels that separate old position evidence from current wall time.

use crate::backend_cohort_exit_plan::CohortOpenExitPlan;
use crate::backend_source::LIVE_LEDGER_INACTIVITY_LIMIT;

#[derive(Debug, Default)]
pub(crate) struct HoldClock {
    pub evidence: String,
    pub timer: String,
    pub origin: &'static str,
    pub attention: bool,
}

/// Describe a bound timer without asserting that old exposure remains open now.
pub(crate) fn clock_labels(plan: &CohortOpenExitPlan, now_ms: Option<u64>) -> HoldClock {
    let origin = match plan.timer_origin.as_deref() {
        Some("persisted_runtime_opened_at") => "DECISION CLOCK",
        Some("venue_entry_fill_fallback_legacy") => "FILL FALLBACK",
        _ => "ORIGIN UNKNOWN",
    };
    let Some(now) = now_ms.filter(|now| plan.as_of_timestamp_ms.is_none_or(|at| at <= *now)) else {
        return HoldClock {
            evidence: "CLOCK INVALID".into(),
            timer: "CLOCK INVALID".into(),
            origin,
            attention: true,
        };
    };
    let age = plan.as_of_timestamp_ms.map(|at| now - at);
    let stale = age.is_none_or(|age| u128::from(age) > LIVE_LEDGER_INACTIVITY_LIMIT.as_millis());
    let evidence = age.map_or_else(
        || "AGE UNKNOWN".into(),
        |age| {
            format!(
                "AGE {}{}",
                duration_label(age),
                if stale { " OLD" } else { "" }
            )
        },
    );
    let timer = timer_label(plan, now, stale);
    let attention = stale
        || plan.timer_origin.is_none()
        || now >= plan.soft_deadline_timestamp_ms
        || timer == "PLAN UNKNOWN";
    HoldClock {
        evidence,
        timer,
        origin,
        attention,
    }
}

fn timer_label(plan: &CohortOpenExitPlan, now: u64, stale: bool) -> String {
    if plan.soft_deadline_timestamp_ms == 0 {
        return "PLAN UNKNOWN".into();
    }
    match plan.maximum_hold_policy.as_str() {
        "fixed" => deadline_label(
            "FIXED",
            plan.deadline_timestamp_ms,
            plan.as_of_timestamp_ms,
            now,
        ),
        "extend_while_regime_supported" => extension_label(plan, now, stale),
        _ => "PLAN UNKNOWN".into(),
    }
}

fn extension_label(plan: &CohortOpenExitPlan, now: u64, stale: bool) -> String {
    let Some(hard) = plan.hard_deadline_timestamp_ms else {
        return "PLAN UNKNOWN".into();
    };
    if now >= hard || (plan.extension_active && !stale) {
        return deadline_label("HARD", hard, plan.as_of_timestamp_ms, now);
    }
    if plan
        .as_of_timestamp_ms
        .is_some_and(|at| at >= plan.soft_deadline_timestamp_ms)
        && !plan.extension_active
    {
        return deadline_label(
            "SOFT",
            plan.soft_deadline_timestamp_ms,
            plan.as_of_timestamp_ms,
            now,
        );
    }
    if now >= plan.soft_deadline_timestamp_ms {
        return "SOFT PASSED; EXTENSION UNKNOWN".into();
    }
    deadline_label(
        "SOFT",
        plan.soft_deadline_timestamp_ms,
        plan.as_of_timestamp_ms,
        now,
    )
}

fn deadline_label(kind: &str, deadline: u64, observed: Option<u64>, now: u64) -> String {
    let (clock, suffix) = observed
        .filter(|at| *at >= deadline)
        .map_or((now, "IF STILL OPEN"), |at| (at, "AT SNAPSHOT"));
    if clock == deadline {
        format!("{kind} DUE {suffix}")
    } else if clock > deadline {
        format!("{kind} +{} {suffix}", duration_label(clock - deadline))
    } else {
        let seconds = (deadline - clock).div_ceil(1_000);
        format!(
            "{kind} IN {} {suffix}",
            duration_label(seconds.saturating_mul(1_000))
        )
    }
}

/// Format elapsed evidence age at a precision suitable for a compact warning.
pub(crate) fn duration_label(milliseconds: u64) -> String {
    let seconds = milliseconds / 1_000;
    if seconds >= 3_600 {
        format!("{}h{:02}m", seconds / 3_600, seconds % 3_600 / 60)
    } else if seconds >= 60 {
        format!("{}m{:02}s", seconds / 60, seconds % 60)
    } else {
        format!("{seconds}s")
    }
}

/// Read the display clock without substituting a valid-looking epoch on failure.
pub(crate) fn now_ms() -> Option<u64> {
    u64::try_from(chrono::Utc::now().timestamp_millis()).ok()
}

#[cfg(test)]
#[path = "cohort_open_hold_tests.rs"]
mod tests;
