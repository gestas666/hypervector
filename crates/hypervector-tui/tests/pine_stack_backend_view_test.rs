//! Four-Pine backend observer acceptance tests for the read-only TUI.

use hypervector_tui::{App, backend_telemetry::parse_backend_telemetry};
use ratatui::{Terminal, backend::TestBackend};

const LEDGER: &str = r#"{"schema_version":1,"strategy_name":"pine_stack_eth30_forward_observer_v1","candidate_status":"historical_pseudo_holdout_failed_forward_observer","run_id":"pine-eth30-test","symbol":"ETH","execution_mode":"observe","live_enabled":false,"live_armed":false,"execution_authority":"none","submitted":false,"place_attempted":false,"portfolio_purpose":"zero_capital_forward_observation","strategy_params":{"cs_atr_period":10,"cs_sensitivity":5.0,"trend_lookback":30,"sentiment_role":"annotation_only","tp_pivot_width":5,"tp_bins":5,"tp_minimum_directional_pool":50,"tp_time_of_day_axis":false},"position_policy":{"max_positions_per_symbol":0},"risk":{"capital_usd":0.0,"notional_usd":0.0},"exits":{"research_control":"cs_flip_or_8h_hold","stop_margin_pct":10.0},"execution":{"authority":"none","next_bar_model":"next_30m_open"},"costs":{"status":"not_applicable_zero_capital_observer"},"regime_policy":{"engine":"four_pine_completed_30m_observer_v1","classification":"NOT_A_CANONICAL_REGIME_CLASSIFIER","signal_timeframe":"30m","execution_timeframe":"not_applicable_observer"},"feed_ts":"2026-08-01T12:00:00Z","action":"session_start","activated_at_utc":"2026-08-01T12:00:00Z"}
{"schema_version":1,"strategy_name":"pine_stack_eth30_forward_observer_v1","candidate_status":"historical_pseudo_holdout_failed_forward_observer","run_id":"pine-eth30-test","symbol":"ETH","execution_mode":"observe","live_enabled":false,"live_armed":false,"execution_authority":"none","submitted":false,"place_attempted":false,"portfolio_purpose":"zero_capital_forward_observation","strategy_params":{"cs_atr_period":10,"cs_sensitivity":5.0,"trend_lookback":30,"sentiment_role":"annotation_only","tp_pivot_width":5,"tp_bins":5,"tp_minimum_directional_pool":50,"tp_time_of_day_axis":false},"position_policy":{"max_positions_per_symbol":0},"risk":{"capital_usd":0.0,"notional_usd":0.0},"exits":{"research_control":"cs_flip_or_8h_hold","stop_margin_pct":10.0},"execution":{"authority":"none","next_bar_model":"next_30m_open"},"costs":{"status":"not_applicable_zero_capital_observer"},"regime_policy":{"engine":"four_pine_completed_30m_observer_v1","classification":"NOT_A_CANONICAL_REGIME_CLASSIFIER","signal_timeframe":"30m","execution_timeframe":"not_applicable_observer"},"feed_ts":"2026-08-01T12:30:00Z","action":"regime_history","primary_regime":"NOT_CLASSIFIED","regime_reason":"no_cs_onset","decision_action":"history_only","entry_direction":null,"entry_allowed":false,"pine_candidate_entry":false,"open":3500.0,"high":3520.0,"low":3490.0,"close":3510.0,"volume":1200.0,"mark_px":3510.0,"pine_cs_state":-1,"pine_cs_selected_factor":4.5,"pine_cs_trailing_stop":3530.0,"pine_cs_long_onset":false,"pine_cs_short_onset":false,"pine_trend_state":-1,"pine_trend_episode_bars":8,"pine_trend_episode_high":3550.0,"pine_trend_episode_low":3480.0,"pine_trend_episode_mid":3515.0,"pine_trend_delta_pct":-20.0,"pine_trend_ambiguous":false,"pine_sentiment_score":44.0,"pine_sentiment_support":11,"pine_sentiment_components":{"rsi":42.0,"stochastic":40.0,"stochastic_rsi":38.0,"cci":45.0,"bull_bear_power":41.0,"moving_average":43.0,"vwap":46.0,"bollinger":47.0,"supertrend":39.0,"linear_regression":50.0,"market_structure":53.0},"pine_tp_density_raw":72.0,"pine_tp_density_score":null,"pine_tp_directional_pool":42,"pine_tp_minimum_support":4,"pine_tp_insufficient_support":true,"pine_tp_relative_volume":70.0,"pine_tp_time_of_day":null,"pine_tp_range_position":74.0,"pine_tp_score_semantics":"density_match_not_probability"}
{"schema_version":1,"strategy_name":"pine_stack_eth30_forward_observer_v1","candidate_status":"historical_pseudo_holdout_failed_forward_observer","run_id":"pine-eth30-test","symbol":"ETH","execution_mode":"observe","live_enabled":false,"live_armed":false,"execution_authority":"none","submitted":false,"place_attempted":false,"portfolio_purpose":"zero_capital_forward_observation","strategy_params":{"cs_atr_period":10,"cs_sensitivity":5.0,"trend_lookback":30,"sentiment_role":"annotation_only","tp_pivot_width":5,"tp_bins":5,"tp_minimum_directional_pool":50,"tp_time_of_day_axis":false},"position_policy":{"max_positions_per_symbol":0},"risk":{"capital_usd":0.0,"notional_usd":0.0},"exits":{"research_control":"cs_flip_or_8h_hold","stop_margin_pct":10.0},"execution":{"authority":"none","next_bar_model":"next_30m_open"},"costs":{"status":"not_applicable_zero_capital_observer"},"regime_policy":{"engine":"four_pine_completed_30m_observer_v1","classification":"NOT_A_CANONICAL_REGIME_CLASSIFIER","signal_timeframe":"30m","execution_timeframe":"not_applicable_observer"},"feed_ts":"2026-08-01T13:00:00Z","action":"regime_observation","primary_regime":"NOT_CLASSIFIED","regime_reason":"cs_long_onset_trend_aligned","decision_action":"observe_long_onset","entry_direction":"long","entry_allowed":true,"pine_candidate_entry":true,"open":3510.0,"high":3560.0,"low":3500.0,"close":3550.0,"volume":1600.0,"mark_px":3550.0,"pine_cs_state":1,"pine_cs_selected_factor":5.0,"pine_cs_trailing_stop":3495.0,"pine_cs_long_onset":true,"pine_cs_short_onset":false,"pine_trend_state":1,"pine_trend_episode_bars":1,"pine_trend_episode_high":3560.0,"pine_trend_episode_low":3500.0,"pine_trend_episode_mid":null,"pine_trend_delta_pct":null,"pine_trend_ambiguous":false,"pine_sentiment_score":61.0,"pine_sentiment_support":11,"pine_sentiment_components":{"rsi":62.0,"stochastic":65.0,"stochastic_rsi":63.0,"cci":58.0,"bull_bear_power":60.0,"moving_average":64.0,"vwap":59.0,"bollinger":57.0,"supertrend":66.0,"linear_regression":61.0,"market_structure":56.0},"pine_tp_density_raw":84.0,"pine_tp_density_score":84.0,"pine_tp_directional_pool":55,"pine_tp_minimum_support":8,"pine_tp_insufficient_support":false,"pine_tp_relative_volume":82.0,"pine_tp_time_of_day":null,"pine_tp_range_position":86.0,"pine_tp_score_semantics":"density_match_not_probability"}"#;

#[test]
fn pine_projection_preserves_all_four_backend_components() {
    let telemetry = parse_backend_telemetry(LEDGER).expect("Pine telemetry");

    assert!(telemetry.is_pine_stack());
    assert_eq!(telemetry.pine_stack.cs_state, Some(1));
    assert_eq!(telemetry.pine_stack.trend_state, Some(1));
    assert_eq!(telemetry.pine_stack.sentiment_score, Some(61.0));
    assert_eq!(telemetry.pine_stack.sentiment_components.len(), 11);
    assert_eq!(telemetry.pine_stack.tp_density_score, Some(84.0));
    assert_eq!(telemetry.pine_stack.tp_directional_pool, Some(55));
    assert_eq!(telemetry.execution_authority.as_deref(), Some("none"));
    assert_eq!(telemetry.live_armed, Some(false));
}

#[test]
fn pine_signal_and_chart_screens_state_observer_truth() {
    let telemetry = parse_backend_telemetry(LEDGER).expect("Pine telemetry");
    let mut app = App::new("ETH".into(), "30m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 54);
    let mut terminal = Terminal::new(backend).expect("terminal");

    app.active_tab = 1;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Pine screen");
    let signal = rendered(&terminal);
    assert!(
        signal.contains("FOUR-PINE 30m FORWARD OBSERVER"),
        "{signal}"
    );
    assert!(signal.contains("CS ADAPTIVE SUPERTREND"), "{signal}");
    assert!(signal.contains("TREND LEVELS"), "{signal}");
    assert!(
        signal.contains("MARKET SENTIMENT · ANNOTATION ONLY"),
        "{signal}"
    );
    assert!(
        signal.contains("DENSITY MATCH · NOT PROBABILITY"),
        "{signal}"
    );
    assert!(signal.contains("PSEUDO-HOLDOUT FAILED"), "{signal}");
    assert!(!signal.contains("LIVE ARMED"), "{signal}");

    app.active_tab = 2;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Pine chart");
    let chart = rendered(&terminal);
    assert!(chart.contains("PINE STACK · BACKEND OBSERVER"), "{chart}");
    assert!(chart.contains("CS-STOP $3495.00"), "{chart}");
    assert!(chart.contains("T-HI $3560.00"), "{chart}");
    assert!(chart.contains("ZERO CAPITAL"), "{chart}");
}

#[test]
fn pine_dashboard_and_config_do_not_invent_execution_authority() {
    let telemetry = parse_backend_telemetry(LEDGER).expect("Pine telemetry");
    let mut app = App::new("ETH".into(), "30m".into(), vec![], true, false);
    app.apply_backend_telemetry(telemetry);
    let backend = TestBackend::new(180, 54);
    let mut terminal = Terminal::new(backend).expect("terminal");

    app.active_tab = 0;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Pine dashboard");
    let dashboard = rendered(&terminal);
    assert!(dashboard.contains("ZERO CAPITAL"), "{dashboard}");
    assert!(dashboard.contains("PSEUDO-HOLDOUT FAILED"), "{dashboard}");
    assert!(!dashboard.contains("LIVE ARMED"), "{dashboard}");
    assert!(!dashboard.contains("ELIGIBLE LEVERAGE"), "{dashboard}");

    app.active_tab = 3;
    terminal
        .draw(|frame| hypervector_tui::ui::draw(frame, &app))
        .expect("draw Pine config");
    let config = rendered(&terminal);
    assert!(!config.contains("cs_atr_period"), "{config}");
    assert!(config.contains("ATR period"), "{config}");
    assert!(config.contains("annotation_only"), "{config}");
    assert!(config.contains("xyz:SP500 HIP-3"), "{config}");
    assert!(config.contains("deferred"), "{config}");
}

fn rendered(terminal: &Terminal<TestBackend>) -> String {
    let buffer = terminal.backend().buffer();
    (0..buffer.area.height)
        .map(|y| {
            (0..buffer.area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}
