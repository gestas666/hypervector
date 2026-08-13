use hypervector_tui::app::App;
use hypervector_tui::backend_telemetry::parse_backend_telemetry;
use ratatui::{Terminal, backend::TestBackend};
use serde_json::{Value, json};

fn row(sequence: u64, event_type: &str, payload: Value) -> String {
    json!({
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": "2026-08-11T04:01:05+00:00",
        "execution_mode": "live",
        "live_armed": true,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "range-retired-v39",
        "profile_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "run_id": "cohort-canonical-test",
        "payload": payload
    })
    .to_string()
}

fn identity() -> String {
    row(
        1,
        "configuration_identity",
        json!({
            "symbol": "MULTI",
            "strategy_name": "multi_asset_bidirectional_cohort",
            "enabled_symbols": ["BTC"],
            "assets": [{
                "symbol": "BTC",
                "sides": ["long", "short"],
                "leverage": 5.0,
                "venue_max_leverage": 40.0,
                "margin_fraction": 0.03,
                "max_notional_usd": 25.0,
                "stop_bps": 80.0,
                "maximum_hold_seconds": 86400
            }],
            "providers": [{
                "strategy_id": "fixture_bidirectional_v1",
                "symbols": ["BTC"],
                "sides": ["long", "short"],
                "priority": 10,
                "timeframe": "1m",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": ["BTC"]
            }],
            "position_policy": {
                "max_positions_per_symbol": 1,
                "maximum_concurrent_positions": 1
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

fn canonical() -> String {
    row(
        2,
        "canonical_regime_evaluations",
        json!({
            "contract": {
                "execution_authority": "none",
                "intents_emitted": false,
                "configured_route": false
            },
            "evaluations": [{
                "strategy_id": "canonical_regime_telemetry_v1",
                "symbol": "BTC",
                "decision_time_ms": 1786420860000_u64,
                "reference_price": 118000.0,
                "decision_action": "regime_observation",
                "eligible": false,
                "reason": "canonical_regime_observation",
                "backend_non_action_reason": "telemetry_only_no_execution_authority",
                "side": null,
                "score": null,
                "minimum_score": null,
                "trigger": null,
                "primary_regime": "TREND_UP",
                "state_1m": "TREND_UP",
                "state_5m": "TREND_UP",
                "context_15m": "RANGE",
                "confidence": 0.8,
                "readiness": {
                    "side": null,
                    "conditions_met": 1,
                    "conditions_required": 1,
                    "readiness_fraction": 1.0,
                    "blockers": [],
                    "indicators": ["5m TREND_UP"],
                    "metrics": {}
                }
            }]
        }),
    )
}

#[test]
fn independent_canonical_regime_is_visible_without_becoming_a_provider() {
    let ledger = format!("{}\n{}\n", identity(), canonical());

    let telemetry = parse_backend_telemetry(&ledger).expect("canonical ledger should parse");

    assert_eq!(telemetry.cohort.providers.len(), 1);
    assert_eq!(
        telemetry.cohort.providers[0].strategy_id,
        "fixture_bidirectional_v1"
    );
    assert_eq!(telemetry.cohort.evaluations.len(), 1);
    assert_eq!(
        telemetry.cohort.evaluations[0].strategy_id,
        "canonical_regime_telemetry_v1"
    );
    assert_eq!(telemetry.cohort.regime_history.len(), 1);
    assert_eq!(
        telemetry.cohort.regime_history[0].primary_regime.as_deref(),
        Some("TREND_UP")
    );
}

#[test]
fn canonical_regime_rejects_any_execution_authority() {
    let mut event = serde_json::from_str::<Value>(&canonical()).expect("canonical JSON");
    event["payload"]["contract"]["execution_authority"] = json!("hyperliquid_mainnet");
    let ledger = format!("{}\n{}\n", identity(), event);

    let error = parse_backend_telemetry(&ledger).expect_err("authority must fail closed");

    assert!(error.to_string().contains("authority is invalid"));
}

#[test]
fn staged_canonical_regime_populates_every_screen_eight_diagnostic() {
    let ledger = format!("{}\n{}\n", identity(), canonical());
    let telemetry = parse_backend_telemetry(&ledger).expect("canonical ledger should parse");
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    app.active_tab = 7;
    let mut terminal = Terminal::new(TestBackend::new(180, 50)).expect("terminal");

    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw canonical regime screen");

    let buffer = terminal.backend().buffer();
    let screen = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    assert!(screen.contains("5M VERDICT TREND_UP"), "{screen}");
    assert!(screen.contains("MOVE STRENGTH 80.0%"), "{screen}");
    assert!(screen.contains("TREND STACK // BTC // NEUTRAL"), "{screen}");
    assert!(!screen.contains("PROVIDER ONLY READY"), "{screen}");
}
