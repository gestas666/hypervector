//! Strict projection of read-only Hyperliquid portfolio-value evidence.

use chrono::DateTime;
use serde::Deserialize;
use serde_json::Value;

/// One positive spot balance included in the current portfolio total.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortValuedSpotAsset {
    pub symbol: String,
    pub token_index: u64,
    pub total: f64,
    pub price_usd: f64,
    pub value_usd: f64,
    pub market: String,
}

/// Venue total separated from the USDC collateral used by execution sizing.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortVenuePortfolio {
    pub portfolio_value_usd: f64,
    pub execution_collateral_value_usd: f64,
    pub non_usdc_spot_value_usd: f64,
    pub vault_equity_usd: f64,
    pub valued_spot_assets: Vec<CohortValuedSpotAsset>,
    pub observed_at_utc: String,
    pub valuation_source: String,
}

#[derive(Debug, Deserialize)]
struct VenuePortfolioRaw {
    status: String,
    #[serde(default)]
    portfolio_value_usd: Option<f64>,
    #[serde(default)]
    execution_collateral_value_usd: Option<f64>,
    #[serde(default)]
    non_usdc_spot_value_usd: Option<f64>,
    #[serde(default)]
    vault_equity_usd: Option<f64>,
    #[serde(default)]
    valued_spot_assets: Option<Vec<CohortValuedSpotAsset>>,
    #[serde(default)]
    observed_at_utc: Option<String>,
    #[serde(default)]
    valuation_source: Option<String>,
    #[serde(default)]
    technical_issue: Option<String>,
    contract: VenuePortfolioContract,
}

#[derive(Debug, Deserialize)]
struct VenuePortfolioContract {
    report_only: bool,
    execution_authority: String,
    execution_collateral_unchanged: bool,
}

pub(crate) fn project_venue_portfolio(
    value: Option<Value>,
) -> Result<(Option<CohortVenuePortfolio>, Option<String>), String> {
    let Some(value) = value else {
        return Ok((None, None));
    };
    let raw: VenuePortfolioRaw = serde_json::from_value(value)
        .map_err(|error| format!("invalid venue portfolio evidence: {error}"))?;
    validate_contract(&raw.contract)?;
    match raw.status.as_str() {
        "observed" => Ok((Some(project_observed(raw)?), None)),
        "unavailable" => Ok((None, Some(unavailable_issue(raw)?))),
        _ => Err("venue portfolio status is unsupported".into()),
    }
}

fn project_observed(raw: VenuePortfolioRaw) -> Result<CohortVenuePortfolio, String> {
    if raw.technical_issue.is_some() {
        return Err("observed venue portfolio cannot contain a technical issue".into());
    }
    let portfolio = required_number(raw.portfolio_value_usd, "portfolio total")?;
    let collateral = required_number(raw.execution_collateral_value_usd, "execution collateral")?;
    let spot = required_number(raw.non_usdc_spot_value_usd, "non-USDC spot value")?;
    let vault = required_number(raw.vault_equity_usd, "vault equity")?;
    if !near(portfolio, collateral + spot + vault) {
        return Err("venue portfolio total does not reconcile to its components".into());
    }
    let assets = raw
        .valued_spot_assets
        .ok_or_else(|| "venue portfolio is missing valued spot assets".to_string())?;
    validate_assets(&assets, collateral, spot)?;
    let observed_at = required_text(raw.observed_at_utc, "venue portfolio timestamp")?;
    DateTime::parse_from_rfc3339(&observed_at)
        .map_err(|error| format!("invalid venue portfolio timestamp: {error}"))?;
    let source = required_text(raw.valuation_source, "venue portfolio source")?;
    if source != "spot_midpoints_plus_vault_equity" {
        return Err("venue portfolio valuation source is unsupported".into());
    }
    Ok(CohortVenuePortfolio {
        portfolio_value_usd: portfolio,
        execution_collateral_value_usd: collateral,
        non_usdc_spot_value_usd: spot,
        vault_equity_usd: vault,
        valued_spot_assets: assets,
        observed_at_utc: observed_at,
        valuation_source: source,
    })
}

fn validate_contract(value: &VenuePortfolioContract) -> Result<(), String> {
    if !value.report_only
        || value.execution_authority != "none"
        || !value.execution_collateral_unchanged
    {
        return Err("venue portfolio contract claims execution authority".into());
    }
    Ok(())
}

fn validate_assets(
    assets: &[CohortValuedSpotAsset],
    collateral: f64,
    non_usdc: f64,
) -> Result<(), String> {
    if assets.is_empty() || assets.iter().any(invalid_asset) {
        return Err("venue portfolio valued spot assets are invalid".into());
    }
    let usdc: Vec<&CohortValuedSpotAsset> = assets
        .iter()
        .filter(|asset| asset.token_index == 0 && asset.symbol == "USDC")
        .collect();
    let other = assets
        .iter()
        .filter(|asset| asset.token_index != 0)
        .map(|asset| asset.value_usd)
        .sum::<f64>();
    if usdc.len() != 1 || !near(usdc[0].value_usd, collateral) || !near(other, non_usdc) {
        return Err("venue portfolio spot assets do not reconcile".into());
    }
    Ok(())
}

fn invalid_asset(value: &CohortValuedSpotAsset) -> bool {
    value.symbol.trim().is_empty()
        || value.market.trim().is_empty()
        || !nonnegative(value.total)
        || !positive(value.price_usd)
        || !nonnegative(value.value_usd)
        || !near(value.value_usd, value.total * value.price_usd)
}

fn unavailable_issue(raw: VenuePortfolioRaw) -> Result<String, String> {
    if raw.portfolio_value_usd.is_some()
        || raw.execution_collateral_value_usd.is_some()
        || raw.non_usdc_spot_value_usd.is_some()
        || raw.vault_equity_usd.is_some()
        || raw.valued_spot_assets.is_some()
        || raw.observed_at_utc.is_some()
        || raw.valuation_source.is_some()
    {
        return Err("unavailable venue portfolio contains success-shaped values".into());
    }
    required_text(raw.technical_issue, "venue portfolio technical issue")
}

fn required_number(value: Option<f64>, label: &str) -> Result<f64, String> {
    let number = value.ok_or_else(|| format!("venue portfolio is missing {label}"))?;
    if !nonnegative(number) {
        return Err(format!(
            "venue portfolio {label} must be nonnegative and finite"
        ));
    }
    Ok(number)
}

fn required_text(value: Option<String>, label: &str) -> Result<String, String> {
    let text = value.ok_or_else(|| format!("{label} is missing"))?;
    if text.trim().is_empty() {
        return Err(format!("{label} must be non-empty"));
    }
    Ok(text)
}

fn near(left: f64, right: f64) -> bool {
    (left - right).abs() <= 1e-6_f64.max(right.abs() * 1e-9)
}

fn nonnegative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn positive(value: f64) -> bool {
    value.is_finite() && value > 0.0
}
