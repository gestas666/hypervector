use std::{collections::BTreeMap, fs};

use hypervector_tui::{
    App,
    backend_cohort::{CohortCandle, CohortProvider},
    backend_cohort_aligned_timer_extension::CohortAlignedTimerExtensionEvidence,
    backend_cohort_allocation::{
        CohortAllocationCapacity, CohortAllocationCapacitySide, CohortAllocationChallenger,
        CohortAllocationExecutionSample, CohortAllocationPortfolio, CohortAllocationProjection,
    },
    backend_cohort_checkpoint::{
        CohortCheckpointTelemetry, CohortLiveAuditStatus, CohortObserverPathEvidence,
        CohortObserverProviderEvidence, CohortVenuePortfolio,
    },
    backend_cohort_configuration::CohortConfigurationGeneration,
    backend_cohort_friction_parity::{CohortFrictionParity, CohortProviderFrictionParity},
    backend_cohort_hulk_entry_quality::{
        CohortHulkEntryQuality, CohortHulkEntryQualityOpen, CohortHulkEntryQualitySide,
        CohortHulkEntryQualitySummary,
    },
    backend_cohort_ignored_provider_exit::{
        CohortClosedIgnoredProviderExit, CohortIgnoredProviderActualExit,
        CohortIgnoredProviderExit, CohortIgnoredProviderExitSignal,
    },
    backend_cohort_open_path::CohortOpenPath,
    backend_cohort_open_post_soft_trail::{CohortOpenPostSoftTrail, CohortOpenPostSoftTrailPolicy},
    backend_cohort_open_profit_lock::{
        CohortOpenProfitLock, CohortOpenProfitLockEconomics, CohortOpenProfitLockPolicy,
    },
    backend_cohort_open_profit_protection::CohortOpenProfitProtection,
    backend_cohort_portfolio::CohortPortfolioEvidence,
    backend_cohort_portfolio_archive::{
        CohortAccountingEpoch, CohortPortfolioArchive, CohortPreservedHistory,
    },
    backend_cohort_regime_conflicts::{CohortRegimeConflictEvidence, CohortRegimeConflictHorizon},
    backend_cohort_repeatability::{CohortRepeatabilityEvidence, CohortRepeatabilitySummary},
    backend_cohort_risk_utilization::{CohortAssetRiskUtilization, CohortRiskUtilization},
    backend_cohort_run_windows::CohortProcessRunWindows,
    backend_cohort_side_composition::{CohortSideComponent, CohortSideComposition},
    backend_cohort_trade_performance::{
        CohortAllTimeTradePerformance, CohortProfileTradePerformance, CohortRunTradePerformance,
        CohortTradePerformance, CohortTradePerformanceSummary,
    },
    backend_cohort_trade_reflections::{
        CohortOpenExitPlan, CohortOpenExtensionPath, CohortOpenTradeReflection,
        CohortRegimeOppositionEpisode, CohortTimerContextEvidence, CohortTimerProviderEvidence,
        CohortTradeEntryFollowthroughPath, CohortTradeExitPath, CohortTradeReflection,
        CohortTradeRegimeContext,
    },
    backend_telemetry::{
        BackendConnectionState, BackendTelemetrySnapshot, parse_backend_telemetry,
    },
    cohort_operator::CohortOperatorAction,
};
use ratatui::{Terminal, backend::TestBackend};
use serde_json::{Value, json};

include!("support/bidirectional_cohort_fixture_base.rs");
include!("support/bidirectional_cohort_fixture_routing.rs");
include!("support/bidirectional_cohort_transition.rs");
include!("support/bidirectional_cohort_regime.rs");
include!("support/bidirectional_cohort_reflection_fixtures.rs");
include!("support/bidirectional_cohort_dashboard.rs");
include!("support/bidirectional_cohort_trade_dashboard.rs");
include!("support/bidirectional_cohort_research.rs");
include!("support/bidirectional_cohort_fill_audit.rs");
include!("support/bidirectional_cohort_navigation.rs");
include!("support/bidirectional_cohort_accessibility.rs");
include!("support/bidirectional_cohort_setup_charts.rs");
include!("support/cohort_hourly_charts.rs");
include!("support/cohort_chart_detail_scroll.rs");
include!("support/bidirectional_cohort_validation.rs");
include!("support/cohort_research_sync_view.rs");
include!("support/cohort_stale_checkpoint_view.rs");
include!("support/cohort_restart_truth.rs");
include!("support/cohort_compact_ops.rs");

include!("support/cohort_open_position_columns.rs");
include!("support/cohort_partial_protection_view.rs");

#[path = "support/cohort_entry_deadline_fixtures.rs"]
mod entry_deadline_fixtures;
include!("support/cohort_entry_deadline_view.rs");

include!("support/cohort_open_hold_view.rs");
include!("support/cohort_strategy_context.rs");
include!("support/cohort_leverage_scope_view.rs");
include!("support/cohort_provider_exit_side_view.rs");
