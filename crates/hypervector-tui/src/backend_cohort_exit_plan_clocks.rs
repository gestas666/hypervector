//! Checked timer provenance and source-observation arithmetic.

use super::{CohortOpenExitPlan, RawOpenExitPlan};

pub(super) fn validate_origin(raw: &RawOpenExitPlan, soft: u64) -> Result<(), String> {
    let opened = match (raw.opened_at_ms, raw.timer_origin.as_deref()) {
        (None, None) => None,
        (
            Some(opened),
            Some("persisted_runtime_opened_at" | "venue_entry_fill_fallback_legacy"),
        ) => Some(opened),
        _ => return Err("open timer origin is missing or unsupported".into()),
    };
    if let Some(opened) = opened
        && deadline(opened, raw.maximum_hold_seconds)? != soft
    {
        return Err("open timer origin disagrees with soft deadline".into());
    }
    if let (Some(seconds), Some(hard)) = (
        raw.hard_maximum_hold_seconds,
        raw.hard_deadline_timestamp_ms,
    ) {
        let extra = seconds
            .checked_sub(raw.maximum_hold_seconds)
            .ok_or_else(|| "open hard hold precedes soft hold".to_string())?;
        if deadline(soft, extra)? != hard {
            return Err("open timer hard deadline disagrees with duration".into());
        }
    }
    Ok(())
}

fn deadline(opened: u64, seconds: u64) -> Result<u64, String> {
    seconds
        .checked_mul(1_000)
        .and_then(|ms| opened.checked_add(ms))
        .ok_or_else(|| "open timer deadline overflows milliseconds".to_string())
}

impl CohortOpenExitPlan {
    /// Bind source observation time, preserving explicit absence in legacy evidence.
    pub(crate) fn bind_observation(&mut self, observed: Option<u64>) -> Result<(), String> {
        if let Some(observed) = observed {
            if observed == 0 || self.opened_at_ms.is_some_and(|opened| opened > observed) {
                return Err("open timer observation precedes its origin".into());
            }
            if self.remaining_time_ms != self.deadline_timestamp_ms.saturating_sub(observed)
                || self.expired != (observed >= self.deadline_timestamp_ms)
            {
                return Err("open timer remaining time disagrees with observation clock".into());
            }
            if self.extension_active
                && (observed < self.soft_deadline_timestamp_ms
                    || self
                        .hard_deadline_timestamp_ms
                        .is_none_or(|hard| observed >= hard))
            {
                return Err(
                    "open timer extension is outside its observed soft/hard interval".into(),
                );
            }
        }
        self.as_of_timestamp_ms = observed;
        Ok(())
    }
}
