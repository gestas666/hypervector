use hypervector_tui::backend_cohort::CohortAssetSnapshot;

fn mixed_timestamp_asset() -> CohortAssetSnapshot {
    serde_json::from_str(
        r#"{
            "symbol":"BTC",
            "state":"OPEN",
            "direction_capability":["long","short"],
            "position_size_signed":2.0,
            "position_side":"long",
            "entry_oid":1,
            "stop_oid":2,
            "target_oid":3,
            "target_price":110.0,
            "execution_plan":null,
            "last_fault":null,
            "mark_price":95.0,
            "entry_price":100.0,
            "liquidation_price":80.0,
            "liquidation_distance_pct":15.0,
            "margin_used_usd":40.4,
            "position_value_usd":202.0,
            "unrealized_pnl_usd":2.0,
            "leverage":5,
            "fees_net_usd":0.1,
            "funding_net_usd":0.0,
            "realized_pnl_usd":0.0,
            "fill_count":1,
            "cost_scope":"run_to_date"
        }"#,
    )
    .expect("fixture must deserialize")
}

#[test]
fn position_economics_use_venue_synchronous_mark() {
    let mut asset = mixed_timestamp_asset();

    asset
        .reconcile_position_mark()
        .expect("position mark should reconcile");

    assert_eq!(asset.mark_price, Some(101.0));
    assert_eq!(asset.market_reference_price, Some(95.0));
    assert_eq!(
        asset.mark_price_source.as_deref(),
        Some("venue_position_value_div_size")
    );
    let distance = asset
        .liquidation_distance_pct
        .expect("liquidation distance must exist");
    assert!((distance - 20.792_079_2).abs() < 1e-8);
}
