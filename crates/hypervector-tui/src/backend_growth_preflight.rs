//! Strict read-only projection of the multi-asset growth sizing preflight.

use std::collections::BTreeSet;
use std::fs;
use std::path::PathBuf;
use std::time::{Duration, SystemTime};

use chrono::DateTime;
use serde::Deserialize;

use crate::backend_growth_preflight_retired::{RetiredAsset, valid_retired_asset};

const STATUS_INACTIVITY_LIMIT: Duration = Duration::from_secs(120);
const EXPECTED_OPERATION: &str = "multi_asset_read_only_preflight";

/// Per-asset fee, sizing, and visible-depth readiness evidence.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct GrowthPreflightAssetTelemetry {
    pub symbol: String,
    pub effective_fee_status: String,
    pub one_way_taker_fee_bps: Option<f64>,
    pub margin_fraction: f64,
    pub leverage: f64,
    pub planned_margin_usd: f64,
    pub planned_notional_usd: f64,
    pub above_minimum_lot: bool,
    pub buy_complete: bool,
    pub buy_visible_cost_bps: Option<f64>,
    pub sell_complete: bool,
    pub sell_visible_cost_bps: Option<f64>,
    pub sizing_technically_ready: bool,
}

/// Latest validated report-only growth profile preflight.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct GrowthPreflightTelemetry {
    pub configured: bool,
    pub available: bool,
    pub stale: bool,
    pub issue: Option<String>,
    pub observed_at_utc: Option<String>,
    pub candidate_profile_id: Option<String>,
    pub candidate_profile_fingerprint: Option<String>,
    pub candidate_source_path: Option<String>,
    pub sizing_reference_equity_usd: Option<f64>,
    pub maximum_positions: Option<usize>,
    pub maximum_configured_margin_fraction: Option<f64>,
    pub open_positions: Option<usize>,
    pub open_orders: Option<usize>,
    pub ledger_reconciled: Option<bool>,
    pub sizing_technically_ready: Option<bool>,
    pub technically_ready_for_profile_transition: Option<bool>,
    pub transition_blocking_assets: Vec<String>,
    pub readiness_reasons: Vec<String>,
    pub assets: Vec<GrowthPreflightAssetTelemetry>,
}

impl GrowthPreflightTelemetry {
    fn unavailable(issue: impl Into<String>) -> Self {
        Self {
            configured: true,
            issue: Some(issue.into()),
            ..Self::default()
        }
    }
}

/// Read one optional growth preflight with last-known-good retention.
pub struct GrowthPreflightSource {
    path: Option<PathBuf>,
    signature: Option<(u64, SystemTime)>,
    cached: GrowthPreflightTelemetry,
}

impl GrowthPreflightSource {
    /// Create an execution-incapable file source.
    pub fn new(path: Option<PathBuf>) -> Self {
        Self {
            path,
            signature: None,
            cached: GrowthPreflightTelemetry::default(),
        }
    }

    /// Refresh the sidecar, retaining validated stale evidence on read failure.
    pub fn refresh(&mut self) -> GrowthPreflightTelemetry {
        let Some(path) = self.path.as_ref() else {
            return GrowthPreflightTelemetry::default();
        };
        let metadata = match fs::metadata(path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("growth preflight metadata error: {error}")),
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.signature == Some(signature) {
            return apply_freshness(self.cached.clone(), modified, SystemTime::now());
        }
        let content = match fs::read_to_string(path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("growth preflight read error: {error}")),
        };
        match parse_growth_preflight(&content) {
            Ok(value) => {
                self.signature = Some(signature);
                self.cached = apply_freshness(value, modified, SystemTime::now());
                self.cached.clone()
            }
            Err(error) => self.failed(error),
        }
    }

    fn failed(&self, issue: String) -> GrowthPreflightTelemetry {
        if self.cached.available {
            let mut cached = self.cached.clone();
            cached.stale = true;
            cached.issue = Some(issue);
            cached
        } else {
            GrowthPreflightTelemetry::unavailable(issue)
        }
    }
}

#[derive(Debug, Deserialize)]
struct Document {
    schema_version: u64,
    observed_at_utc: String,
    identity: Identity,
    authority: Authority,
    portfolio: Portfolio,
    assets: Vec<Asset>,
    #[serde(default)]
    retired_assets: Vec<RetiredAsset>,
}

#[derive(Debug, Deserialize)]
struct Identity {
    candidate_profile_id: String,
    candidate_profile_fingerprint: String,
    candidate_source_path: String,
    candidate_differs_from_active: bool,
    network: String,
    margin_mode: String,
}

#[derive(Debug, Deserialize)]
struct Authority {
    execution_authority: String,
    execution_client_constructed: bool,
    signing_key_required: bool,
    operation: String,
}

#[derive(Debug, Deserialize)]
struct Portfolio {
    configured_assets: usize,
    maximum_positions: usize,
    unused_capacity_slots: usize,
    maximum_configured_margin_fraction: f64,
    sizing_reference_equity_usd: f64,
    sizing_reference_source: String,
    open_positions: usize,
    open_orders: usize,
    flat_no_orders: bool,
    transition_blocking_assets: Vec<String>,
    ledger_reconciled: bool,
    sizing_technically_ready: bool,
    technically_ready_for_profile_transition: bool,
    readiness_reasons: Vec<String>,
    performance_gate: bool,
    balance_gate: bool,
}

#[derive(Debug, Deserialize)]
struct Asset {
    symbol: String,
    venue: Venue,
    position: Position,
    open_orders: Vec<serde_json::Value>,
    ledger_reconciliation: Reconciliation,
    sizing: Sizing,
    visible_depth: Depth,
    sizing_technically_ready: bool,
}

#[derive(Debug, Deserialize)]
struct Venue {
    effective_fee_status: String,
    effective_taker_fee_rate: Option<f64>,
    one_way_taker_fee_bps: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct Position {
    size_signed: f64,
}

#[derive(Debug, Deserialize)]
struct Reconciliation {
    matches: bool,
}

#[derive(Debug, Deserialize)]
struct Sizing {
    sizing_reference_equity_usd: f64,
    margin_fraction: f64,
    leverage: f64,
    planned_margin_usd: f64,
    planned_notional_usd: f64,
    above_minimum_lot: bool,
}

#[derive(Debug, Deserialize)]
struct Depth {
    buy_complete: bool,
    buy_visible_cost_bps: Option<f64>,
    sell_complete: bool,
    sell_visible_cost_bps: Option<f64>,
}

/// Parse one execution-incapable growth sizing preflight.
pub fn parse_growth_preflight(content: &str) -> Result<GrowthPreflightTelemetry, String> {
    let document: Document = serde_json::from_str(content)
        .map_err(|error| format!("invalid growth preflight JSON: {error}"))?;
    validate_document(&document)?;
    Ok(project(document))
}

fn validate_document(document: &Document) -> Result<(), String> {
    if document.schema_version != 1
        || document.authority.execution_authority != "none"
        || document.authority.execution_client_constructed
        || document.authority.signing_key_required
        || document.authority.operation != EXPECTED_OPERATION
    {
        return Err("growth preflight schema or authority contract is invalid".into());
    }
    if DateTime::parse_from_rfc3339(&document.observed_at_utc).is_err()
        || document.identity.network != "mainnet"
        || document.identity.margin_mode != "isolated"
        || !document.identity.candidate_differs_from_active
        || !valid_identity(&document.identity)
    {
        return Err("growth preflight candidate identity is invalid".into());
    }
    validate_assets(document)?;
    validate_portfolio(document)
}

fn valid_identity(identity: &Identity) -> bool {
    !identity.candidate_profile_id.trim().is_empty()
        && !identity.candidate_source_path.trim().is_empty()
        && identity.candidate_profile_fingerprint.len() == 64
        && identity
            .candidate_profile_fingerprint
            .chars()
            .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase())
}

fn validate_assets(document: &Document) -> Result<(), String> {
    let mut symbols = BTreeSet::new();
    symbols.extend(document.assets.iter().map(|asset| asset.symbol.as_str()));
    if symbols.len() != document.assets.len()
        || symbols.iter().any(|symbol| symbol.trim().is_empty())
    {
        return Err("growth preflight asset identity is invalid".into());
    }
    for asset in &document.assets {
        validate_asset(asset, document.portfolio.sizing_reference_equity_usd)?;
    }
    for asset in &document.retired_assets {
        if !symbols.insert(asset.symbol.as_str()) || !valid_retired_asset(asset) {
            return Err("growth preflight retired asset evidence is invalid".into());
        }
    }
    Ok(())
}

fn validate_asset(asset: &Asset, reference: f64) -> Result<(), String> {
    let fee_resolved = asset.venue.effective_fee_status.starts_with("resolved_");
    let fee_valid = match (
        fee_resolved,
        asset.venue.effective_taker_fee_rate,
        asset.venue.one_way_taker_fee_bps,
    ) {
        (true, Some(rate), Some(bps)) => {
            finite_nonnegative(rate)
                && finite_nonnegative(bps)
                && (rate * 10_000.0 - bps).abs() <= 1e-9
        }
        (false, None, None) if asset.venue.effective_fee_status.starts_with("unresolved_") => true,
        _ => false,
    };
    let sizing_valid = finite_positive(asset.sizing.margin_fraction)
        && asset.sizing.margin_fraction <= 1.0
        && finite_positive(asset.sizing.leverage)
        && finite_positive(asset.sizing.planned_margin_usd)
        && finite_positive(asset.sizing.planned_notional_usd)
        && (asset.sizing.sizing_reference_equity_usd - reference).abs() <= 1e-9
        && (asset.sizing.planned_margin_usd * asset.sizing.leverage
            - asset.sizing.planned_notional_usd)
            .abs()
            <= 1e-6;
    let depth_valid = valid_depth_side(
        asset.visible_depth.buy_complete,
        asset.visible_depth.buy_visible_cost_bps,
    ) && valid_depth_side(
        asset.visible_depth.sell_complete,
        asset.visible_depth.sell_visible_cost_bps,
    );
    let expected_ready = asset.sizing.above_minimum_lot
        && asset.visible_depth.buy_complete
        && asset.visible_depth.sell_complete
        && fee_resolved;
    if !asset.position.size_signed.is_finite()
        || !fee_valid
        || !sizing_valid
        || !depth_valid
        || asset.sizing_technically_ready != expected_ready
    {
        return Err(format!(
            "{} growth preflight fee or sizing evidence is invalid",
            asset.symbol
        ));
    }
    Ok(())
}

fn validate_portfolio(document: &Document) -> Result<(), String> {
    let portfolio = &document.portfolio;
    let mut blocking = document
        .assets
        .iter()
        .filter(|asset| asset.position.size_signed != 0.0 || !asset.open_orders.is_empty())
        .map(|asset| asset.symbol.as_str())
        .collect::<Vec<_>>();
    blocking.extend(
        document
            .retired_assets
            .iter()
            .filter(|asset| !asset.flat_no_orders)
            .map(|asset| asset.symbol.as_str()),
    );
    let sizing_ready = document
        .assets
        .iter()
        .all(|asset| asset.sizing_technically_ready);
    let ledger_reconciled = document
        .assets
        .iter()
        .all(|asset| asset.ledger_reconciliation.matches)
        && document
            .retired_assets
            .iter()
            .all(|asset| asset.ledger_reconciled);
    let expected_ready = blocking.is_empty() && sizing_ready && ledger_reconciled;
    let fields_valid = portfolio.configured_assets == document.assets.len()
        && portfolio.maximum_positions > 0
        && portfolio.unused_capacity_slots
            == portfolio
                .maximum_positions
                .saturating_sub(document.assets.len())
        && finite_positive(portfolio.sizing_reference_equity_usd)
        && portfolio.sizing_reference_source == "explicit_scenario"
        && portfolio.open_positions
            == document
                .assets
                .iter()
                .filter(|asset| asset.position.size_signed != 0.0)
                .count()
                + document
                    .retired_assets
                    .iter()
                    .filter(|asset| asset.position_size_signed != 0.0)
                    .count()
        && portfolio.open_orders
            == document
                .assets
                .iter()
                .map(|asset| asset.open_orders.len())
                .sum::<usize>()
                + document
                    .retired_assets
                    .iter()
                    .map(|asset| asset.open_order_ids.len())
                    .sum::<usize>()
        && portfolio.flat_no_orders == blocking.is_empty()
        && portfolio.transition_blocking_assets == blocking
        && portfolio.ledger_reconciled == ledger_reconciled
        && portfolio.sizing_technically_ready == sizing_ready
        && portfolio.technically_ready_for_profile_transition == expected_ready
        && portfolio.readiness_reasons.is_empty() == expected_ready
        && !portfolio.performance_gate
        && !portfolio.balance_gate
        && finite_nonnegative(portfolio.maximum_configured_margin_fraction);
    if !fields_valid {
        return Err("growth preflight portfolio readiness is inconsistent".into());
    }
    Ok(())
}

fn valid_depth_side(complete: bool, cost: Option<f64>) -> bool {
    if complete {
        cost.is_some_and(finite_nonnegative)
    } else {
        cost.is_none()
    }
}

fn finite_positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn finite_nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn project(document: Document) -> GrowthPreflightTelemetry {
    GrowthPreflightTelemetry {
        configured: true,
        available: true,
        observed_at_utc: Some(document.observed_at_utc),
        candidate_profile_id: Some(document.identity.candidate_profile_id),
        candidate_profile_fingerprint: Some(document.identity.candidate_profile_fingerprint),
        candidate_source_path: Some(document.identity.candidate_source_path),
        sizing_reference_equity_usd: Some(document.portfolio.sizing_reference_equity_usd),
        maximum_positions: Some(document.portfolio.maximum_positions),
        maximum_configured_margin_fraction: Some(
            document.portfolio.maximum_configured_margin_fraction,
        ),
        open_positions: Some(document.portfolio.open_positions),
        open_orders: Some(document.portfolio.open_orders),
        ledger_reconciled: Some(document.portfolio.ledger_reconciled),
        sizing_technically_ready: Some(document.portfolio.sizing_technically_ready),
        technically_ready_for_profile_transition: Some(
            document.portfolio.technically_ready_for_profile_transition,
        ),
        transition_blocking_assets: document.portfolio.transition_blocking_assets,
        readiness_reasons: document.portfolio.readiness_reasons,
        assets: document.assets.into_iter().map(project_asset).collect(),
        ..GrowthPreflightTelemetry::default()
    }
}

fn project_asset(asset: Asset) -> GrowthPreflightAssetTelemetry {
    GrowthPreflightAssetTelemetry {
        symbol: asset.symbol,
        effective_fee_status: asset.venue.effective_fee_status,
        one_way_taker_fee_bps: asset.venue.one_way_taker_fee_bps,
        margin_fraction: asset.sizing.margin_fraction,
        leverage: asset.sizing.leverage,
        planned_margin_usd: asset.sizing.planned_margin_usd,
        planned_notional_usd: asset.sizing.planned_notional_usd,
        above_minimum_lot: asset.sizing.above_minimum_lot,
        buy_complete: asset.visible_depth.buy_complete,
        buy_visible_cost_bps: asset.visible_depth.buy_visible_cost_bps,
        sell_complete: asset.visible_depth.sell_complete,
        sell_visible_cost_bps: asset.visible_depth.sell_visible_cost_bps,
        sizing_technically_ready: asset.sizing_technically_ready,
    }
}

fn apply_freshness(
    mut telemetry: GrowthPreflightTelemetry,
    modified: SystemTime,
    now: SystemTime,
) -> GrowthPreflightTelemetry {
    telemetry.stale = now.duration_since(modified).unwrap_or_default() > STATUS_INACTIVITY_LIMIT;
    if telemetry.stale {
        telemetry.issue = Some("growth preflight point-in-time evidence is stale".into());
    }
    telemetry
}
