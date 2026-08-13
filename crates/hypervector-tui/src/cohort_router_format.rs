//! Human-readable labels for backend-authored cohort readiness tokens.

pub(crate) fn human_token(value: &str) -> String {
    match value {
        "awaiting_squeeze_release" => "WAITING SQUEEZE RELEASE".into(),
        "squeeze_not_armed" => "SQUEEZE NOT ARMED".into(),
        "ema_supertrend_not_aligned" => "EMA/ST MISALIGNED".into(),
        "adx_below_usable" => "ADX BELOW MIN".into(),
        "heikin_ashi_choppy" => "HA CHOPPY".into(),
        "volume_not_above_1x" => "VOLUME <= 1X".into(),
        "money_flow_not_aligned" => "FLOW MISALIGNED".into(),
        "hourly_sma_warmup" => "SMA WARMUP".into(),
        "5m_regime_not_admitted" => "5M REGIME BLOCKED".into(),
        "awaiting_hourly_sma_cross" => "WAITING HOURLY CROSS".into(),
        "indicator_telemetry_unavailable" => "TELEMETRY UNAVAILABLE".into(),
        "regime_not_admitted" => "REGIME BLOCKED".into(),
        "entry_condition_absent" => "NO ENTRY CONDITION".into(),
        "entry_signal_present" => "ENTRY SIGNAL".into(),
        "awaiting_primary_onset" => "WAITING 5M PRIMARY ONSET".into(),
        "source_primary_not_directional" => "5M SOURCE NOT DIRECTIONAL".into(),
        "source_confidence_below_minimum" => "SOURCE CONFIDENCE BELOW MIN".into(),
        "source_range_below_minimum" => "5M RANGE BELOW MIN".into(),
        "source_range_above_maximum" => "5M RANGE ABOVE MAX".into(),
        "5m_not_breakout" => "WAITING 5M BREAKOUT".into(),
        "awaiting_new_5m_breakout_onset" => "WAITING FRESH 5M BREAKOUT".into(),
        "structural_direction_neutral" => "STRUCTURE NEUTRAL".into(),
        _ => value.replace('_', " ").to_uppercase(),
    }
}
