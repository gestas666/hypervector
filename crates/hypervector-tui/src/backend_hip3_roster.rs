//! Typed read-only projection of the backend HIP-3 roster checkpoint.

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::time::{Duration, SystemTime};

use chrono::DateTime;
use serde::Deserialize;

const EXPECTED_MODE: &str = "hip3_roster_observer_checkpoint";
const EXPECTED_LEVELS: usize = 20;
const STATUS_INACTIVITY_LIMIT: Duration = Duration::from_secs(300);

/// One exact order-book summary authored by the HIP-3 observer.
#[derive(Debug, Clone, Default)]
pub struct Hip3BookTelemetry {
    pub exchange_timestamp_ms: u64,
    pub mid_price: f64,
    pub spread_bps: f64,
    pub bid_levels: usize,
    pub ask_levels: usize,
    pub depth_5_pressure: f64,
    pub depth_20_pressure: f64,
}

/// Venue constraints and effective fee state for one HIP-3 market.
#[derive(Debug, Clone, Default)]
pub struct Hip3VenueTelemetry {
    pub mark_price: f64,
    pub max_leverage: u32,
    pub funding_rate_hourly: Option<f64>,
    pub effective_fee_status: String,
    pub maker_fee_rate: Option<f64>,
    pub taker_fee_rate: Option<f64>,
}

/// One exact HIP-3 market row with account exposure truth.
#[derive(Debug, Clone, Default)]
pub struct Hip3MarketTelemetry {
    pub symbol: String,
    pub book: Hip3BookTelemetry,
    pub venue: Hip3VenueTelemetry,
    pub position_size_signed: f64,
    pub open_order_count: usize,
}

/// Explicit non-equivalence state for the user's requested WTI identity.
#[derive(Debug, Clone, Default)]
pub struct WtiAliasTelemetry {
    pub status: String,
    pub live_symbol: Option<String>,
    pub historical_symbol: String,
    pub active_alternative: String,
    pub equivalence_assumed: bool,
}

/// Latest validated report-only HIP-3 roster telemetry.
#[derive(Debug, Clone, Default)]
pub struct Hip3RosterTelemetry {
    pub configured: bool,
    pub available: bool,
    pub stale: bool,
    pub issue: Option<String>,
    pub lifecycle: Option<String>,
    pub observed_at_utc: Option<String>,
    pub polls: Option<u64>,
    pub active_symbols: Vec<String>,
    pub markets: Vec<Hip3MarketTelemetry>,
    pub wti_alias: Option<WtiAliasTelemetry>,
}

impl Hip3RosterTelemetry {
    fn unavailable(issue: impl Into<String>) -> Self {
        Self {
            configured: true,
            issue: Some(issue.into()),
            ..Self::default()
        }
    }
}

#[derive(Debug, Deserialize)]
struct RosterDocument {
    schema_version: u64,
    mode: String,
    status: String,
    observed_at_utc: String,
    active_symbols: Vec<String>,
    markets: Option<Vec<MarketDocument>>,
    requested_aliases: HashMap<String, WtiAliasTelemetryDocument>,
    error: Option<ErrorDocument>,
    execution_authority: String,
    report_only: bool,
    automatic_promotion: bool,
    runtime_strategy_changed: bool,
    signing_client_constructed: bool,
    lifecycle: String,
    polls: u64,
}

#[derive(Debug, Deserialize)]
struct MarketDocument {
    symbol: String,
    venue_namespace: String,
    venue: VenueDocument,
    book: BookDocument,
    account: AccountDocument,
}

#[derive(Debug, Deserialize)]
struct VenueDocument {
    mark_price: f64,
    max_leverage: u32,
    #[serde(default)]
    funding_rate_hourly: Option<f64>,
    effective_fee_status: String,
    maker_fee_rate: Option<f64>,
    taker_fee_rate: Option<f64>,
}

#[derive(Debug, Deserialize)]
struct BookDocument {
    exchange_timestamp_ms: u64,
    mid_price: f64,
    spread_bps: f64,
    level_count: LevelCountDocument,
    depth_5: DepthDocument,
    depth_20: DepthDocument,
}

#[derive(Debug, Deserialize)]
struct LevelCountDocument {
    bids: usize,
    asks: usize,
}

#[derive(Debug, Deserialize)]
struct DepthDocument {
    order_pressure: f64,
}

#[derive(Debug, Deserialize)]
struct AccountDocument {
    open_order_count: usize,
    position: PositionDocument,
}

#[derive(Debug, Deserialize)]
struct PositionDocument {
    size_signed: f64,
}

#[derive(Debug, Deserialize)]
struct WtiAliasTelemetryDocument {
    status: String,
    live_symbol: Option<String>,
    historical_symbol: String,
    active_alternative: String,
    equivalence_assumed: bool,
}

#[derive(Debug, Deserialize)]
struct ErrorDocument {
    #[serde(rename = "type")]
    kind: String,
    message: String,
}

/// Parse and validate one execution-incapable HIP-3 roster checkpoint.
pub fn parse_hip3_roster_status(content: &str) -> Result<Hip3RosterTelemetry, String> {
    let document: RosterDocument = serde_json::from_str(content)
        .map_err(|error| format!("invalid HIP-3 roster checkpoint JSON: {error}"))?;
    validate_contract(&document)?;
    let alias = validate_wti_alias(&document)?;
    match document.status.as_str() {
        "available" => project_available(document, alias),
        "unavailable" => project_unavailable(document, alias),
        _ => Err("HIP-3 roster checkpoint status is invalid".into()),
    }
}

fn validate_contract(document: &RosterDocument) -> Result<(), String> {
    if document.schema_version != 1 || document.mode != EXPECTED_MODE {
        return Err("HIP-3 roster checkpoint schema or mode is unsupported".into());
    }
    if document.execution_authority != "none"
        || !document.report_only
        || document.automatic_promotion
        || document.runtime_strategy_changed
        || document.signing_client_constructed
    {
        return Err("HIP-3 roster checkpoint violates the report-only contract".into());
    }
    if !matches!(
        document.lifecycle.as_str(),
        "running" | "stopped" | "failed_start"
    ) {
        return Err("HIP-3 roster lifecycle is invalid".into());
    }
    DateTime::parse_from_rfc3339(&document.observed_at_utc)
        .map_err(|error| format!("invalid HIP-3 roster observation time: {error}"))?;
    Ok(())
}

fn validate_wti_alias(document: &RosterDocument) -> Result<WtiAliasTelemetry, String> {
    let alias = document
        .requested_aliases
        .get("WTIOIL")
        .ok_or_else(|| "HIP-3 roster omits the WTIOIL identity state".to_string())?;
    if alias.status != "historical_only"
        || alias.live_symbol.is_some()
        || alias.historical_symbol != "cash:WTI"
        || alias.active_alternative != "xyz:BRENTOIL"
        || alias.equivalence_assumed
    {
        return Err("HIP-3 roster WTIOIL identity contract is invalid".into());
    }
    Ok(WtiAliasTelemetry {
        status: alias.status.clone(),
        live_symbol: alias.live_symbol.clone(),
        historical_symbol: alias.historical_symbol.clone(),
        active_alternative: alias.active_alternative.clone(),
        equivalence_assumed: alias.equivalence_assumed,
    })
}

fn project_available(
    document: RosterDocument,
    alias: WtiAliasTelemetry,
) -> Result<Hip3RosterTelemetry, String> {
    if document.error.is_some() {
        return Err("available HIP-3 roster is success-shaped with an error".into());
    }
    let markets = document
        .markets
        .as_ref()
        .ok_or_else(|| "available HIP-3 roster has no markets".to_string())?;
    if markets.is_empty() || markets.len() != document.active_symbols.len() {
        return Err("HIP-3 roster market coverage is incomplete".into());
    }
    let projected = markets
        .iter()
        .map(project_market)
        .collect::<Result<Vec<_>, _>>()?;
    let observed = projected
        .iter()
        .map(|market| market.symbol.as_str())
        .collect::<Vec<_>>();
    let expected = document
        .active_symbols
        .iter()
        .map(String::as_str)
        .collect::<Vec<_>>();
    if observed != expected {
        return Err("HIP-3 roster market identity or ordering is inconsistent".into());
    }
    Ok(Hip3RosterTelemetry {
        configured: true,
        available: true,
        lifecycle: Some(document.lifecycle),
        observed_at_utc: Some(document.observed_at_utc),
        polls: Some(document.polls),
        active_symbols: document.active_symbols,
        markets: projected,
        wti_alias: Some(alias),
        ..Hip3RosterTelemetry::default()
    })
}

fn project_market(document: &MarketDocument) -> Result<Hip3MarketTelemetry, String> {
    if !document.symbol.starts_with("xyz:") || document.venue_namespace != "xyz" {
        return Err("HIP-3 roster market namespace identity is invalid".into());
    }
    if document.book.level_count.bids != EXPECTED_LEVELS
        || document.book.level_count.asks != EXPECTED_LEVELS
    {
        return Err(format!(
            "{} HIP-3 book level count is incomplete",
            document.symbol
        ));
    }
    validate_numbers(document)?;
    validate_fees(&document.symbol, &document.venue)?;
    Ok(Hip3MarketTelemetry {
        symbol: document.symbol.clone(),
        book: Hip3BookTelemetry {
            exchange_timestamp_ms: document.book.exchange_timestamp_ms,
            mid_price: document.book.mid_price,
            spread_bps: document.book.spread_bps,
            bid_levels: document.book.level_count.bids,
            ask_levels: document.book.level_count.asks,
            depth_5_pressure: document.book.depth_5.order_pressure,
            depth_20_pressure: document.book.depth_20.order_pressure,
        },
        venue: Hip3VenueTelemetry {
            mark_price: document.venue.mark_price,
            max_leverage: document.venue.max_leverage,
            funding_rate_hourly: document.venue.funding_rate_hourly,
            effective_fee_status: document.venue.effective_fee_status.clone(),
            maker_fee_rate: document.venue.maker_fee_rate,
            taker_fee_rate: document.venue.taker_fee_rate,
        },
        position_size_signed: document.account.position.size_signed,
        open_order_count: document.account.open_order_count,
    })
}

fn validate_numbers(document: &MarketDocument) -> Result<(), String> {
    let finite = document.book.mid_price.is_finite()
        && document.book.spread_bps.is_finite()
        && document.book.depth_5.order_pressure.is_finite()
        && document.book.depth_20.order_pressure.is_finite()
        && document.venue.mark_price.is_finite()
        && document
            .venue
            .funding_rate_hourly
            .is_none_or(f64::is_finite)
        && document.account.position.size_signed.is_finite();
    let pressure_valid = (-1.0..=1.0).contains(&document.book.depth_5.order_pressure)
        && (-1.0..=1.0).contains(&document.book.depth_20.order_pressure);
    if !finite
        || document.book.exchange_timestamp_ms == 0
        || document.book.mid_price <= 0.0
        || document.book.spread_bps < 0.0
        || document.venue.mark_price <= 0.0
        || document.venue.max_leverage == 0
        || !pressure_valid
    {
        return Err(format!(
            "{} HIP-3 market values are invalid",
            document.symbol
        ));
    }
    Ok(())
}

fn validate_fees(symbol: &str, venue: &VenueDocument) -> Result<(), String> {
    match venue.effective_fee_status.as_str() {
        "resolved"
            if venue.maker_fee_rate.is_some_and(valid_fee)
                && venue.taker_fee_rate.is_some_and(valid_fee) =>
        {
            Ok(())
        }
        status
            if status.starts_with("unresolved_")
                && venue.maker_fee_rate.is_none()
                && venue.taker_fee_rate.is_none() =>
        {
            Ok(())
        }
        _ => Err(format!(
            "{symbol} HIP-3 effective fee state is inconsistent"
        )),
    }
}

fn valid_fee(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn project_unavailable(
    document: RosterDocument,
    alias: WtiAliasTelemetry,
) -> Result<Hip3RosterTelemetry, String> {
    if document.markets.is_some() {
        return Err("unavailable HIP-3 roster contains market values".into());
    }
    let error = document
        .error
        .as_ref()
        .filter(|error| !error.kind.is_empty() && !error.message.is_empty())
        .ok_or_else(|| "unavailable HIP-3 roster has no technical error".to_string())?;
    Ok(Hip3RosterTelemetry {
        configured: true,
        issue: Some(format!("{}: {}", error.kind, error.message)),
        lifecycle: Some(document.lifecycle),
        observed_at_utc: Some(document.observed_at_utc),
        polls: Some(document.polls),
        active_symbols: document.active_symbols,
        wti_alias: Some(alias),
        ..Hip3RosterTelemetry::default()
    })
}

/// Independent file source that cannot mutate backend execution telemetry.
pub struct Hip3RosterSource {
    path: Option<PathBuf>,
    signature: Option<(u64, SystemTime)>,
    cached: Hip3RosterTelemetry,
}

impl Hip3RosterSource {
    /// Configure one optional report-only roster checkpoint path.
    pub fn new(path: Option<PathBuf>) -> Self {
        Self {
            path,
            signature: None,
            cached: Hip3RosterTelemetry::default(),
        }
    }

    /// Refresh the roster while retaining the last valid value as stale.
    pub fn refresh(&mut self) -> Hip3RosterTelemetry {
        let Some(path) = self.path.as_ref() else {
            return Hip3RosterTelemetry::default();
        };
        let metadata = match fs::metadata(path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("HIP-3 roster unavailable: {error}")),
        };
        let modified = metadata.modified().unwrap_or(SystemTime::UNIX_EPOCH);
        let signature = (metadata.len(), modified);
        if self.signature == Some(signature) {
            return apply_freshness(self.cached.clone(), modified, SystemTime::now());
        }
        self.load(path.clone(), signature)
    }

    fn load(&mut self, path: PathBuf, signature: (u64, SystemTime)) -> Hip3RosterTelemetry {
        let content = match fs::read_to_string(path) {
            Ok(value) => value,
            Err(error) => return self.failed(format!("HIP-3 roster read failed: {error}")),
        };
        match parse_hip3_roster_status(&content) {
            Ok(status) => {
                self.signature = Some(signature);
                self.cached = apply_freshness(status, signature.1, SystemTime::now());
                self.cached.clone()
            }
            Err(error) => self.failed(error),
        }
    }

    fn failed(&self, issue: String) -> Hip3RosterTelemetry {
        if self.cached.available {
            let mut stale = self.cached.clone();
            stale.stale = true;
            stale.issue = Some(issue);
            stale
        } else {
            Hip3RosterTelemetry::unavailable(issue)
        }
    }
}

fn apply_freshness(
    mut status: Hip3RosterTelemetry,
    modified: SystemTime,
    now: SystemTime,
) -> Hip3RosterTelemetry {
    let inactive = now
        .duration_since(modified)
        .is_ok_and(|age| age > STATUS_INACTIVITY_LIMIT);
    let stopped = status.lifecycle.as_deref() != Some("running");
    status.stale = inactive || stopped;
    if status.stale && status.issue.is_none() {
        status.issue = Some(if stopped {
            "HIP-3 roster observer is not running".into()
        } else {
            "HIP-3 roster has not refreshed for more than five minutes".into()
        });
    }
    status
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_configured_checkpoint_is_explicitly_unavailable() {
        let directory = tempfile::tempdir().expect("tempdir");
        let mut source = Hip3RosterSource::new(Some(directory.path().join("missing.json")));

        let status = source.refresh();

        assert!(status.configured);
        assert!(!status.available);
        assert!(
            status
                .issue
                .as_deref()
                .is_some_and(|value| value.contains("unavailable"))
        );
    }
}
