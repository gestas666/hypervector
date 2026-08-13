const SYMBOLS: [&str; 4] = ["BTC", "ETH", "SOL", "HYPE"];
const COMPLETE_SYMBOLS: [&str; 9] = [
    "BTC",
    "ETH",
    "SOL",
    "HYPE",
    "xyz:SP500",
    "xyz:SPCX",
    "xyz:SNDK",
    "xyz:GOLD",
    "xyz:BRENTOIL",
];

fn row(sequence: u64, event_type: &str, payload: Value) -> String {
    json!({
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-01T16:00:00+00:00",
        "execution_mode": "live",
        "live_armed": true,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "multi_asset_bidirectional_canary_v1",
        "profile_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "run_id": "cohort-test",
        "payload": payload
    })
    .to_string()
}

fn asset_config(symbol: &str) -> Value {
    json!({
        "symbol": symbol,
        "sides": ["long", "short"],
        "leverage": 5.0,
        "venue_max_leverage": 20.0,
        "margin_fraction": 0.03,
        "max_notional_usd": 25.0,
        "stop_bps": 80.0,
        "maximum_hold_seconds": 28800
    })
}

fn asset_snapshot(symbol: &str, mark: f64) -> Value {
    let is_open = symbol == "BTC";
    json!({
        "symbol": symbol,
        "state": if is_open { "OPEN" } else { "FLAT" },
        "direction_capability": ["long", "short"],
        "position_size_signed": if is_open { 0.5 } else { 0.0 },
        "position_side": if is_open { Some("long") } else { None },
        "entry_oid": if is_open { Some(11) } else { None },
        "stop_oid": if is_open { Some(12) } else { None },
        "target_oid": if is_open { Some(13) } else { None },
        "target_price": if is_open { Some(103.0) } else { None },
        "execution_plan": if is_open { Some(json!({
            "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
            "entry_liquidity": "taker_ioc",
            "stop_policy": "structural_clamped_bps",
            "target_policy": "reward_risk",
            "maximum_hold_seconds": 86400,
            "stop_bps": null,
            "minimum_stop_bps": 20.0,
            "maximum_stop_bps": 75.0,
            "target_bps": null,
            "target_r_multiple": 3.0,
            "safety_stop_overlay": false,
            "stop_anchor": 99.0
        })) } else { None },
        "last_fault": null,
        "mark_price": mark,
        "entry_price": if is_open { Some(100.0) } else { None },
        "liquidation_price": if is_open { Some(82.0) } else { None },
        "liquidation_distance_pct": if is_open { Some(18.811881) } else { None },
        "margin_used_usd": if is_open { 5.0 } else { 0.0 },
        "position_value_usd": if is_open { 25.0 } else { 0.0 },
        "unrealized_pnl_usd": if is_open { 0.5 } else { 0.0 },
        "leverage": if is_open { Some(5) } else { None },
        "fees_net_usd": 0.01,
        "funding_net_usd": -0.001,
        "realized_pnl_usd": 0.0,
        "fill_count": 1,
        "cost_scope": "compatible_profile_history"
    })
}

fn exact_fill() -> Value {
    json!({
        "symbol": "BTC",
        "strategy_id": "range_onset_bidirectional_v1",
        "operation": "entry",
        "trade_id": 101,
        "oid": 11,
        "venue_timestamp_ms": 1785599999000_u64,
        "price": 101.0,
        "size": 0.5,
        "side": "B",
        "direction": "Open Long",
        "fee_usd": 0.01,
        "closed_pnl_usd": 0.0,
        "expected_price": 100.9,
        "slippage_bps": 9.91,
        "acknowledgement_latency_ms": 40,
        "markout_bps": 5.2,
        "markout_horizon_ms": 6000,
        "origin_run_id": "bidirectional-live-1785704911829",
        "exit_controller_id": "cohort_maximum_hold",
        "entry_price": 100.0,
        "entry_venue_timestamp_ms": 1_785_599_000_000_u64,
        "lifecycle_fees_usd": 0.02,
        "lifecycle_funding_usd": 0.003,
        "net_pnl_usd": 0.233,
        "holding_time_ms": 28_800_000_u64,
        "exit_reason": null
    })
}

fn research_evidence() -> Vec<Value> {
    let mappings = [
        ("hulk_expansion_bidirectional_tuned_v2", SYMBOLS.as_slice()),
        ("range_onset_bidirectional_v1", SYMBOLS.as_slice()),
        ("hypervelocity_source_follow_bidirectional_5m_v1", &["BTC"]),
        ("hype_breakout_onset_bidirectional_v1", &["HYPE"]),
    ];
    mappings
        .into_iter()
        .flat_map(|(strategy_id, symbols)| {
            symbols.iter().map(move |symbol| {
                let (state, confidence, cadence, summary) = match (strategy_id, *symbol) {
                    ("hulk_expansion_bidirectional_tuned_v2", "BTC") => (
                        "contradictory",
                        "high",
                        "110 trades / 337 days (~2.3/week)",
                        "Forward evidence contradicted development.",
                    ),
                    ("range_onset_bidirectional_v1", "SOL") => (
                        "historical_candidate",
                        "medium",
                        "42 trades / 201 days (~1.5/week)",
                        "Both directions positive; long profits are concentrated.",
                    ),
                    ("hypervelocity_source_follow_bidirectional_5m_v1", "BTC") => (
                        "mixed_nonmatching_risk",
                        "medium",
                        "175 events / 90 days (~1.9/day)",
                        "Signal cadence measured; current wrapper outcomes unvalidated.",
                    ),
                    _ => (
                        "unreviewed_exact_mapping",
                        "low",
                        "not established",
                        "No matched outcome record.",
                    ),
                };
                json!({
                    "strategy_id": strategy_id, "symbol": symbol, "research_state": state,
                    "confidence": confidence, "cadence": cadence, "summary": summary,
                    "evidence_source": "docs/reviews/evidence.md", "execution_effect": "report_only"
                })
            })
        })
        .collect()
}

fn identity() -> String {
    row(
        1,
        "configuration_identity",
        json!({
            "symbol": "MULTI",
            "strategy_name": "multi_asset_bidirectional_cohort",
            "config_source_path": "configs/multi_asset_bidirectional_canary.toml",
            "runtime": {"poll_seconds": 5.0, "lookback_days": 10},
            "enabled_symbols": SYMBOLS,
            "assets": SYMBOLS.map(asset_config),
            "providers": [
                {
                    "strategy_id": "hulk_expansion_bidirectional_tuned_v2",
                    "symbols": SYMBOLS,
                    "sides": ["long", "short"],
                    "priority": 10,
                    "timeframe": "30m",
                    "maximum_entry_delay_seconds": 60,
                    "execution_symbols": SYMBOLS,
                    "execution": {
                        "entry_liquidity": "taker_ioc",
                        "stop_policy": "structural_clamped_bps",
                        "target_policy": "reward_risk",
                        "maximum_hold_seconds": 86400,
                        "stop_bps": null,
                        "minimum_stop_bps": 20.0,
                        "maximum_stop_bps": 75.0,
                        "target_bps": null,
                        "target_r_multiple": 3.0,
                        "safety_stop_overlay": false
                    }
                },
                {
                    "strategy_id": "range_onset_bidirectional_v1",
                    "symbols": SYMBOLS,
                    "sides": ["long", "short"],
                    "priority": 20,
                    "timeframe": "1m",
                    "maximum_entry_delay_seconds": 60,
                    "execution_symbols": SYMBOLS,
                    "sizing_overrides": {
                        "SOL": {
                            "margin_fraction": 0.06,
                            "max_notional_usd": 20.0
                        }
                    }
                },
                {
                    "strategy_id": "hypervelocity_source_follow_bidirectional_5m_v1",
                    "symbols": ["BTC"],
                    "sides": ["long", "short"],
                    "priority": 30,
                    "timeframe": "5m",
                    "maximum_entry_delay_seconds": 60,
                    "execution_symbols": ["BTC"],
                    "source_profile": "configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml"
                },
                {
                    "strategy_id": "hype_breakout_onset_bidirectional_v1",
                    "symbols": ["HYPE"],
                    "sides": ["long", "short"],
                    "priority": 40,
                    "timeframe": "1m",
                    "maximum_entry_delay_seconds": 60,
                    "execution_symbols": ["HYPE"]
                }
            ],
            "strategy_evidence": research_evidence(),
            "position_policy": {
                "max_positions_per_symbol": 1,
                "maximum_concurrent_positions": 4
            },
            "routing_policy": {
                "mode": "same_symbol_conflict_preference_v1",
                "alignment_basis": "canonical_1m_5m_15m_1_3_2_v1",
                "state_weights": {
                    "state_1m": 1.0,
                    "state_5m": 3.0,
                    "context_15m": 2.0
                },
                "standalone_intents_ungated": true,
                "forced_regime_exit": false,
                "fallback": "provider_priority_then_decision_time"
            }
        }),
    )
}

fn regime_metrics() -> Value {
    json!({
        "component_authority": "observe_only",
        "ema_21_55_gap_bps": 12.4,
        "sma_100_200_gap_bps": -4.0,
        "cipher_a_direction": 1.0,
        "harsi_direction": -1.0,
        "choppiness_14": 48.2,
        "regime_1m_reason": "range_structure",
        "regime_5m_reason": "range_structure",
        "regime_15m_reason": "trend_structure",
        "regime_1m_strength_percentile": 22.0,
        "regime_5m_strength_percentile": 18.0,
        "regime_15m_strength_percentile": 76.0,
        "regime_1m_bbwp_percentile": 19.0,
        "regime_5m_bbwp_percentile": 12.0,
        "regime_15m_bbwp_percentile": 44.0,
        "regime_1m_ema_gap_bps": 2.1,
        "regime_5m_ema_gap_bps": 0.8,
        "regime_15m_ema_gap_bps": 11.2,
        "regime_1m_coiling": true,
        "regime_5m_coiling": true,
        "regime_15m_coiling": false,
        "regime_5m_range_cause_coiling": true,
        "regime_5m_range_cause_strength": true,
        "regime_5m_range_cause_gap": true,
        "regime_5m_range_cause_filter": true,
        "regime_range_filter_name": "bbwp",
        "regime_bbwp_threshold_pct": 25.0,
        "regime_minimum_gap_bps": 5.0,
        "regime_range_strength_threshold_pct": 30.0,
        "regime_trend_strength_threshold_pct": 60.0,
        "regime_5m_breakout_volume_ratio": 0.7,
        "regime_breakout_volume_multiple": 2.5,
        "mtf_5m_bias": 2.0,
        "mtf_15m_bias": 3.0,
        "trend_r2": 0.72,
        "self_aware_tqi": 0.61
    })
}
