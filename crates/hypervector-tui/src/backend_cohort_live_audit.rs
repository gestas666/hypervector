//! Strict projection of live audit cadence and health evidence.

use serde::Deserialize;

type CohortRunIdentity = (Option<String>, Option<String>, Option<String>);

/// Operator-facing live audit status from one authoritative checkpoint.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortLiveAuditStatus {
    pub row_count: usize,
    pub faults: usize,
    pub poll_cycles: usize,
    pub poll_interval_count: usize,
    pub poll_interval_mean_seconds: Option<f64>,
    pub poll_interval_median_seconds: Option<f64>,
    pub poll_interval_minimum_seconds: Option<f64>,
    pub poll_interval_maximum_seconds: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct LiveAuditRuntimeRaw {
    pub(crate) poll_cycles: usize,
    pub(crate) poll_interval_seconds: LivePollIntervalRaw,
}

#[derive(Debug, Deserialize)]
pub(crate) struct LivePollIntervalRaw {
    pub(crate) count: usize,
    pub(crate) mean: Option<f64>,
    pub(crate) median: Option<f64>,
    pub(crate) minimum: Option<f64>,
    pub(crate) maximum: Option<f64>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct LiveAuditHealthRaw {
    pub(crate) faults: usize,
}

#[derive(Debug, Deserialize)]
pub(crate) struct LiveAuditRunRaw {
    pub(crate) row_count: usize,
    #[serde(default)]
    pub(crate) run_id: Option<String>,
    #[serde(default)]
    pub(crate) profile_id: Option<String>,
    #[serde(default)]
    pub(crate) profile_fingerprint: Option<String>,
}

pub(crate) fn project_live_run_identity(
    run: Option<&LiveAuditRunRaw>,
) -> Result<CohortRunIdentity, String> {
    let Some(run) = run else {
        return Ok((None, None, None));
    };
    let values = (&run.run_id, &run.profile_id, &run.profile_fingerprint);
    if values.0.is_none() && values.1.is_none() && values.2.is_none() {
        return Ok((None, None, None));
    }
    if values.0.as_deref().is_none_or(str::is_empty)
        || values.1.as_deref().is_none_or(str::is_empty)
        || values.2.as_deref().is_none_or(str::is_empty)
    {
        return Err("live checkpoint run identity is incomplete".into());
    }
    Ok((
        run.run_id.clone(),
        run.profile_id.clone(),
        run.profile_fingerprint.clone(),
    ))
}

pub(crate) fn project_live_audit_status(
    runtime: Option<LiveAuditRuntimeRaw>,
    health: Option<LiveAuditHealthRaw>,
    run: Option<LiveAuditRunRaw>,
) -> Result<Option<CohortLiveAuditStatus>, String> {
    let (runtime, health, run) = match (runtime, health, run) {
        (None, None, None) => return Ok(None),
        (Some(runtime), Some(health), Some(run)) => (runtime, health, run),
        _ => return Err("live checkpoint audit health evidence is incomplete".into()),
    };
    validate_intervals(&runtime)?;
    Ok(Some(CohortLiveAuditStatus {
        row_count: run.row_count,
        faults: health.faults,
        poll_cycles: runtime.poll_cycles,
        poll_interval_count: runtime.poll_interval_seconds.count,
        poll_interval_mean_seconds: runtime.poll_interval_seconds.mean,
        poll_interval_median_seconds: runtime.poll_interval_seconds.median,
        poll_interval_minimum_seconds: runtime.poll_interval_seconds.minimum,
        poll_interval_maximum_seconds: runtime.poll_interval_seconds.maximum,
    }))
}

fn validate_intervals(runtime: &LiveAuditRuntimeRaw) -> Result<(), String> {
    let interval = &runtime.poll_interval_seconds;
    let values = [
        interval.minimum,
        interval.median,
        interval.mean,
        interval.maximum,
    ];
    let complete = values.iter().all(Option::is_some);
    let empty = values.iter().all(Option::is_none);
    let bounded = match values {
        [Some(minimum), Some(median), Some(mean), Some(maximum)] => {
            minimum.is_finite()
                && median.is_finite()
                && mean.is_finite()
                && maximum.is_finite()
                && 0.0 <= minimum
                && minimum <= median
                && median <= maximum
                && minimum <= mean
                && mean <= maximum
        }
        _ => false,
    };
    if interval.count > runtime.poll_cycles || (!empty && (!complete || !bounded)) {
        return Err("live checkpoint audit cadence evidence is invalid".into());
    }
    if interval.count == 0 && !empty || interval.count > 0 && !complete {
        return Err("live checkpoint audit cadence evidence is inconsistent".into());
    }
    Ok(())
}
