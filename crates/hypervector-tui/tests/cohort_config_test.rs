use std::{collections::BTreeMap, fs};

use hypervector_tui::{
    App,
    backend_cohort::{
        BackendCohortTelemetry, CohortAssetConfig, CohortPrestartBackupEvidence, CohortProvider,
        CohortProviderSizing, CohortRuntimeConfig,
    },
    backend_cohort_checkpoint::CohortCheckpointTelemetry,
    backend_cohort_configuration::{
        CohortConfigurationGeneration, CohortPendingAssetSizing, CohortPendingExitPolicy,
    },
    backend_cohort_risk_utilization::{
        CohortAssetRiskUtilization, CohortProviderRiskUtilization, CohortRiskUtilization,
    },
    backend_growth_preflight::{
        GrowthPreflightAssetTelemetry, GrowthPreflightRetiredAssetTelemetry,
        GrowthPreflightTelemetry,
    },
    backend_telemetry::BackendTelemetrySnapshot,
};
use ratatui::{Terminal, backend::TestBackend};
use serde_json::Value;
use tempfile::tempdir;

include!("support/cohort_config_profile.rs");
include!("support/cohort_config_evidence.rs");
include!("support/cohort_config_slippage.rs");
include!("support/cohort_observer_scope.rs");
