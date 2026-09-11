//! Explicit clock evidence for a retained backend book, without freshness gates.

const MILLIS_PER_SECOND: u64 = 1_000;

pub(crate) fn book_age(exchange_ms: u64, now_ms: i64) -> String {
    if exchange_ms == 0 {
        return "BOOK AGE UNAVAILABLE".into();
    }
    let Ok(exchange) = i64::try_from(exchange_ms) else {
        return "BOOK AGE INVALID".into();
    };
    if now_ms <= 0 {
        return "BOOK AGE CLOCK INVALID".into();
    }
    if exchange > now_ms {
        return format!("BOOK AGE FUTURE {}", seconds(exchange.abs_diff(now_ms)));
    }
    format!("BOOK AGE {}", seconds(exchange.abs_diff(now_ms)))
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
