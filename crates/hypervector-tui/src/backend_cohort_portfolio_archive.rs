//! Strict projection of durable all-profile live portfolio performance.

use std::collections::{BTreeMap, BTreeSet};

use serde::Deserialize;

use crate::backend_cohort_trade_performance::{
    CohortAllTimeTradePerformance, RawTradePerformanceSummary, project_partition,
};

const MODE: &str = "cohort_live_portfolio_archive_v1";
const RETURN_BASIS: &str = "net_pnl_divided_by_sum_entry_margin";

/// Durable all-live performance and its exact symbol coverage.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortPortfolioArchive {
    pub symbols: Vec<String>,
    pub observed_through_utc: Option<String>,
    pub performance: CohortAllTimeTradePerformance,
    pub accounting_epoch: Option<CohortAccountingEpoch>,
    pub preserved_history: Option<CohortPreservedHistory>,
}

/// Read-only backend history retained outside a fresh display epoch.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct CohortPreservedHistory {
    pub symbols: Vec<String>,
    pub observed_through_utc: Option<String>,
    pub performance: CohortAllTimeTradePerformance,
}

/// Exact clean-accounting boundary carried by an epoch-scoped archive.
#[derive(Debug, Clone, Default, PartialEq, Deserialize)]
pub struct CohortAccountingEpoch {
    pub epoch_id: String,
    pub profile_fingerprint: String,
    pub start_venue_timestamp_ms: u64,
    #[serde(default)]
    pub included_profile_fingerprints: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct PortfolioArchiveRaw {
    schema_version: u64,
    mode: String,
    contract: ArchiveContractRaw,
    symbols: Vec<String>,
    #[serde(default)]
    observed_through_utc: Option<String>,
    #[serde(default)]
    accounting_epoch: Option<CohortAccountingEpoch>,
    #[serde(default)]
    preserved_history: Option<PreservedHistoryRaw>,
    coverage: ArchiveCoverageRaw,
    performance: ArchivePerformanceRaw,
}

#[derive(Debug, Deserialize)]
struct PreservedHistoryRaw {
    scope: String,
    symbols: Vec<String>,
    #[serde(default)]
    observed_through_utc: Option<String>,
    coverage: ArchiveCoverageRaw,
    performance: ArchivePerformanceRaw,
}

#[derive(Debug, Deserialize)]
struct ArchiveContractRaw {
    report_only: bool,
    execution_authority: String,
    runtime_strategy_changed: bool,
}

#[derive(Debug, Deserialize)]
struct ArchiveCoverageRaw {
    complete: bool,
    closed_orders: usize,
    leverage_matches: usize,
}

#[derive(Debug, Deserialize)]
struct ArchivePerformanceRaw {
    scope: String,
    return_basis: String,
    total: RawTradePerformanceSummary,
    by_strategy: BTreeMap<String, RawTradePerformanceSummary>,
}

pub(crate) fn project_portfolio_archive(
    raw: Option<PortfolioArchiveRaw>,
) -> Result<Option<CohortPortfolioArchive>, String> {
    let Some(value) = raw else {
        return Ok(None);
    };
    validate_contract(&value)?;
    let (total, by_strategy) = project_partition(
        value.performance.total,
        value.performance.by_strategy,
        "portfolio archive",
    )?;
    if value.coverage.closed_orders != total.closed_trades
        || value.coverage.leverage_matches != value.coverage.closed_orders
    {
        return Err("portfolio archive coverage disagrees with performance".into());
    }
    let preserved_history = value
        .preserved_history
        .map(project_preserved_history)
        .transpose()?;
    Ok(Some(CohortPortfolioArchive {
        symbols: value.symbols,
        observed_through_utc: value.observed_through_utc,
        performance: CohortAllTimeTradePerformance { total, by_strategy },
        accounting_epoch: value.accounting_epoch,
        preserved_history,
    }))
}

fn project_preserved_history(raw: PreservedHistoryRaw) -> Result<CohortPreservedHistory, String> {
    let symbols = raw.symbols.iter().collect::<BTreeSet<_>>();
    if raw.scope != "full_backend_history"
        || !raw.coverage.complete
        || symbols.len() != raw.symbols.len()
        || raw.symbols.iter().any(|symbol| symbol.trim().is_empty())
        || raw.performance.scope != "all_live_history"
        || raw.performance.return_basis != RETURN_BASIS
        || raw
            .observed_through_utc
            .as_ref()
            .is_some_and(|timestamp| chrono::DateTime::parse_from_rfc3339(timestamp).is_err())
    {
        return Err("preserved portfolio history contract is invalid".into());
    }
    let (total, by_strategy) = project_partition(
        raw.performance.total,
        raw.performance.by_strategy,
        "preserved portfolio history",
    )?;
    if raw.coverage.closed_orders != total.closed_trades
        || raw.coverage.leverage_matches != raw.coverage.closed_orders
    {
        return Err("preserved portfolio history coverage disagrees with performance".into());
    }
    Ok(CohortPreservedHistory {
        symbols: raw.symbols,
        observed_through_utc: raw.observed_through_utc,
        performance: CohortAllTimeTradePerformance { total, by_strategy },
    })
}

fn validate_contract(value: &PortfolioArchiveRaw) -> Result<(), String> {
    let symbols = value.symbols.iter().collect::<BTreeSet<_>>();
    if value.schema_version != 1
        || value.mode != MODE
        || !value.contract.report_only
        || value.contract.execution_authority != "none"
        || value.contract.runtime_strategy_changed
        || !value.coverage.complete
        || symbols.len() != value.symbols.len()
        || value.symbols.iter().any(|symbol| symbol.trim().is_empty())
        || value.performance.scope != "all_live_history"
        || value.performance.return_basis != RETURN_BASIS
        || value
            .accounting_epoch
            .as_ref()
            .is_some_and(|epoch| !valid_epoch(epoch))
        || value
            .observed_through_utc
            .as_ref()
            .is_some_and(|timestamp| chrono::DateTime::parse_from_rfc3339(timestamp).is_err())
    {
        return Err("portfolio archive contract is invalid".into());
    }
    Ok(())
}

fn valid_epoch(epoch: &CohortAccountingEpoch) -> bool {
    !epoch.epoch_id.trim().is_empty()
        && valid_fingerprint(&epoch.profile_fingerprint)
        && epoch.start_venue_timestamp_ms > 0
        && valid_profile_lineage(epoch)
}

fn valid_profile_lineage(epoch: &CohortAccountingEpoch) -> bool {
    if epoch.included_profile_fingerprints.is_empty() {
        return true;
    }
    let profiles = epoch
        .included_profile_fingerprints
        .iter()
        .collect::<BTreeSet<_>>();
    profiles.len() == epoch.included_profile_fingerprints.len()
        && profiles.contains(&epoch.profile_fingerprint)
        && profiles.iter().all(|value| valid_fingerprint(value))
}

fn valid_fingerprint(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|character| character.is_ascii_digit() || (b'a'..=b'f').contains(&character))
}
