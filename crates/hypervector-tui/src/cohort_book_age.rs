//! Explicit clock evidence for a retained backend book, without freshness gates.

const MILLIS_PER_SECOND: u64 = 1_000;
const SOURCE_CANDLE_SECONDS: u64 = 60;

pub(crate) fn book_age(exchange_ms: u64, now_ms: i64) -> String {
    timestamp_age("BOOK", exchange_ms, now_ms)
}

/// Report age since the latest backend one-minute candle completed.
pub(crate) fn candle_age(candles: &[crate::backend_cohort::CohortCandle], now_ms: i64) -> String {
    let Some(last) = candles.last() else {
        return "1M CANDLE AGE UNAVAILABLE".into();
    };
    if last.timestamp_ms == 0 {
        return "1M CANDLE AGE UNAVAILABLE".into();
    }
    let Some(closed_at) = last
        .timestamp_ms
        .checked_add(SOURCE_CANDLE_SECONDS * MILLIS_PER_SECOND)
    else {
        return "1M CANDLE AGE INVALID".into();
    };
    timestamp_age("1M CANDLE", closed_at, now_ms)
}

fn timestamp_age(label: &str, exchange_ms: u64, now_ms: i64) -> String {
    if exchange_ms == 0 {
        return format!("{label} AGE UNAVAILABLE");
    }
    let Ok(exchange) = i64::try_from(exchange_ms) else {
        return format!("{label} AGE INVALID");
    };
    if now_ms <= 0 {
        return format!("{label} AGE CLOCK INVALID");
    }
    if exchange > now_ms {
        return format!("{label} AGE FUTURE {}", seconds(exchange.abs_diff(now_ms)));
    }
    format!("{label} AGE {}", seconds(exchange.abs_diff(now_ms)))
}

pub(crate) fn receive_delay(receive_ms: u64, exchange_ms: u64) -> String {
    if receive_ms == 0 || exchange_ms == 0 {
        return "UNAVAILABLE".into();
    }
    if receive_ms < exchange_ms {
        return format!("CLOCK SKEW -{}ms", exchange_ms - receive_ms);
    }
    format!("{}ms", receive_ms - exchange_ms)
}

fn seconds(milliseconds: u64) -> String {
    format!(
        "{}.{:03}s",
        milliseconds / MILLIS_PER_SECOND,
        milliseconds % MILLIS_PER_SECOND,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candle(timestamp_ms: u64) -> crate::backend_cohort::CohortCandle {
        crate::backend_cohort::CohortCandle {
            timestamp_ms,
            open: 100.0,
            high: 101.0,
            low: 99.0,
            close: 100.0,
            volume: 1.0,
        }
    }

    #[test]
    fn candle_age_starts_at_close_and_keeps_source_clock_failures_explicit() {
        assert_eq!(
            candle_age(&[candle(101_000)], 165_001),
            "1M CANDLE AGE 4.001s"
        );
        assert_eq!(
            candle_age(&[candle(101_000)], 160_000),
            "1M CANDLE AGE FUTURE 1.000s"
        );
        assert_eq!(candle_age(&[], 165_001), "1M CANDLE AGE UNAVAILABLE");
        assert_eq!(
            candle_age(&[candle(0)], 165_001),
            "1M CANDLE AGE UNAVAILABLE"
        );
        assert_eq!(
            candle_age(&[candle(u64::MAX)], 165_001),
            "1M CANDLE AGE INVALID"
        );
        assert_eq!(
            candle_age(&[candle(101_000)], 0),
            "1M CANDLE AGE CLOCK INVALID"
        );
    }

    #[test]
    fn age_keeps_elapsed_milliseconds_and_does_not_claim_freshness() {
        assert_eq!(book_age(1_000, 1_000), "BOOK AGE 0.000s");
        assert_eq!(book_age(1_000, 3_374), "BOOK AGE 2.374s");
        assert_eq!(book_age(1_000, 518_401_001), "BOOK AGE 518400.001s");
    }

    #[test]
    fn future_missing_and_invalid_clocks_remain_explicit() {
        assert_eq!(book_age(1_001, 1_000), "BOOK AGE FUTURE 0.001s");
        assert_eq!(book_age(0, 1_000), "BOOK AGE UNAVAILABLE");
        assert_eq!(book_age(u64::MAX, 1_000), "BOOK AGE INVALID");
        for now in [0, -1, i64::MIN] {
            assert_eq!(book_age(1_000, now), "BOOK AGE CLOCK INVALID");
        }
    }

    #[test]
    fn transport_delay_retains_negative_clock_evidence() {
        assert_eq!(receive_delay(3_374, 1_000), "2374ms");
        assert_eq!(receive_delay(1_000, 1_000), "0ms");
        assert_eq!(receive_delay(1_000, 1_001), "CLOCK SKEW -1ms");
        assert_eq!(receive_delay(0, 1_000), "UNAVAILABLE");
        assert_eq!(receive_delay(1_000, 0), "UNAVAILABLE");
    }
}
