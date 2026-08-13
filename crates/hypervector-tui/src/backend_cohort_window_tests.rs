use serde_json::{Value, json};

use super::*;

fn row(sequence: usize, event_type: &str, payload: Value) -> String {
    json!({
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-03T12:00:00+00:00",
        "run_id": "bounded-run",
        "payload": payload
    })
    .to_string()
}

fn identity() -> String {
    row(
        1,
        "configuration_identity",
        json!({
            "strategy_name": "multi_asset_bidirectional_cohort",
            "enabled_symbols": ["BTC", "ETH", "SOL", "HYPE"]
        }),
    )
}

fn candles(sequence: usize, count: usize) -> String {
    let bars = ["BTC", "ETH", "SOL", "HYPE"]
        .into_iter()
        .map(|symbol| {
            let values = (0..count)
                .map(|offset| {
                    let price = 100.0 + offset as f64;
                    json!({
                        "timestamp_ms": 1_700_000_000_000_u64 + offset as u64 * 60_000,
                        "open": price,
                        "high": price + 1.0,
                        "low": price - 1.0,
                        "close": price + 0.5,
                        "volume": 10.0
                    })
                })
                .collect::<Vec<_>>();
            (symbol.to_string(), Value::Array(values))
        })
        .collect::<serde_json::Map<_, _>>();
    row(
        sequence,
        "market_candles",
        json!({"timeframe": "1m", "bars": bars}),
    )
}

#[test]
fn cohort_window_bounds_repeated_state_and_candles() {
    let mut rows = vec![identity(), candles(2, 400)];
    rows.extend((0..130).map(|index| {
        row(
            index + 3,
            "cohort_snapshot",
            json!({"snapshot_index": index}),
        )
    }));
    let compact = compact_latest_cohort(&rows.join("\n"))
        .expect("valid cohort")
        .expect("cohort projection");
    let values = compact
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).expect("compacted row"))
        .collect::<Vec<_>>();
    let snapshots = values
        .iter()
        .filter(|value| value["event_type"] == "cohort_snapshot")
        .count();
    let candle_row = values
        .iter()
        .find(|value| value["event_type"] == "market_candles")
        .expect("candles retained");

    assert_eq!(snapshots, 90);
    for symbol in ["BTC", "ETH", "SOL", "HYPE"] {
        assert_eq!(
            candle_row["payload"]["bars"][symbol]
                .as_array()
                .unwrap()
                .len(),
            360
        );
    }
}

#[test]
fn recompacting_retained_window_plus_append_matches_full_ledger() {
    let mut initial = vec![identity(), candles(2, 400)];
    initial.extend((0..130).map(|index| {
        row(
            index + 3,
            "cohort_snapshot",
            json!({"snapshot_index": index}),
        )
    }));
    let appended = (130..140)
        .map(|index| {
            row(
                index + 3,
                "cohort_snapshot",
                json!({"snapshot_index": index}),
            )
        })
        .collect::<Vec<_>>();
    let retained = compact_latest_cohort(&initial.join("\n"))
        .expect("initial cohort")
        .expect("bounded initial cohort");
    let incremental = compact_latest_cohort(&format!("{retained}\n{}", appended.join("\n")))
        .expect("incremental cohort")
        .expect("bounded incremental cohort");
    initial.extend(appended);
    let full = compact_latest_cohort(&initial.join("\n"))
        .expect("full cohort")
        .expect("bounded full cohort");

    assert_eq!(incremental, full);
}

#[test]
fn malformed_current_run_row_is_not_hidden() {
    let content = format!("{}\n{{not-json", identity());

    let error = compact_latest_cohort(&content).expect_err("invalid current row");

    assert!(error.to_string().contains("line 2"));
}

#[test]
fn routing_window_keeps_exact_recent_outcomes_and_regime_history() {
    let mut rows = vec![identity()];
    rows.extend((0..300).map(|index| {
        row(
            index + 2,
            "intent_routing",
            json!({
                "actions": [{"sample": index}],
                "withheld": [{"sample": index}],
                "evaluations": [{
                    "strategy_id": "range_onset_bidirectional_v1",
                    "symbol": "BTC",
                    "decision_time_ms": index as u64 + 1
                }]
            }),
        )
    }));

    let compact = compact_latest_cohort(&rows.join("\n"))
        .expect("valid cohort")
        .expect("cohort projection");
    let payloads = compact
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).expect("compacted row"))
        .filter(|value| value["event_type"] == "intent_routing")
        .map(|value| value["payload"].clone())
        .collect::<Vec<_>>();
    let samples = |key: &str| {
        payloads
            .iter()
            .flat_map(|payload| payload[key].as_array().unwrap())
            .map(|value| value["sample"].as_u64().unwrap())
            .collect::<Vec<_>>()
    };
    let evaluations = payloads
        .iter()
        .flat_map(|payload| payload["evaluations"].as_array().unwrap())
        .count();

    assert_eq!(samples("actions"), (250..300).collect::<Vec<_>>());
    assert_eq!(samples("withheld"), (250..300).collect::<Vec<_>>());
    assert_eq!(evaluations, 240);
}

#[test]
fn cohort_window_retains_bounded_maximum_hold_decisions() {
    let mut rows = vec![identity()];
    rows.extend((0..60).map(|index| {
        row(
            index + 2,
            "maximum_hold_decision",
            json!({
                "decision_id": format!("HYPE:{index}:soft_maximum_hold"),
                "lifecycle_id": format!("HYPE:{index}"),
                "symbol": "HYPE",
                "strategy_id": "hype_breakout_onset_bidirectional_v1",
                "outcome": "extend"
            }),
        )
    }));

    let compact = compact_latest_cohort(&rows.join("\n"))
        .expect("valid cohort")
        .expect("cohort projection");
    let decisions = compact
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).expect("compacted row"))
        .filter(|value| value["event_type"] == "maximum_hold_decision")
        .collect::<Vec<_>>();

    assert_eq!(decisions.len(), 50);
    assert_eq!(
        decisions[0]["payload"]["decision_id"],
        "HYPE:10:soft_maximum_hold"
    );
}

#[test]
fn cohort_window_retains_bounded_independent_regime_history() {
    let mut rows = vec![identity()];
    rows.extend((0..300).map(|index| {
        row(
            index + 2,
            "canonical_regime_evaluations",
            json!({
                "evaluations": [{
                    "strategy_id": "canonical_regime_telemetry_v1",
                    "symbol": "BTC",
                    "decision_time_ms": index as u64 + 1
                }],
                "contract": {
                    "execution_authority": "none",
                    "intents_emitted": false,
                    "configured_route": false
                }
            }),
        )
    }));

    let compact = compact_latest_cohort(&rows.join("\n"))
        .expect("valid cohort")
        .expect("cohort projection");
    let evaluations = compact
        .lines()
        .map(|line| serde_json::from_str::<Value>(line).expect("compacted row"))
        .filter(|value| value["event_type"] == "canonical_regime_evaluations")
        .flat_map(|value| {
            value["payload"]["evaluations"]
                .as_array()
                .expect("canonical evaluations")
                .clone()
        })
        .collect::<Vec<_>>();

    assert_eq!(evaluations.len(), 240);
    assert_eq!(evaluations[0]["decision_time_ms"], 61);
    assert_eq!(evaluations[239]["decision_time_ms"], 300);
}
