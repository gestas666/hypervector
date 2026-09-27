//! The cockpit's STOP/LOCK lines follow an acknowledged venue stop raise.
//!
//! The checkpoint keeps attributing an open lifecycle to its initial stop. After
//! the backend raises that stop to the profit floor, the cohort ledger carries the
//! acknowledgement (`breakeven_stop_attempt`) and the covering replacement oid.

use std::fs;
use std::path::Path;

use chrono::Utc;
use hypervector_tui::theme::CockpitTheme;
use hypervector_tui::{
    App,
    backend_telemetry::{
        BackendConnectionState, BackendTelemetrySnapshot, BackendTelemetrySource,
        parse_backend_telemetry,
    },
};
use ratatui::{
    Terminal,
    backend::TestBackend,
    style::{Color, Style},
};
use serde_json::{Value, json};

const RUN_ID: &str = "bidirectional-live-raise-fixture";
const PROFILE_ID: &str = "multi_asset_stop_raise_display_fixture";
const FINGERPRINT: &str = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
const SYMBOL: &str = "xyz:BRENTOIL";
const ROUTE: &str = "hourly_donchian_20_10_atr20_strong_short_v1";
const ENTRY_OID: u64 = 555_018_656_094;
const INITIAL_STOP_OID: u64 = 555_018_726_035;
const RAISED_STOP_OID: u64 = 555_530_692_113;
const INITIAL_TRIGGER: f64 = 97.554;
const RAISED_TRIGGER: f64 = 99.297625;

fn row(sequence: u64, event_type: &str, observed_at: &str, payload: Value) -> String {
    json!({
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": observed_at,
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": true,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": PROFILE_ID,
        "profile_fingerprint": FINGERPRINT,
        "run_id": RUN_ID,
        "payload": payload
    })
    .to_string()
}

fn identity(observed_at: &str) -> String {
    let asset = |symbol: &str| {
        json!({
            "symbol": symbol,
            "sides": ["long", "short"],
            "leverage": 8.0,
            "venue_max_leverage": 20.0,
            "margin_fraction": 0.1,
            "max_notional_usd": 1500.0,
            "stop_bps": 100.0,
            "maximum_hold_seconds": 86400
        })
    };
    row(
        1,
        "configuration_identity",
        observed_at,
        json!({
            "symbol": "MULTI",
            "strategy_name": "multi_asset_bidirectional_cohort",
            "runtime": {"poll_seconds": 5.0, "lookback_days": 10},
            "enabled_symbols": ["BTC", SYMBOL],
            "assets": [asset("BTC"), asset(SYMBOL)],
            "providers": [{
                "strategy_id": ROUTE,
                "symbols": ["BTC", SYMBOL],
                "sides": ["long", "short"],
                "priority": 10,
                "timeframe": "1h",
                "maximum_entry_delay_seconds": 60,
                "execution_symbols": [SYMBOL],
                "execution": {
                    "entry_liquidity": "taker_ioc",
                    "stop_policy": "structural_clamped_bps",
                    "target_policy": "none",
                    "maximum_hold_seconds": 86400,
                    "stop_bps": null,
                    "minimum_stop_bps": 20.0,
                    "maximum_stop_bps": 250.0,
                    "target_bps": null,
                    "target_r_multiple": null,
                    "safety_stop_overlay": false,
                    "provider_recipe_exit_policy": "honor",
                    "adaptive_exit_policy": "regime_flip_floor_retention_v2",
                    "breakeven_stop_target": "floor"
                }
            }],
            "position_policy": {"max_positions_per_symbol": 1, "maximum_concurrent_positions": 2}
        }),
    )
}

fn snapshot(observed_at: &str, stop_oid: u64) -> String {
    let flat = json!({
        "symbol": "BTC", "state": "FLAT", "direction_capability": ["long", "short"],
        "position_size_signed": 0.0, "position_side": null, "entry_oid": null,
        "stop_oid": null, "target_oid": null, "target_price": null, "execution_plan": null,
        "last_fault": null, "mark_price": 64_000.0, "entry_price": null,
        "liquidation_price": null, "liquidation_distance_pct": null, "margin_used_usd": 0.0,
        "position_value_usd": 0.0, "unrealized_pnl_usd": 0.0, "leverage": null,
        "fees_net_usd": 0.0, "funding_net_usd": 0.0, "realized_pnl_usd": 0.0,
        "fill_count": 0, "opened_at_ms": null, "protective_exit_pending": false,
        "partial_exit_fill_count": 0, "partial_exit_size": 0.0, "stop_protection": "flat"
    });
    let open = json!({
        "symbol": SYMBOL, "state": "OPEN", "direction_capability": ["long", "short"],
        "position_size_signed": 5.84, "position_side": "long", "entry_oid": ENTRY_OID,
        "stop_oid": stop_oid, "target_oid": null, "target_price": null, "execution_plan": null,
        "last_fault": null, "mark_price": 99.9765, "entry_price": 99.05,
        "liquidation_price": 88.8631, "liquidation_distance_pct": 11.1, "margin_used_usd": 78.0,
        "position_value_usd": 583.86276, "unrealized_pnl_usd": 5.41276, "leverage": 8,
        "fees_net_usd": 0.049978, "funding_net_usd": -0.002567, "realized_pnl_usd": 0.0,
        "fill_count": 1, "opened_at_ms": 1_785_600_000_000_u64, "protective_exit_pending": false,
        "partial_exit_fill_count": 0, "partial_exit_size": 0.0, "stop_protection": "covering"
    });
    row(
        2,
        "cohort_snapshot",
        observed_at,
        json!({
            "account_value_usd": 4824.72,
            "withdrawable_usd": 4599.76,
            "total_margin_used_usd": 78.0,
            "total_notional_position_usd": 583.86,
            "open_position_count": 1,
            "assets": [flat, open],
            "recent_fills": []
        }),
    )
}

fn raise_attempt(entry_oid: u64) -> Value {
    json!({
        "symbol": SYMBOL,
        "entry_oid": entry_oid,
        "attempt": 1,
        "trigger_price": RAISED_TRIGGER,
        "raised": true,
        "breakeven_stop_target": "floor",
        "executable_price": 99.974
    })
}

/// One run's ledger: identity, the given `breakeven_stop_attempt` payloads, the venue snapshot.
fn ledger_with(stop_oid: u64, attempts: &[Value]) -> String {
    let now = Utc::now().to_rfc3339();
    let mut rows = vec![identity(&now)];
    for attempt in attempts {
        rows.push(row(3, "breakeven_stop_attempt", &now, attempt.clone()));
    }
    rows.push(snapshot(&now, stop_oid));
    rows.push(row(4, "heartbeat", &now, json!({"status": "running"})));
    rows.join("\n")
}

fn ledger(stop_oid: u64, raise_entry_oid: Option<u64>) -> String {
    let attempts = raise_entry_oid
        .map(raise_attempt)
        .into_iter()
        .collect::<Vec<_>>();
    ledger_with(stop_oid, &attempts)
}

fn context(primary: &str) -> Value {
    json!({
        "status": "observed", "primary_regime": primary, "state_1m": primary,
        "state_5m": primary, "context_15m": primary, "confidence": 0.8
    })
}

/// The backend's report-only estimate for the initial 97.554 stop (entry 99.05 x 5.84).
fn initial_profit_protection() -> Value {
    json!({
        "status": "open_profit_unprotected",
        "reported_marked_net_pnl_usd": 5.358215230201701,
        "estimated_exit_now_net_usd": 5.307769975257308,
        "estimated_stop_net_usd": -8.838407701195626,
        "marked_to_stop_giveback_usd": 14.146177676452934,
        "protected_profit_fraction": 0.0,
        "stop_distance_from_mark_bps": 242.30694213140083,
        "measured_entry_fee_rate_bps": 0.8639916500992931,
        "estimated_current_exit_fee_usd": 0.05044525494439275,
        "estimated_stop_exit_fee_usd": 0.049222931397331283,
        "method": "measured_entry_fee_rate_no_future_funding_or_slippage"
    })
}

fn open_reflection() -> Value {
    let contract = json!({
        "report_only": true, "execution_authority": "none",
        "runtime_strategy_changed": false, "automatic_strategy_changes": false
    });
    json!({
        "lifecycle_id": format!("{SYMBOL}:{ENTRY_OID}"),
        "source_run_id": RUN_ID,
        "symbol": SYMBOL,
        "strategy_id": ROUTE,
        "side": "long",
        "entry": {"price": 99.05, "size": 5.84, "venue_timestamp_ms": 1_785_600_030_000_u64},
        "protective_stop": {"oid": INITIAL_STOP_OID, "trigger_price": INITIAL_TRIGGER},
        "profit_protection": initial_profit_protection(),
        "holding_time_ms": 19_886_090,
        "exit_plan": {
            "opened_at_ms": 1_785_600_000_000_u64,
            "timer_origin": "persisted_runtime_opened_at",
            "maximum_hold_seconds": 86400,
            "maximum_hold_policy": "fixed",
            "provider_recipe_exit_policy": "honor",
            "adaptive_exit_policy": "regime_flip_floor_retention_v2",
            "deadline_timestamp_ms": 1_785_686_400_000_u64,
            "remaining_time_ms": 66_513_910,
            "expired": false,
            "source": "bound_execution_plan",
            "controller": "cohort_maximum_hold",
            "opposite_intent_exit_scope": "selected_opposite_from_any_executable_provider_same_symbol",
            "opposite_intent_arbitration": "regime_then_priority"
        },
        "path_since_entry": {
            "status": "observed", "completed_bars": 331,
            "first_timestamp_ms": 1_785_600_060_000_u64, "last_timestamp_ms": 1_785_619_860_000_u64,
            "highest_price": 100.05, "lowest_price": 98.9, "current_directional_return_bps": 93.5,
            "maximum_favorable_excursion_bps": 101.0, "maximum_adverse_excursion_bps": 15.1,
            "peak_giveback_bps": 7.5
        },
        "entry_context": {"signal_provider": context("TREND_UP"), "canonical_regime": context("TREND_UP")},
        "current_context": {"signal_provider": context("TREND_UP"), "canonical_regime": context("TREND_UP")},
        "regime_drift": {"signal_provider_changed": false, "canonical_regime_changed": false},
        "regime_assessment": {
            "contract": contract,
            "structure_support_score": 0.75,
            "structure_stance": "directionally_supported",
            "component_alignment_score": 0.5,
            "component_stance": "aligned_with_position",
            "movement_strength": 0.8,
            "maximum_hold_context": "still_directionally_supported"
        },
        "marked_economics": {
            "mark_price": 99.9765,
            "active_lifecycle_marked_net_pnl_usd": 5.358215230201701,
            "size_signed": 5.84,
            "fees_usd": 0.049977769798323635,
            "funding_usd": -0.002567
        }
    })
}

fn write_checkpoint(path: &Path, trade: Value) {
    let contract = json!({
        "report_only": true, "execution_authority": "none",
        "runtime_strategy_changed": false, "automatic_strategy_changes": false
    });
    let checkpoint = json!({
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "generated_at_utc": Utc::now().to_rfc3339(),
        "lifecycle": {
            "state": "running_consistent",
            "cohort_heartbeat_status": "running",
            "asset_states": {"BTC": "FLAT", SYMBOL: "OPEN"}
        },
        "audit": {
            "run": {"row_count": 4, "run_id": RUN_ID, "profile_id": PROFILE_ID, "profile_fingerprint": FINGERPRINT},
            "runtime": {"poll_cycles": 1, "poll_interval_seconds": {"count": 0, "mean": null, "median": null, "minimum": null, "maximum": null}},
            "health": {"faults": 0},
            "coverage": {"complete": true, "technical_gaps": []},
            "readiness": {"evaluations": 1},
            "execution": {"closed_trades": 0, "net_pnl_usd": 0.0, "open_lifecycles": 1},
            "learning": {"evidence_state": "descriptive_trade_evidence"},
            "open_trade_reflections": {
                "as_of_timestamp_ms": 1_785_619_886_090_u64,
                "contract": contract,
                "open_lifecycles": 1,
                "trades": [trade]
            }
        }
    });
    fs::write(path, checkpoint.to_string()).expect("checkpoint fixture");
}

fn load(stop_oid: u64, raise_entry_oid: Option<u64>) -> BackendTelemetrySnapshot {
    load_from(ledger(stop_oid, raise_entry_oid), open_reflection())
}

/// Load a ledger and a one-trade checkpoint; the cockpit must connect with the checkpoint available.
fn load_from(ledger: String, trade: Value) -> BackendTelemetrySnapshot {
    let directory = tempfile::tempdir().expect("tempdir");
    let ledger_path = directory.path().join("decisions.jsonl");
    let checkpoint_path = directory.path().join("latest.json");
    fs::write(&ledger_path, ledger).expect("ledger fixture");
    write_checkpoint(&checkpoint_path, trade);
    let backend =
        BackendTelemetrySource::with_checkpoint_path(ledger_path, Some(checkpoint_path)).refresh();
    assert_ne!(
        backend.connection,
        BackendConnectionState::Error,
        "{}",
        backend.status_message
    );
    assert!(
        backend.cohort_checkpoint.available,
        "{:?}",
        backend.cohort_checkpoint.issue
    );
    backend
}

struct RegimePage {
    text: String,
    rows: Vec<Vec<(String, Style)>>,
    theme: CockpitTheme,
}

impl RegimePage {
    /// Foreground of the first cell where `needle` starts on screen.
    fn foreground_of(&self, needle: &str) -> Option<Color> {
        self.rows.iter().find_map(|row| {
            (0..row.len()).find_map(|start| {
                let tail = row[start..]
                    .iter()
                    .map(|(symbol, _)| symbol.as_str())
                    .collect::<String>();
                tail.starts_with(needle).then(|| row[start].1.fg).flatten()
            })
        })
    }
}

/// Render the regime tab: page 1 carries the full-width open snapshot, page 0 the compact deck.
fn regime_page(backend: BackendTelemetrySnapshot, page: u8) -> RegimePage {
    let mut app = App::new("MULTI".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(backend);
    app.selected_cohort_symbol_index = 1;
    app.active_tab = 7;
    app.cohort_regime_page = page;
    let mut terminal = Terminal::new(TestBackend::new(176, 50)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw regime page");
    let buffer = terminal.backend().buffer();
    let rows = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| {
                    let cell = &buffer[(x, y)];
                    (cell.symbol().to_string(), cell.style())
                })
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();
    let text = rows
        .iter()
        .map(|row| {
            row.iter()
                .map(|(symbol, _)| symbol.as_str())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    RegimePage {
        text,
        rows,
        theme: app.theme,
    }
}

#[test]
fn acknowledged_raise_is_the_displayed_stop_and_is_not_flagged_unprotected() {
    let backend = load(RAISED_STOP_OID, Some(ENTRY_OID));

    let trade = &backend.cohort_checkpoint.open_trade_reflections[0];
    assert_eq!(trade.protective_stop_oid, Some(RAISED_STOP_OID));
    assert_eq!(trade.protective_stop_price, Some(RAISED_TRIGGER));
    let raise = trade
        .protective_stop_raise
        .as_ref()
        .expect("raise attribution");
    assert_eq!(raise.previous_oid, INITIAL_STOP_OID);
    assert_eq!(raise.previous_trigger_price, INITIAL_TRIGGER);
    let protection = trade.profit_protection.as_ref().expect("repriced lock");
    assert_eq!(protection.status, "partial_profit_locked");
    assert!(protection.estimated_stop_net_usd > 0.0);

    let page = regime_page(backend, 1);
    let text = &page.text;
    assert!(
        text.contains(&format!(
            "VENUE STOP RAISED #{RAISED_STOP_OID} @99.30 // FROM #{INITIAL_STOP_OID} @97.55"
        )),
        "{text}"
    );
    assert!(!text.contains("LAST STOP"), "{text}");
    let lock = "PROFIT RISK $3.96 // EXIT NOW +$5.31 // STOP +$1.34 // LOCK 25%";
    assert!(text.contains(lock), "{text}");
    assert!(!text.contains("STOP -$8.84"), "{text}");
    assert_eq!(page.foreground_of(lock), page.theme.gold.fg);
    assert_ne!(page.foreground_of(lock), page.theme.bear.fg);
}

#[test]
fn compact_open_snapshot_marks_the_raised_stop() {
    let page = regime_page(load(RAISED_STOP_OID, Some(ENTRY_OID)), 0);
    let text = &page.text;

    assert!(
        text.contains(&format!("S↑#{RAISED_STOP_OID}@99.30")),
        "{text}"
    );
    let lock = "RISK $3.96 NOW+$5.31 STOP+$1.34 LOCK25%";
    assert!(text.contains(lock), "{text}");
    assert_ne!(page.foreground_of(lock), page.theme.bear.fg);
}

#[test]
fn raise_for_another_lifecycle_leaves_the_checkpoint_stop_in_place() {
    let backend = load(RAISED_STOP_OID, Some(ENTRY_OID + 1));

    let trade = &backend.cohort_checkpoint.open_trade_reflections[0];
    assert_eq!(trade.protective_stop_oid, Some(INITIAL_STOP_OID));
    assert_eq!(trade.protective_stop_raise, None);
    let page = regime_page(backend, 1);
    let text = &page.text;
    assert!(
        text.contains(&format!("LAST STOP #{INITIAL_STOP_OID} @97.55")),
        "{text}"
    );
    let lock = "PROFIT RISK $14.15 // EXIT NOW +$5.31 // STOP -$8.84 // LOCK 0%";
    assert!(text.contains(lock), "{text}");
    assert_eq!(page.foreground_of(lock), page.theme.bear.fg);
}

#[test]
fn venue_snapshot_before_the_replacement_keeps_the_initial_stop() {
    let backend = load(INITIAL_STOP_OID, Some(ENTRY_OID));

    let trade = &backend.cohort_checkpoint.open_trade_reflections[0];
    assert_eq!(trade.protective_stop_oid, Some(INITIAL_STOP_OID));
    assert_eq!(trade.protective_stop_price, Some(INITIAL_TRIGGER));
    assert_eq!(trade.protective_stop_raise, None);
}

#[test]
fn ledger_projects_raise_acknowledgements_only_as_display_evidence() {
    let backend =
        parse_backend_telemetry(&ledger(RAISED_STOP_OID, Some(ENTRY_OID))).expect("cohort ledger");

    assert_eq!(backend.cohort.venue_stop_raises.len(), 1);
    let raise = &backend.cohort.venue_stop_raises[0];
    assert_eq!(
        (raise.symbol.as_str(), raise.entry_oid, raise.trigger_price),
        (SYMBOL, ENTRY_OID, RAISED_TRIGGER)
    );
    assert!(!raise.already_at_target);
}

#[test]
fn invalid_raise_evidence_shows_the_checkpoint_stop_instead_of_failing_the_cockpit() {
    let invalid_attempts = [
        json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "attempt": 2, "trigger_price": RAISED_TRIGGER, "raised": "ALREADY_AT_TARGET"}),
        json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "attempt": 2, "trigger_price": null, "raised": true}),
        json!({"symbol": SYMBOL, "entry_oid": null, "attempt": 2, "trigger_price": RAISED_TRIGGER, "raised": true}),
        json!({"symbol": "HYPE", "entry_oid": 7, "attempt": 0, "trigger_price": 40.0, "raised": true}),
    ];
    for invalid in invalid_attempts {
        let ledger = ledger_with(
            RAISED_STOP_OID,
            &[raise_attempt(ENTRY_OID), invalid.clone()],
        );

        let backend = load_from(ledger, open_reflection());

        assert!(backend.cohort.venue_stop_raises.is_empty(), "{invalid}");
        assert_eq!(backend.cohort.assets.len(), 2, "{invalid}");
        let trade = &backend.cohort_checkpoint.open_trade_reflections[0];
        assert_eq!(
            trade.protective_stop_oid,
            Some(INITIAL_STOP_OID),
            "{invalid}"
        );
        assert_eq!(trade.protective_stop_raise, None, "{invalid}");
        let text = regime_page(backend, 1).text;
        assert!(
            text.contains(&format!("LAST STOP #{INITIAL_STOP_OID} @97.55")),
            "{invalid}\n{text}"
        );
        assert!(!text.contains("VENUE STOP RAISED"), "{invalid}\n{text}");
    }
}

#[test]
fn unusable_entry_size_withholds_only_the_repriced_lock() {
    for size in [json!(0.0), json!(-5.84), json!("5.84"), Value::Null] {
        let mut trade = open_reflection();
        trade["entry"]["size"] = size.clone();

        let backend = load_from(ledger(RAISED_STOP_OID, Some(ENTRY_OID)), trade);

        let reflection = &backend.cohort_checkpoint.open_trade_reflections[0];
        assert_eq!(reflection.entry_size, None, "{size}");
        assert_eq!(
            reflection.protective_stop_oid,
            Some(RAISED_STOP_OID),
            "{size}"
        );
        assert_eq!(reflection.profit_protection, None, "{size}");
        let text = regime_page(backend, 1).text;
        assert!(text.contains("PROFIT RISK N/A"), "{size}\n{text}");
        assert!(!text.contains("STOP -$8.84"), "{size}\n{text}");
    }
}

/// One per-asset live journal event, as the single-asset engine writes it.
fn asset_event(sequence: u64, event_type: &str, payload: Value) -> String {
    json!({
        "schema_version": 1,
        "sequence": sequence,
        "event_type": event_type,
        "observed_at_utc": format!("2026-07-31T13:00:{:02}+00:00", sequence),
        "execution_mode": "live",
        "effective_mode": "LIVE ARMED",
        "live_armed": true,
        "execution_authority": "hyperliquid_mainnet",
        "profile_id": "sol_range_onset_canary_v1",
        "profile_fingerprint": "profile",
        "run_fingerprint": "run",
        "run_id": "sol-live-raise",
        "payload": payload
    })
    .to_string()
}

fn open_state(sequence: u64, stop_oid: u64) -> String {
    asset_event(
        sequence,
        "state_transition",
        json!({
            "state": "OPEN", "entry_oid": 101, "stop_oid": stop_oid, "close_oid": null,
            "position_size_signed": 0.30, "opened_at_ms": 1_785_499_500_000_u64,
            "last_fault": null, "stop_reason": null
        }),
    )
}

fn venue_orders(sequence: u64, oid: u64, trigger_price: f64) -> String {
    asset_event(
        sequence,
        "reconciliation",
        json!({
            "account_value_usd": 150.12, "withdrawable_usd": 145.61, "open_order_ids": [oid],
            "open_orders": [{"oid": oid, "size": 0.30, "side": "A", "reduce_only": true,
                "is_trigger": true, "trigger_price": trigger_price, "order_type": "Stop Market"}],
            "fill_ids": [101]
        }),
    )
}

fn raise_ack(sequence: u64, operation: &str, status: &str) -> String {
    asset_event(
        sequence,
        "stop_order",
        json!({
            "operation": operation, "accepted": true, "oid": 303, "status": status,
            "filled_size": null, "average_price": null, "error": null,
            "client_order_id": "0x18b866944864c62356ffbc4951b08baf"
        }),
    )
}

fn raised_event(sequence: u64) -> String {
    asset_event(
        sequence,
        "protective_stop_raised",
        json!({
            "previous_stop_oid": 202, "stop_oid": 303, "previous_trigger_price": 72.515,
            "trigger_price": 73.29, "position_size_signed": 0.30, "venue_visible": true
        }),
    )
}

/// An OPEN SOL lifecycle protected by stop 202, before any raise.
fn open_asset_journal() -> Vec<String> {
    vec![
        asset_event(
            1,
            "configuration_identity",
            json!({
                "symbol": "SOL", "strategy_name": "sol_1h_sma10x30_5m_range_or_breakout",
                "strategy_params": {"leverage": 5.0}, "execution": {"order_type": "market"}
            }),
        ),
        asset_event(
            2,
            "regime_decision",
            json!({
                "decision_time_ms": 1_785_499_500_000_u64, "reference_price": 73.10,
                "long_entry": true, "short_entry": false, "long_exit": false, "short_exit": false,
                "primary_regime": "BREAKOUT", "state_1m": "BREAKOUT", "state_5m": "TREND_UP",
                "context_15m": "TREND_UP", "confidence": 0.82, "structural_direction": "long",
                "regime_admitted": true, "decision_action": "enter_long"
            }),
        ),
        asset_event(
            3,
            "fill",
            json!({
                "oid": 101, "venue_timestamp_ms": 1_785_499_501_000_u64, "price": 73.10, "size": 0.30,
                "side": "B", "direction": "Open Long", "closed_pnl_usd": 0.0, "fee_usd": 0.00987
            }),
        ),
        asset_event(
            4,
            "position",
            json!({
                "size_signed": 0.30, "entry_price": 73.10, "margin_used_usd": 4.386,
                "position_value_usd": 22.2, "unrealized_pnl_usd": 0.27, "leverage": 5.0
            }),
        ),
        venue_orders(5, 202, 72.515),
        open_state(6, 202),
        asset_event(
            7,
            "book_observation",
            json!({
                "source": "hyperliquid_mainnet_l2_rest", "exchange_ts_ms": 1_785_502_802_000_u64,
                "recv_ts_ms": 1_785_502_802_010_u64, "mid_px": 73.675, "spread_bps": 1.3577,
                "bid_depth_ratio": 1.6667, "opi": 0.25,
                "bids": [{"price": 73.67, "size": 10.0}], "asks": [{"price": 73.68, "size": 6.0}]
            }),
        ),
    ]
}

fn asset_dashboard(journal: &[String]) -> (BackendTelemetrySnapshot, String) {
    let telemetry = parse_backend_telemetry(&journal.join("\n")).expect("asset journal");
    let mut app = App::new("SOL".into(), "1m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry.clone());
    let mut terminal = Terminal::new(TestBackend::new(180, 52)).expect("terminal");
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw asset dashboard");
    let buffer = terminal.backend().buffer();
    let text = (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n");
    (telemetry, text)
}

#[test]
fn asset_journal_follows_a_raised_stop_the_venue_lists() {
    let mut journal = open_asset_journal();
    journal.extend([
        asset_event(8, "order_intent", json!({
            "operation": "raise_protective_stop", "client_order_id": "0x18b866944864c62356ffbc4951b08baf",
            "oid": 202, "position_size_signed": 0.30, "trigger_price": 73.29
        })),
        raise_ack(9, "protective_stop_raise", "resting"),
        open_state(10, 303),
        venue_orders(11, 303, 73.29),
        raised_event(12),
    ]);

    let (telemetry, dashboard) = asset_dashboard(&journal);

    assert_eq!(telemetry.live_state.as_deref(), Some("OPEN"));
    assert_eq!(telemetry.protective_stop_oid, Some(303));
    assert_eq!(telemetry.protective_stop_price, Some(73.29));
    assert_eq!(telemetry.protective_stop_status.as_deref(), Some("RESTING"));
    assert!(
        dashboard.contains("STOP $73.29 OID 303 RESTING"),
        "{dashboard}"
    );
    assert!(!dashboard.contains("OID 202"), "{dashboard}");
    assert!(!dashboard.contains("STOP NOT CONFIRMED"), "{dashboard}");
}

#[test]
fn restart_recovered_raise_shows_its_acknowledged_trigger_before_the_venue_lists_it() {
    let mut journal = open_asset_journal();
    journal.extend([
        raise_ack(8, "protective_stop_raise_restart_recovery", "open"),
        raised_event(9),
        open_state(10, 303),
    ]);

    let (telemetry, dashboard) = asset_dashboard(&journal);

    assert_eq!(telemetry.protective_stop_oid, Some(303));
    assert_eq!(telemetry.protective_stop_price, Some(73.29));
    assert_eq!(telemetry.protective_stop_status.as_deref(), Some("OPEN"));
    assert!(
        dashboard.contains("STOP $73.29 OID 303 OPEN"),
        "{dashboard}"
    );
    assert!(!dashboard.contains("$72.52"), "{dashboard}");
}
