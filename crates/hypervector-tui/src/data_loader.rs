//! Data loader and synthesizer for real-time and historical playback snapshots.

use serde_json::Value;
use std::fs;
use std::path::Path;

use crate::model::{RegimeSnapshot, RegimeState};

pub fn load_snapshots_with_metadata(
    args: &crate::cli_args::CliArgs,
) -> (Vec<RegimeSnapshot>, bool) {
    if let Some(ref path) = args.file
        && path.exists()
    {
        let snaps = load_snapshots_from_file(path);
        return (snaps, false);
    }

    // Check data_root for real cached aligned data snapshots
    let cache_candidates = [
        args.data_root.join("exports").join("regime_snapshots.json"),
        args.data_root
            .join("cache")
            .join("aligned")
            .join(format!("{}_aligned_latest.json", args.symbol)),
    ];

    for candidate in &cache_candidates {
        if candidate.exists() {
            let snaps = load_snapshots_from_file(candidate);
            if !snaps.is_empty() {
                return (snaps, false);
            }
        }
    }

    // Default to empty real snapshot array (NO synthetic demo fallback)
    (Vec::new(), false)
}

pub fn load_snapshots_from_file(path: &Path) -> Vec<RegimeSnapshot> {
    if !path.exists() {
        return Vec::new();
    }

    if let Ok(content) = fs::read_to_string(path) {
        let json_res: Result<Value, _> = serde_json::from_str(&content);
        if let Ok(json) = json_res
            && let Some(arr) = json.as_array()
        {
            let mut out = Vec::new();
            for (idx, item) in arr.iter().enumerate() {
                if let Some(snap) = parse_snapshot_json(item, idx) {
                    out.push(snap);
                }
            }
            if !out.is_empty() {
                return out;
            }
        }
    }

    Vec::new()
}

pub fn get_today_date_str() -> String {
    chrono::Local::now().format("%Y-%m-%d").to_string()
}

struct SnapshotCore {
    timestamp_str: String,
    timestamp_ms: u64,
    price: f64,
    high: f64,
    low: f64,
    volume: f64,
    state: RegimeState,
}

pub fn parse_snapshot_json(val: &Value, _idx: usize) -> Option<RegimeSnapshot> {
    Some(snapshot_from_json(val, parse_snapshot_core(val)?))
}

fn parse_snapshot_core(val: &Value) -> Option<SnapshotCore> {
    let price = number(val, "close").or_else(|| number(val, "price"))?;
    let state = parse_regime_state(val.get("regime_state")?.as_str()?)?;
    Some(SnapshotCore {
        timestamp_str: normalized_timestamp(val)?,
        timestamp_ms: val
            .get("timestamp_ms")
            .and_then(Value::as_u64)
            .filter(|&milliseconds| milliseconds > 0)
            .unwrap_or(0),
        price,
        high: number(val, "high")?,
        low: number(val, "low")?,
        volume: number(val, "volume")?,
        state,
    })
}

fn parse_regime_state(value: &str) -> Option<RegimeState> {
    Some(match value {
        "TREND_UP" => RegimeState::BullMomentum,
        "TREND_DOWN" => RegimeState::BearMomentum,
        "BREAKOUT" => RegimeState::VolatilityCoiling,
        "TRANSITION" => RegimeState::FundingCarry,
        "RANGE" => RegimeState::RangeChop,
        "UNKNOWN" => RegimeState::Unknown,
        _ => return None,
    })
}

fn normalized_timestamp(val: &Value) -> Option<String> {
    let today = get_today_date_str();
    let raw_timestamp = text(val, "timestamp_str")
        .or_else(|| text(val, "timestamp"))
        .or_else(|| text(val, "time"))
        .or_else(|| text(val, "datetime"));
    Some(match raw_timestamp {
        Some(s) if !s.contains("1969-12-31") && !s.contains("1970-01-01") => s,
        Some(s) => s
            .replace("1969-12-31", &today)
            .replace("1970-01-01", &today),
        None => return None,
    })
}

fn snapshot_from_json(val: &Value, core: SnapshotCore) -> RegimeSnapshot {
    RegimeSnapshot {
        timestamp_str: core.timestamp_str,
        timestamp_ms: core.timestamp_ms,
        price: core.price,
        open: number(val, "open"),
        high: core.high,
        low: core.low,
        volume: core.volume,
        state: core.state,
        regime_reason: text(val, "regime_reason").unwrap_or_else(|| "snapshot_file".into()),
        confidence: number(val, "regime_strength_score")
            .or_else(|| number(val, "confidence"))
            .unwrap_or(0.0),
        regime_score_source: text(val, "regime_score_source")
            .unwrap_or_else(|| "legacy_confidence_alias".into()),
        source_diagnostics: None,
        opi: number(val, "opi").unwrap_or(0.0),
        spread_bps: number(val, "spread_bps").unwrap_or(0.0),
        bid_depth_ratio: number(val, "bid_depth_ratio").unwrap_or(0.0),
        microstructure_source: text(val, "microstructure_source")
            .unwrap_or_else(|| "not_available".into()),
        bbwp_percentile: number(val, "bbwp_percentile").unwrap_or(0.0),
        rsi: number(val, "rsi").unwrap_or(0.0),
        funding_zscore: number(val, "funding_zscore").unwrap_or(0.0),
        funding_source: text(val, "funding_source").unwrap_or_else(|| "not_available".into()),
        trend_1m: text(val, "trend_1m").unwrap_or_else(|| "UNKNOWN".into()),
        trend_5m: text(val, "trend_5m").unwrap_or_else(|| "UNKNOWN".into()),
        trend_15m: text(val, "trend_15m").unwrap_or_else(|| "UNKNOWN".into()),
        long_weight: number(val, "long_weight").unwrap_or(0.0),
        short_weight: number(val, "short_weight").unwrap_or(0.0),
        max_leverage: number(val, "max_leverage").unwrap_or(0.0),
        dynamic_leverage: number(val, "dynamic_leverage").unwrap_or(0.0),
        taker_allowed: val
            .get("taker_allowed")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    }
}

fn number(val: &Value, key: &str) -> Option<f64> {
    val.get(key).and_then(Value::as_f64)
}

fn text(val: &Value, key: &str) -> Option<String> {
    val.get(key).and_then(Value::as_str).map(str::to_string)
}

#[derive(Clone, Copy)]
struct SyntheticMetrics {
    opi: f64,
    spread: f64,
    depth_ratio: f64,
    bbwp: f64,
    rsi: f64,
    zscore: f64,
    trend_1m: &'static str,
    trend_5m: &'static str,
    trend_15m: &'static str,
    long_weight: f64,
    short_weight: f64,
    leverage: f64,
    taker_allowed: bool,
}

const BULL_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: 0.42,
    spread: 1.6,
    depth_ratio: 1.65,
    bbwp: 48.0,
    rsi: 64.5,
    zscore: 0.4,
    trend_1m: "BULL",
    trend_5m: "BULL",
    trend_15m: "BULL",
    long_weight: 2.0,
    short_weight: 0.0,
    leverage: 3.0,
    taker_allowed: false,
};

const BEAR_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: -0.38,
    spread: 1.9,
    depth_ratio: 0.62,
    bbwp: 52.0,
    rsi: 38.0,
    zscore: -0.3,
    trend_1m: "BEAR",
    trend_5m: "BEAR",
    trend_15m: "BEAR",
    long_weight: 0.0,
    short_weight: 2.0,
    leverage: 3.0,
    taker_allowed: false,
};

const COILING_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: 0.05,
    spread: 1.4,
    depth_ratio: 1.10,
    bbwp: 14.5,
    rsi: 51.0,
    zscore: 0.1,
    trend_1m: "NEUTRAL",
    trend_5m: "BULL",
    trend_15m: "NEUTRAL",
    long_weight: 1.5,
    short_weight: 0.0,
    leverage: 2.5,
    taker_allowed: false,
};

const CARRY_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: 0.12,
    spread: 1.5,
    depth_ratio: 1.25,
    bbwp: 38.0,
    rsi: 44.0,
    zscore: -2.15,
    trend_1m: "BULL",
    trend_5m: "BEAR",
    trend_15m: "BEAR",
    long_weight: 2.0,
    short_weight: 0.0,
    leverage: 3.0,
    taker_allowed: false,
};

const RANGE_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: -0.02,
    spread: 5.2,
    depth_ratio: 0.95,
    bbwp: 68.0,
    rsi: 49.0,
    zscore: 0.0,
    trend_1m: "NEUTRAL",
    trend_5m: "NEUTRAL",
    trend_15m: "NEUTRAL",
    long_weight: 0.0,
    short_weight: 0.0,
    leverage: 1.0,
    taker_allowed: false,
};

const UNKNOWN_METRICS: SyntheticMetrics = SyntheticMetrics {
    opi: 0.0,
    spread: 0.0,
    depth_ratio: 0.0,
    bbwp: 0.0,
    rsi: 0.0,
    zscore: 0.0,
    trend_1m: "UNKNOWN",
    trend_5m: "UNKNOWN",
    trend_15m: "UNKNOWN",
    long_weight: 0.0,
    short_weight: 0.0,
    leverage: 0.0,
    taker_allowed: false,
};

pub fn generate_synthetic_history(count: usize) -> Vec<RegimeSnapshot> {
    let mut snapshots = Vec::with_capacity(count);
    let mut base_px = 65200.0;
    let states = [
        RegimeState::BullMomentum,
        RegimeState::BullMomentum,
        RegimeState::VolatilityCoiling,
        RegimeState::RangeChop,
        RegimeState::BearMomentum,
        RegimeState::FundingCarry,
    ];
    let today = get_today_date_str();
    for i in 0..count {
        let phase = (i / 30) % states.len();
        let state = states[phase];
        let price = advance_synthetic_price(&mut base_px, state, i);
        let metrics = synthetic_metrics(state);
        let leverage = synthetic_dynamic_leverage(state, metrics);
        snapshots.push(synthetic_snapshot(
            i, &today, price, state, metrics, leverage,
        ));
    }
    snapshots
}

fn advance_synthetic_price(base_price: &mut f64, state: RegimeState, index: usize) -> f64 {
    let noise = ((index as f64 * 0.1).sin() * 15.0) + ((index as f64 * 0.3).cos() * 8.0);
    match state {
        RegimeState::BullMomentum => *base_price += 4.5 + (index % 3) as f64 * 1.2,
        RegimeState::BearMomentum => *base_price -= 4.2 + (index % 3) as f64 * 1.1,
        RegimeState::VolatilityCoiling => *base_price += (index % 2) as f64 * 0.5 - 0.25,
        RegimeState::Unknown => {}
        _ => *base_price += (index % 5) as f64 * 1.0 - 2.0,
    }
    *base_price + noise
}

fn synthetic_metrics(state: RegimeState) -> SyntheticMetrics {
    match state {
        RegimeState::BullMomentum => BULL_METRICS,
        RegimeState::BearMomentum => BEAR_METRICS,
        RegimeState::VolatilityCoiling => COILING_METRICS,
        RegimeState::FundingCarry => CARRY_METRICS,
        RegimeState::RangeChop => RANGE_METRICS,
        RegimeState::Unknown => UNKNOWN_METRICS,
    }
}

fn synthetic_dynamic_leverage(state: RegimeState, metrics: SyntheticMetrics) -> f64 {
    match state {
        RegimeState::BullMomentum | RegimeState::BearMomentum => {
            (2.0 * (1.0 + metrics.opi.abs() * 0.5)).clamp(1.0, metrics.leverage)
        }
        RegimeState::VolatilityCoiling => {
            (1.5 * (1.0 + (20.0 - metrics.bbwp) / 20.0)).clamp(1.0, metrics.leverage)
        }
        RegimeState::FundingCarry => {
            (3.0 * (metrics.zscore.abs() / 2.0)).clamp(1.0, metrics.leverage)
        }
        RegimeState::RangeChop => 1.0,
        RegimeState::Unknown => 0.0,
    }
}

fn synthetic_snapshot(
    index: usize,
    today: &str,
    price: f64,
    state: RegimeState,
    metrics: SyntheticMetrics,
    dynamic_leverage: f64,
) -> RegimeSnapshot {
    RegimeSnapshot {
        timestamp_str: format!("{} {:02}:{:02}:00", today, (index / 60) % 24, index % 60),
        timestamp_ms: 1784850000000 + (index as u64 * 60000),
        price,
        open: Some(price),
        high: price + 25.0,
        low: price - 25.0,
        volume: 18.4 + (index % 7) as f64 * 2.1,
        state,
        regime_reason: "synthetic_fixture".to_string(),
        confidence: 0.88 + ((index % 10) as f64 * 0.01),
        regime_score_source: "synthetic_fixture".into(),
        source_diagnostics: None,
        opi: metrics.opi,
        spread_bps: metrics.spread,
        bid_depth_ratio: metrics.depth_ratio,
        microstructure_source: "synthetic_fixture".into(),
        bbwp_percentile: metrics.bbwp,
        rsi: metrics.rsi,
        funding_zscore: metrics.zscore,
        funding_source: "synthetic_fixture".into(),
        trend_1m: metrics.trend_1m.into(),
        trend_5m: metrics.trend_5m.into(),
        trend_15m: metrics.trend_15m.into(),
        long_weight: metrics.long_weight,
        short_weight: metrics.short_weight,
        max_leverage: metrics.leverage,
        dynamic_leverage: (dynamic_leverage * 100.0).round() / 100.0,
        taker_allowed: metrics.taker_allowed,
    }
}
