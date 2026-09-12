use super::{CohortCandle, MINUTE_MS, decision_timeframe_candles};

fn minutes(count: u32) -> Vec<CohortCandle> {
    (0..count)
        .map(|minute| CohortCandle {
            timestamp_ms: u64::from(minute) * MINUTE_MS,
            open: 100.0 + f64::from(minute),
            high: 102.0 + f64::from(minute),
            low: 99.0 + f64::from(minute),
            close: 101.0 + f64::from(minute),
            volume: f64::from(minute + 1),
        })
        .collect()
}

#[test]
fn hourly_chart_aggregates_exact_completed_ohlcv() {
    let bars = decision_timeframe_candles(&minutes(120), "1h").expect("configured hour");
    assert_eq!(bars.len(), 2);
    let first = &bars[0];
    assert_eq!(first.timestamp_ms, 0);
    assert_eq!(
        (first.open, first.high, first.low, first.close),
        (100.0, 161.0, 99.0, 160.0)
    );
    assert_eq!(first.volume, 1830.0);
    assert_eq!(bars[1].timestamp_ms, 3_600_000);
    assert_eq!(bars[1].close, 220.0);
    assert_eq!(bars[1].volume, 5430.0);
}

#[test]
fn hourly_chart_excludes_partial_edges_and_internal_gaps() {
    let mut source = minutes(150);
    source.drain(..5);
    let bars = decision_timeframe_candles(&source, "1h").expect("configured hour");
    assert_eq!(bars.len(), 1);
    assert_eq!(bars[0].timestamp_ms, 3_600_000);
    source.retain(|bar| bar.timestamp_ms != 90 * MINUTE_MS);
    assert!(
        decision_timeframe_candles(&source, "1h")
            .expect("gapped hour")
            .is_empty()
    );
}

#[test]
fn hourly_chart_keeps_unsupported_intervals_explicit() {
    for timeframe in ["0h", "2h", "60m", "1d", "", "0m"] {
        let error = decision_timeframe_candles(&minutes(120), timeframe).expect_err("unsupported");
        assert!(error.contains("UNSUPPORTED DECISION TIMEFRAME"));
    }
}
