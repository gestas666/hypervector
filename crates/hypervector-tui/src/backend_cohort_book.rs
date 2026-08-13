//! Strict projection of backend-authored Hyperliquid L2 snapshots.

use std::collections::BTreeMap;

use serde::Deserialize;
use serde_json::Value;

use crate::backend_telemetry::LedgerRow;

/// One exact aggregated price level from the backend venue reader.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortBookLevel {
    pub price: f64,
    pub size: f64,
    #[serde(default)]
    pub orders: Option<u64>,
}

/// Latest complete venue book and directly derived order-flow metrics.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct CohortBookSnapshot {
    pub symbol: String,
    pub source: String,
    pub exchange_ts_ms: u64,
    pub recv_ts_ms: u64,
    pub mid_px: f64,
    pub spread_bps: f64,
    pub bid_depth_ratio: f64,
    pub opi: f64,
    pub bids: Vec<CohortBookLevel>,
    pub asks: Vec<CohortBookLevel>,
}

#[derive(Debug, Deserialize)]
struct MarketBooksPayload {
    books: BTreeMap<String, CohortBookSnapshot>,
}

#[derive(Debug, Deserialize)]
struct SnapshotBooksPayload {
    #[serde(default)]
    books: Vec<CohortBookSnapshot>,
}

pub(crate) fn project_books(
    rows: &[&LedgerRow],
    symbols: &[String],
) -> Result<BTreeMap<String, CohortBookSnapshot>, String> {
    let mut latest = BTreeMap::new();
    for row in rows {
        match row.action.as_str() {
            "market_books" => apply_market_row(row, symbols, &mut latest)?,
            "cohort_snapshot" => apply_snapshot_row(row, symbols, &mut latest)?,
            _ => {}
        }
    }
    Ok(latest)
}

fn apply_market_row(
    row: &LedgerRow,
    symbols: &[String],
    latest: &mut BTreeMap<String, CohortBookSnapshot>,
) -> Result<(), String> {
    let payload: MarketBooksPayload = parse_payload(row)?;
    if payload.books.len() != symbols.len()
        || symbols
            .iter()
            .any(|symbol| !payload.books.contains_key(symbol))
    {
        return Err("cohort market books must cover every configured symbol".into());
    }
    for (symbol, book) in payload.books {
        if symbol != book.symbol {
            return Err("cohort market book key disagrees with its symbol".into());
        }
        validate_book(&book, symbols)?;
        latest.insert(symbol, book);
    }
    Ok(())
}

fn apply_snapshot_row(
    row: &LedgerRow,
    symbols: &[String],
    latest: &mut BTreeMap<String, CohortBookSnapshot>,
) -> Result<(), String> {
    let payload: SnapshotBooksPayload = parse_payload(row)?;
    for book in payload.books {
        validate_book(&book, symbols)?;
        latest.insert(book.symbol.clone(), book);
    }
    Ok(())
}

fn validate_book(book: &CohortBookSnapshot, symbols: &[String]) -> Result<(), String> {
    let scalars_valid = book.exchange_ts_ms > 0
        && book.recv_ts_ms > 0
        && book.mid_px.is_finite()
        && book.mid_px > 0.0
        && book.spread_bps.is_finite()
        && book.spread_bps >= 0.0
        && book.bid_depth_ratio.is_finite()
        && book.bid_depth_ratio > 0.0
        && book.opi.is_finite()
        && (-1.0..=1.0).contains(&book.opi);
    if !symbols.contains(&book.symbol)
        || book.source != "hyperliquid_mainnet_l2_rest"
        || !scalars_valid
        || book.bids.is_empty()
        || book.asks.is_empty()
        || book.bids.len() > 20
        || book.asks.len() > 20
        || !valid_levels(&book.bids, true)
        || !valid_levels(&book.asks, false)
        || book.bids[0].price >= book.asks[0].price
    {
        return Err("cohort market book is structurally invalid".into());
    }
    let derived_mid = (book.bids[0].price + book.asks[0].price) / 2.0;
    if (derived_mid - book.mid_px).abs() > book.mid_px * 1e-9 {
        return Err("cohort market book midpoint disagrees with top of book".into());
    }
    Ok(())
}

fn valid_levels(levels: &[CohortBookLevel], descending: bool) -> bool {
    levels.iter().all(|level| {
        level.price.is_finite() && level.price > 0.0 && level.size.is_finite() && level.size > 0.0
    }) && levels.windows(2).all(|pair| {
        if descending {
            pair[0].price > pair[1].price
        } else {
            pair[0].price < pair[1].price
        }
    })
}

fn parse_payload<T: for<'de> Deserialize<'de>>(row: &LedgerRow) -> Result<T, String> {
    let values = row.extra.clone().into_iter().collect();
    serde_json::from_value(Value::Object(values))
        .map_err(|error| format!("invalid {} payload: {error}", row.action))
}
