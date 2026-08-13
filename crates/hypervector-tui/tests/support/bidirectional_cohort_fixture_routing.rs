fn routing() -> String {
    row(
        2,
        "intent_routing",
        json!({
            "actions": [{
                "action": "enter",
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "BTC",
                "side": "long",
                "decision_time_ms": 1785599999000_u64,
                "reference_price": 101.0,
                "regime_alignment_score": 0.6666666667,
                "regime_alignment_stance": "directionally_supported",
                "regime_decision_time_ms": 1785599999000_u64,
                "regime_alignment_basis": "canonical_1m_5m_15m_1_3_2_v1"
            }],
            "withheld": [{
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "SOL",
                "side": "short",
                "decision_time_ms": 1785599999000_u64,
                "reference_price": 42.0,
                "source_reason": "fixture",
                "regime_alignment_score": -0.6666666667,
                "regime_alignment_stance": "directionally_opposed",
                "regime_decision_time_ms": 1785599999000_u64,
                "regime_alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
                "reason": "portfolio_position_capacity"
            }],
            "evaluations": [
                {
                    "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
                    "symbol": "ETH",
                    "decision_time_ms": 1785599999000_u64,
                    "reference_price": 100.0,
                    "decision_action": "hold",
                    "eligible": false,
                    "reason": "no_trigger",
                    "side": "long",
                    "score": 3,
                    "minimum_score": 8,
                    "trigger": "none",
                    "primary_regime": null,
                    "state_1m": null,
                    "state_5m": null,
                    "context_15m": null,
                    "confidence": null,
                    "readiness": {
                        "side": "long",
                        "conditions_met": 4,
                        "conditions_required": 6,
                        "readiness_fraction": 0.6666666667,
                        "blockers": ["awaiting_squeeze_release", "volume_not_above_1x"],
                        "indicators": ["ADX 21.4/18.0", "VOLUME 0.92x", "SQUEEZE ARMED"]
                    }
                },
                {
                    "strategy_id": "range_onset_bidirectional_v1",
                    "symbol": "SOL",
                    "decision_time_ms": 1785599999000_u64,
                    "reference_price": 42.0,
                    "decision_action": "hold",
                    "eligible": false,
                    "reason": "regime_not_admitted",
                    "side": "short",
                    "score": null,
                    "minimum_score": null,
                    "trigger": null,
                    "primary_regime": "RANGE",
                    "state_1m": "RANGE",
                    "state_5m": "RANGE",
                    "context_15m": "TREND_UP",
                    "confidence": 0.62,
                    "readiness": {
                        "side": "short",
                        "conditions_met": 2,
                        "conditions_required": 3,
                        "readiness_fraction": 0.6666666667,
                        "blockers": ["5m_regime_not_admitted"],
                        "indicators": ["SMA GAP -1.8bps", "5m REGIME BLOCKED", "RAW CROSS NONE"],
                        "metrics": regime_metrics()
                    }
                },
                {
                    "strategy_id": "hypervelocity_source_follow_bidirectional_5m_v1",
                    "symbol": "BTC",
                    "decision_time_ms": 1785599999000_u64,
                    "reference_price": 101.0,
                    "decision_action": "hold",
                    "eligible": false,
                    "reason": "primary_onset_absent",
                    "side": "long",
                    "score": null,
                    "minimum_score": null,
                    "trigger": "none",
                    "primary_regime": "TREND_UP",
                    "state_1m": null,
                    "state_5m": "TREND_UP",
                    "context_15m": null,
                    "confidence": 0.85,
                    "readiness": {
                        "side": "long",
                        "conditions_met": 2,
                        "conditions_required": 3,
                        "readiness_fraction": 0.6666666667,
                        "blockers": ["awaiting_primary_onset"],
                        "indicators": ["5M TREND_UP", "ONSET NO", "CONF 85/70", "RANGE 20.0 [12.0,100.0]"]
                    }
                },
                {
                    "strategy_id": "hype_breakout_onset_bidirectional_v1",
                    "symbol": "HYPE",
                    "decision_time_ms": 1785599999000_u64,
                    "reference_price": 51.0,
                    "decision_action": "hold",
                    "eligible": false,
                    "reason": "5m_not_breakout",
                    "side": "long",
                    "score": null,
                    "minimum_score": null,
                    "trigger": "none",
                    "primary_regime": "RANGE",
                    "state_1m": "TREND_UP",
                    "state_5m": "RANGE",
                    "context_15m": "RANGE",
                    "confidence": 0.61,
                    "readiness": {
                        "side": "long",
                        "conditions_met": 1,
                        "conditions_required": 3,
                        "readiness_fraction": 0.3333333333,
                        "blockers": ["5m_not_breakout"],
                        "indicators": ["5M RANGE", "ONSET NO", "STRUCT LONG", "CONF 61% TELEMETRY"]
                    }
                }
            ]
        }),
    )
}

fn market_candles() -> String {
    let bars = SYMBOLS
        .iter()
        .enumerate()
        .map(|(symbol_index, symbol)| {
            let scale = 1.0 / (symbol_index as f64 + 1.0);
            let candles = [
                json!({
                    "timestamp_ms": 1_785_585_420_000_u64,
                    "open": 100.0 * scale,
                    "high": 102.0 * scale,
                    "low": 99.0 * scale,
                    "close": 101.0 * scale,
                    "volume": 10.0
                }),
                json!({
                    "timestamp_ms": 1_785_585_480_000_u64,
                    "open": 101.0 * scale,
                    "high": 103.0 * scale,
                    "low": 98.0 * scale,
                    "close": 99.0 * scale,
                    "volume": 12.0
                }),
                json!({
                    "timestamp_ms": 1_785_585_540_000_u64,
                    "open": 99.0 * scale,
                    "high": 102.0 * scale,
                    "low": 98.0 * scale,
                    "close": 101.0 * scale,
                    "volume": 11.0
                }),
            ];
            ((*symbol).to_string(), json!(candles))
        })
        .collect::<serde_json::Map<String, Value>>();
    row(
        3,
        "market_candles",
        json!({"timeframe": "1m", "bars": bars}),
    )
}

fn snapshot(sequence: u64, mark: f64, include_fill: bool) -> String {
    snapshot_with_equity(sequence, mark, include_fill, 503.16)
}

fn snapshot_with_equity(sequence: u64, mark: f64, include_fill: bool, equity: f64) -> String {
    row(
        sequence,
        "cohort_snapshot",
        json!({
            "account_value_usd": equity,
            "withdrawable_usd": (equity - 6.0).max(0.0),
            "account_balance_source": "spot_clearinghouse_state",
            "total_margin_used_usd": 5.0,
            "total_notional_position_usd": 25.0,
            "open_position_count": 1,
            "recent_fills": if include_fill { vec![exact_fill()] } else { vec![] },
            "books": SYMBOLS.map(|symbol| book_snapshot(symbol, mark)),
            "assets": [
                asset_snapshot("BTC", mark),
                asset_snapshot("ETH", mark * 0.05),
                asset_snapshot("SOL", mark * 0.02),
                asset_snapshot("HYPE", mark * 0.01)
            ]
        }),
    )
}

fn snapshot_with_transition_drain(sequence: u64, drain: Value) -> String {
    let mut value: Value =
        serde_json::from_str(&snapshot(sequence, 101.0, true)).expect("snapshot row");
    value["payload"]["transition_drain"] = drain;
    value.to_string()
}

fn transition_drain(status: &str) -> Value {
    json!({
        "status": status,
        "request_id": if status == "inactive" { None } else { Some("d".repeat(32)) },
        "origin_run_id": if status == "inactive" { None } else { Some("cohort-test") },
        "run_id": "cohort-test",
        "profile_fingerprint": "a".repeat(64),
        "requested_at_utc": if status == "inactive" { None } else { Some("2026-08-01T15:59:58+00:00") },
        "activated_at_utc": if status == "inactive" { None } else { Some("2026-08-01T15:59:59+00:00") },
        "resume_count": 0,
        "last_resumed_at_utc": None::<String>,
        "completed_at_utc": if status == "completed" { Some("2026-08-01T16:00:00+00:00") } else { None }
    })
}

fn resumed_transition_drain(status: &str) -> Value {
    let mut drain = transition_drain(status);
    drain["origin_run_id"] = json!("origin-live-001");
    drain["resume_count"] = json!(2);
    drain["last_resumed_at_utc"] = json!("2026-08-01T15:59:59.500+00:00");
    drain
}

fn backend_with_transition_drain(drain: Value) -> BackendTelemetrySnapshot {
    let ledger = [identity(), snapshot_with_transition_drain(2, drain)].join("\n");
    parse_backend_telemetry(&format!("{ledger}\n")).expect("transition drain fixture")
}

fn book_snapshot(symbol: &str, mark: f64) -> Value {
    let scale = match symbol {
        "BTC" => 1.0,
        "ETH" => 0.05,
        "SOL" => 0.02,
        _ => 0.01,
    };
    let mid = mark * scale;
    json!({
        "symbol": symbol,
        "source": "hyperliquid_mainnet_l2_rest",
        "exchange_ts_ms": 1_785_599_999_000_u64,
        "recv_ts_ms": 1_785_599_999_020_u64,
        "mid_px": mid,
        "spread_bps": 2.0,
        "bid_depth_ratio": 1.5,
        "opi": 0.2,
        "bids": [
            {"price": mid - 0.01 * scale, "size": 3.0, "orders": 2},
            {"price": mid - 0.02 * scale, "size": 2.0, "orders": 1}
        ],
        "asks": [
            {"price": mid + 0.01 * scale, "size": 2.0, "orders": 1},
            {"price": mid + 0.02 * scale, "size": 2.0, "orders": 2}
        ]
    })
}

fn cohort_backend() -> BackendTelemetrySnapshot {
    let ledger = [
        identity(),
        routing(),
        market_candles(),
        snapshot(4, 100.0, false),
        snapshot(5, 99.0, false),
        snapshot(6, 101.0, true),
    ]
    .join("\n");
    parse_backend_telemetry(&format!("{ledger}\n")).expect("cohort fixture should parse")
}

fn disarmed_cohort_backend() -> BackendTelemetrySnapshot {
    let ledger = [identity(), routing(), market_candles()]
        .into_iter()
        .map(|line| {
            let mut value: Value = serde_json::from_str(&line).expect("valid cohort row");
            value["live_armed"] = json!(false);
            value["execution_authority"] = json!("none");
            value.to_string()
        })
        .collect::<Vec<_>>()
        .join("\n");
    parse_backend_telemetry(&format!("{ledger}\n")).expect("disarmed fixture should parse")
}

fn cohort_app() -> App {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(cohort_backend());
    app
}
