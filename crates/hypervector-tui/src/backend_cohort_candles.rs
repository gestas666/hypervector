//! Strict completed-candle history projection for cohort telemetry.

use std::collections::BTreeMap;

use serde::Deserialize;
use serde_json::Value;

use crate::backend_cohort::CohortCandle;
use crate::backend_telemetry::LedgerRow;

#[derive(Debug, Clone, Deserialize)]
struct CohortMarketCandlesPayload {
    timeframe: String,
    bars: BTreeMap<String, Vec<CohortCandle>>,
}

pub(crate) fn candle_history(
    rows: &[&LedgerRow],
    symbols: &[String],
) -> Result<BTreeMap<String, Vec<CohortCandle>>, String> {
    let mut history = BTreeMap::new();
    let mut first_window = true;
    for row in rows.iter().filter(|row| row.action == "market_candles") {
        let payload: CohortMarketCandlesPayload = parse_payload(row)?;
        validate_window(&payload, symbols, first_window)?;
        first_window = false;
        for (symbol, candles) in payload.bars {
            if !symbols.contains(&symbol) || candles.is_empty() {
                return Err("cohort market candles carry invalid symbols or bars".into());
            }
            append_candles(history.entry(symbol).or_default(), candles)?;
        }
    }
    for candles in history.values_mut() {
        retain_tail(candles, 360);
    }
    Ok(history)
}

fn validate_window(
    payload: &CohortMarketCandlesPayload,
    symbols: &[String],
    first_window: bool,
) -> Result<(), String> {
    if payload.timeframe != "1m" || payload.bars.is_empty() {
        return Err("cohort market candles require non-empty 1m bars".into());
    }
    let complete = payload.bars.len() == symbols.len()
        && symbols
            .iter()
            .all(|symbol| payload.bars.contains_key(symbol));
    if first_window && !complete {
        return Err("cohort initial candle window must cover every symbol".into());
    }
    Ok(())
}

fn append_candles(
    history: &mut Vec<CohortCandle>,
    candles: Vec<CohortCandle>,
) -> Result<(), String> {
    for candle in candles {
        validate_candle(&candle)?;
        if history
            .last()
            .is_some_and(|prior| candle.timestamp_ms <= prior.timestamp_ms)
        {
            return Err("cohort candle timestamps must be strictly increasing".into());
        }
        history.push(candle);
    }
    Ok(())
}

fn validate_candle(candle: &CohortCandle) -> Result<(), String> {
    let prices = [candle.open, candle.high, candle.low, candle.close];
    let invalid = candle.timestamp_ms == 0
        || prices
            .iter()
            .any(|price| !price.is_finite() || *price <= 0.0)
        || !candle.volume.is_finite()
        || candle.volume < 0.0
        || candle.low > candle.high
        || candle.high < candle.open.max(candle.close)
        || candle.low > candle.open.min(candle.close);
    if invalid {
        return Err("cohort candle contains invalid OHLCV".into());
    }
    Ok(())
}

fn retain_tail<T>(values: &mut Vec<T>, maximum: usize) {
    if values.len() > maximum {
        values.drain(..values.len() - maximum);
    }
}

fn parse_payload<T: for<'de> Deserialize<'de>>(row: &LedgerRow) -> Result<T, String> {
    let values = row.extra.clone().into_iter().collect();
    serde_json::from_value(Value::Object(values))
        .map_err(|error| format!("invalid {} payload: {error}", row.action))
}
