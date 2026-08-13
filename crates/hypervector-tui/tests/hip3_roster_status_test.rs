use hypervector_tui::backend_hip3_roster::parse_hip3_roster_status;

#[test]
fn parses_complete_report_only_roster_without_aliasing_wti() {
    let status = parse_hip3_roster_status(&fixture("none", true))
        .expect("valid report-only HIP-3 checkpoint");

    assert!(status.available);
    assert_eq!(status.markets.len(), 2);
    assert_eq!(status.markets[0].symbol, "xyz:SP500");
    assert_eq!(status.markets[0].book.bid_levels, 20);
    assert_eq!(status.markets[0].book.ask_levels, 20);
    assert_eq!(status.markets[0].venue.taker_fee_rate, Some(0.0000864));
    assert_eq!(status.markets[1].venue.taker_fee_rate, None);
    let alias = status.wti_alias.expect("WTIOIL alias state");
    assert_eq!(alias.historical_symbol, "cash:WTI");
    assert_eq!(alias.active_alternative, "xyz:BRENTOIL");
    assert!(!alias.equivalence_assumed);
    assert_eq!(alias.live_symbol, None);
}

#[test]
fn rejects_checkpoint_that_claims_execution_authority() {
    let error = parse_hip3_roster_status(&fixture("hyperliquid_mainnet", true))
        .expect_err("execution-capable roster must be rejected");

    assert!(error.contains("report-only contract"));
}

#[test]
fn rejects_market_identity_or_level_count_mismatch() {
    let error = parse_hip3_roster_status(&fixture("none", false))
        .expect_err("incomplete book must not look available");

    assert!(error.contains("level count"));
}

fn fixture(execution_authority: &str, complete_book: bool) -> String {
    let bid_levels = if complete_book { 20 } else { 19 };
    format!(
        r#"{{
          "schema_version":1,
          "mode":"hip3_roster_observer_checkpoint",
          "status":"available",
          "observed_at_utc":"2026-08-06T18:36:16.986925+00:00",
          "active_symbols":["xyz:SP500","xyz:GOLD"],
          "markets":[
            {{
              "symbol":"xyz:SP500","venue_namespace":"xyz",
              "venue":{{"mark_price":7713.65,"max_leverage":50,
                "effective_fee_status":"resolved","maker_fee_rate":0.0000288,
                "taker_fee_rate":0.0000864}},
              "book":{{"exchange_timestamp_ms":1786041106711,"mid_price":7714.2,
                "spread_bps":0.259,"level_count":{{"bids":{bid_levels},"asks":20}},
                "depth_5":{{"order_pressure":-0.04}},
                "depth_20":{{"order_pressure":-0.23}}}},
              "account":{{"open_order_count":0,
                "position":{{"size_signed":0.0}}}}
            }},
            {{
              "symbol":"xyz:GOLD","venue_namespace":"xyz",
              "venue":{{"mark_price":4247.25,"max_leverage":25,
                "effective_fee_status":"unresolved_growth_mode",
                "maker_fee_rate":null,"taker_fee_rate":null}},
              "book":{{"exchange_timestamp_ms":1786041116962,"mid_price":4247.25,
                "spread_bps":0.235,"level_count":{{"bids":20,"asks":20}},
                "depth_5":{{"order_pressure":-0.25}},
                "depth_20":{{"order_pressure":-0.07}}}},
              "account":{{"open_order_count":0,
                "position":{{"size_signed":0.0}}}}
            }}
          ],
          "requested_aliases":{{"WTIOIL":{{"status":"historical_only",
            "live_symbol":null,"historical_symbol":"cash:WTI",
            "active_alternative":"xyz:BRENTOIL","equivalence_assumed":false}}}},
          "execution_authority":"{execution_authority}",
          "report_only":true,"automatic_promotion":false,
          "runtime_strategy_changed":false,"signing_client_constructed":false,
          "lifecycle":"running","polls":32
        }}"#,
    )
}
