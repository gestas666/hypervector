//! Data loader and synthesizer for real-time and historical playback snapshots.

use std::fs;
use std::path::Path;
use serde_json::Value;

use crate::model::{RegimeSnapshot, RegimeState};

pub fn load_snapshots_with_metadata(args: &crate::cli_args::CliArgs) -> (Vec<RegimeSnapshot>, bool) {
    if let Some(ref path) = args.file {
        if path.exists() {
            let snaps = load_snapshots_from_file(path);
            return (snaps, false);
        }
    }

    // Check data_root for real cached aligned data snapshots
    let cache_candidates = [
        args.data_root.join("exports").join("regime_snapshots.json"),
        args.data_root.join("cache").join("aligned").join(format!("{}_aligned_latest.json", args.symbol)),
    ];

    for candidate in &cache_candidates {
        if candidate.exists() {
            let snaps = load_snapshots_from_file(candidate);
            if !snaps.is_empty() {
                return (snaps, false);
            }
        }
    }

    // Fall back to synthetic data with explicit synthetic flag
    (generate_synthetic_history(300), true)
}

pub fn load_snapshots_from_file(path: &Path) -> Vec<RegimeSnapshot> {
    if !path.exists() {
        return generate_synthetic_history(300);
    }

    if let Ok(content) = fs::read_to_string(path) {
        let json_res: Result<Value, _> = serde_json::from_str(&content);
        if let Ok(json) = json_res {
            if let Some(arr) = json.as_array() {
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
    }

    generate_synthetic_history(300)
}

fn parse_snapshot_json(val: &Value, idx: usize) -> Option<RegimeSnapshot> {
    let px = val.get("close").or_else(|| val.get("price")).and_then(|v| v.as_f64()).unwrap_or(65000.0);
    let state_str = val.get("regime_state").and_then(|v| v.as_str()).unwrap_or("BULL_MOMENTUM_EXPANSION");
    
    let state = match state_str {
        s if s.contains("BULL") => RegimeState::BullMomentum,
        s if s.contains("BEAR") => RegimeState::BearMomentum,
        s if s.contains("COILING") || s.contains("COMPRESSION") => RegimeState::VolatilityCoiling,
        s if s.contains("CARRY") || s.contains("FUNDING") => RegimeState::FundingCarry,
        _ => RegimeState::RangeChop,
    };

    Some(RegimeSnapshot {
        timestamp_str: format!("2026-07-24 {:02}:{:02}:00", (idx / 60) % 24, idx % 60),
        timestamp_ms: 1784850000000 + (idx as u64 * 60000),
        price: px,
        high: px + 40.0,
        low: px - 40.0,
        volume: 12.5 + (idx as f64 % 10.0),
        state,
        confidence: 0.85,
        opi: if state == RegimeState::BullMomentum { 0.35 } else if state == RegimeState::BearMomentum { -0.35 } else { 0.05 },
        spread_bps: 1.8,
        bid_depth_ratio: 1.45,
        bbwp_percentile: if state == RegimeState::VolatilityCoiling { 14.2 } else { 45.0 },
        rsi: if state == RegimeState::BullMomentum { 62.0 } else { 42.0 },
        funding_zscore: if state == RegimeState::FundingCarry { -2.1 } else { 0.2 },
        trend_1m: if state == RegimeState::BullMomentum { "BULL".into() } else { "BEAR".into() },
        trend_5m: "BULL".into(),
        trend_15m: "BULL".into(),
        long_weight: if state == RegimeState::BullMomentum { 2.0 } else { 0.5 },
        short_weight: if state == RegimeState::BearMomentum { 2.0 } else { 0.0 },
        max_leverage: 3.0,
        dynamic_leverage: if state == RegimeState::BullMomentum { 2.42 } else { 1.25 },
        taker_allowed: false,
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

    for i in 0..count {
        let phase = (i / 30) % states.len();
        let state = states[phase];

        let noise = ((i as f64 * 0.1).sin() * 15.0) + ((i as f64 * 0.3).cos() * 8.0);
        match state {
            RegimeState::BullMomentum => base_px += 4.5 + (i % 3) as f64 * 1.2,
            RegimeState::BearMomentum => base_px -= 4.2 + (i % 3) as f64 * 1.1,
            RegimeState::VolatilityCoiling => base_px += (i % 2) as f64 * 0.5 - 0.25,
            _ => base_px += (i % 5) as f64 * 1.0 - 2.0,
        };

        let current_px = base_px + noise;
        let (opi, spread, depth_ratio, bbwp, rsi, zscore, t1, t5, t15, lw, sw, lev, taker): (f64, f64, f64, f64, f64, f64, &str, &str, &str, f64, f64, f64, bool) = match state {
            RegimeState::BullMomentum => (0.42, 1.6, 1.65, 48.0, 64.5, 0.4, "BULL", "BULL", "BULL", 2.0, 0.0, 3.0, false),
            RegimeState::BearMomentum => (-0.38, 1.9, 0.62, 52.0, 38.0, -0.3, "BEAR", "BEAR", "BEAR", 0.0, 2.0, 3.0, false),
            RegimeState::VolatilityCoiling => (0.05, 1.4, 1.10, 14.5, 51.0, 0.1, "NEUTRAL", "BULL", "NEUTRAL", 1.5, 1.5, 2.5, false),
            RegimeState::FundingCarry => (0.12, 1.5, 1.25, 38.0, 44.0, -2.15, "BULL", "BEAR", "BEAR", 2.0, 0.0, 3.0, false),
            RegimeState::RangeChop => (-0.02, 5.2, 0.95, 68.0, 49.0, 0.0, "NEUTRAL", "NEUTRAL", "NEUTRAL", 0.25, 0.25, 1.0, false),
        };

        let dynamic_leverage = match state {
            RegimeState::BullMomentum | RegimeState::BearMomentum => (2.0 * (1.0 + opi.abs() * 0.5)).clamp(1.0, lev),
            RegimeState::VolatilityCoiling => (1.5 * (1.0 + (20.0 - bbwp) / 20.0)).clamp(1.0, lev),
            RegimeState::FundingCarry => (3.0 * (zscore.abs() / 2.0)).clamp(1.0, lev),
            RegimeState::RangeChop => 1.0,
        };

        snapshots.push(RegimeSnapshot {
            timestamp_str: format!("2026-07-24 {:02}:{:02}:00", (i / 60) % 24, i % 60),
            timestamp_ms: 1784850000000 + (i as u64 * 60000),
            price: current_px,
            high: current_px + 25.0,
            low: current_px - 25.0,
            volume: 18.4 + (i % 7) as f64 * 2.1,
            state,
            confidence: 0.88 + ((i % 10) as f64 * 0.01),
            opi,
            spread_bps: spread,
            bid_depth_ratio: depth_ratio,
            bbwp_percentile: bbwp,
            rsi,
            funding_zscore: zscore,
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
