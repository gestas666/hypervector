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

pub fn parse_snapshot_json(val: &Value, _idx: usize) -> Option<RegimeSnapshot> {
    let num = |key: &str| val.get(key).and_then(|v| v.as_f64());
    let text = |key: &str| val.get(key).and_then(|v| v.as_str()).map(|s| s.to_string());

    let px = num("close").or_else(|| num("price"))?;
    let state_str = val.get("regime_state").and_then(|v| v.as_str())?;

    let state = match state_str {
        "TREND_UP" => RegimeState::BullMomentum,
        "TREND_DOWN" => RegimeState::BearMomentum,
        "BREAKOUT" => RegimeState::VolatilityCoiling,
        "TRANSITION" => RegimeState::FundingCarry,
        "RANGE" => RegimeState::RangeChop,
        "UNKNOWN" => RegimeState::Unknown,
        _ => return None,
    };

    let today = get_today_date_str();
    let raw_ts = text("timestamp_str")
        .or_else(|| text("timestamp"))
        .or_else(|| text("time"))
        .or_else(|| text("datetime"));

    let timestamp_str = match raw_ts {
        Some(s) if !s.contains("1969-12-31") && !s.contains("1970-01-01") => s,
        Some(s) => s
            .replace("1969-12-31", &today)
            .replace("1970-01-01", &today),
        None => return None,
    };

    let timestamp_ms = val
        .get("timestamp_ms")
        .and_then(|v| v.as_u64())
        .filter(|&ms| ms > 0)
        .unwrap_or(0);

    let high = num("high")?;
    let low = num("low")?;
    let volume = num("volume")?;

    Some(RegimeSnapshot {
        timestamp_str,
        timestamp_ms,
        price: px,
        high,
        low,
        volume,
        state,
        regime_reason: text("regime_reason").unwrap_or_else(|| "snapshot_file".into()),
        confidence: num("regime_strength_score")
            .or_else(|| num("confidence"))
            .unwrap_or(0.0),
        regime_score_source: text("regime_score_source")
            .unwrap_or_else(|| "legacy_confidence_alias".into()),
        opi: num("opi").unwrap_or(0.0),
        spread_bps: num("spread_bps").unwrap_or(0.0),
        bid_depth_ratio: num("bid_depth_ratio").unwrap_or(0.0),
        microstructure_source: text("microstructure_source")
            .unwrap_or_else(|| "not_available".into()),
        bbwp_percentile: num("bbwp_percentile").unwrap_or(0.0),
        rsi: num("rsi").unwrap_or(0.0),
        funding_zscore: num("funding_zscore").unwrap_or(0.0),
        funding_source: text("funding_source").unwrap_or_else(|| "not_available".into()),
        trend_1m: text("trend_1m").unwrap_or_else(|| "UNKNOWN".into()),
        trend_5m: text("trend_5m").unwrap_or_else(|| "UNKNOWN".into()),
        trend_15m: text("trend_15m").unwrap_or_else(|| "UNKNOWN".into()),
        long_weight: num("long_weight").unwrap_or(0.0),
        short_weight: num("short_weight").unwrap_or(0.0),
        max_leverage: num("max_leverage").unwrap_or(0.0),
        dynamic_leverage: num("dynamic_leverage").unwrap_or(0.0),
        taker_allowed: val
            .get("taker_allowed")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
    })
}

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

        let noise = ((i as f64 * 0.1).sin() * 15.0) + ((i as f64 * 0.3).cos() * 8.0);
        match state {
            RegimeState::BullMomentum => base_px += 4.5 + (i % 3) as f64 * 1.2,
            RegimeState::BearMomentum => base_px -= 4.2 + (i % 3) as f64 * 1.1,
            RegimeState::VolatilityCoiling => base_px += (i % 2) as f64 * 0.5 - 0.25,
            RegimeState::Unknown => {}
            _ => base_px += (i % 5) as f64 * 1.0 - 2.0,
        };

        let current_px = base_px + noise;
        let (opi, spread, depth_ratio, bbwp, rsi, zscore, t1, t5, t15, lw, sw, lev, taker) =
            match state {
                RegimeState::BullMomentum => (
                    0.42_f64, 1.6_f64, 1.65_f64, 48.0_f64, 64.5_f64, 0.4_f64, "BULL", "BULL",
                    "BULL", 2.0_f64, 0.0_f64, 3.0_f64, false,
                ),
                RegimeState::BearMomentum => (
                    -0.38, 1.9, 0.62, 52.0, 38.0, -0.3, "BEAR", "BEAR", "BEAR", 0.0, 2.0, 3.0,
                    false,
                ),
                RegimeState::VolatilityCoiling => (
                    0.05, 1.4, 1.10, 14.5, 51.0, 0.1, "NEUTRAL", "BULL", "NEUTRAL", 1.5, 0.0, 2.5,
                    false,
                ),
                RegimeState::FundingCarry => (
                    0.12, 1.5, 1.25, 38.0, 44.0, -2.15, "BULL", "BEAR", "BEAR", 2.0, 0.0, 3.0,
                    false,
                ),
                RegimeState::RangeChop => (
                    -0.02, 5.2, 0.95, 68.0, 49.0, 0.0, "NEUTRAL", "NEUTRAL", "NEUTRAL", 0.0, 0.0,
                    1.0, false,
                ),
                RegimeState::Unknown => (
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "UNKNOWN", "UNKNOWN", "UNKNOWN", 0.0, 0.0, 0.0,
                    false,
                ),
            };

        let dynamic_leverage = match state {
            RegimeState::BullMomentum | RegimeState::BearMomentum => {
                (2.0 * (1.0 + opi.abs() * 0.5)).clamp(1.0, lev)
            }
            RegimeState::VolatilityCoiling => (1.5 * (1.0 + (20.0 - bbwp) / 20.0)).clamp(1.0, lev),
            RegimeState::FundingCarry => (3.0 * (zscore.abs() / 2.0)).clamp(1.0, lev),
            RegimeState::RangeChop => 1.0,
            RegimeState::Unknown => 0.0,
        };

        snapshots.push(RegimeSnapshot {
            timestamp_str: format!("{} {:02}:{:02}:00", today, (i / 60) % 24, i % 60),
            timestamp_ms: 1784850000000 + (i as u64 * 60000),
            price: current_px,
            high: current_px + 25.0,
            low: current_px - 25.0,
            volume: 18.4 + (i % 7) as f64 * 2.1,
            state,
            regime_reason: "synthetic_fixture".to_string(),
            confidence: 0.88 + ((i % 10) as f64 * 0.01),
            regime_score_source: "synthetic_fixture".into(),
            opi,
            spread_bps: spread,
            bid_depth_ratio: depth_ratio,
            microstructure_source: "synthetic_fixture".into(),
            bbwp_percentile: bbwp,
            rsi,
            funding_zscore: zscore,
            funding_source: "synthetic_fixture".into(),
            trend_1m: t1.into(),
            trend_5m: t5.into(),
            trend_15m: t15.into(),
            long_weight: lw,
            short_weight: sw,
            max_leverage: lev,
            dynamic_leverage: (dynamic_leverage * 100.0).round() / 100.0,
            taker_allowed: taker,
        });
    }

    snapshots
}
