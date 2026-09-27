//! Display binding of acknowledged venue stop raises to open checkpoint lifecycles.
//!
//! The analysis checkpoint attributes an open lifecycle's protective stop to its
//! initial placement. When the backend later moves that stop toward the profit
//! floor, the authoritative ledger carries the acknowledgement
//! (`breakeven_stop_attempt`) and the venue-backed replacement oid
//! (`cohort_snapshot`). Binding the two here changes only what the cockpit shows.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::backend_cohort::{BackendCohortTelemetry, CohortAssetSnapshot};
use crate::backend_cohort_open_profit_protection::StopMove;
use crate::backend_cohort_open_trade_reflection::{CohortOpenStopRaise, CohortOpenTradeReflection};
use crate::backend_telemetry::LedgerRow;

const RAISE_ATTEMPT_EVENT: &str = "breakeven_stop_attempt";

/// Latest backend acknowledgement that one lifecycle's stop moved to, or already sat at, its raise target.
///
/// This is the engine's own claim; venue coverage of the replacement stop is
/// checked separately against the cohort snapshot before anything is displayed.
#[derive(Debug, Clone, PartialEq)]
pub struct CohortVenueStopRaise {
    pub symbol: String,
    pub entry_oid: u64,
    pub trigger_price: f64,
    /// The engine found the owned stop already at the target and sent no venue call.
    pub already_at_target: bool,
}

#[derive(Debug, Deserialize)]
struct RawRaiseAttempt {
    symbol: String,
    entry_oid: u64,
    trigger_price: f64,
    raised: bool,
    #[serde(default)]
    already_at_target: bool,
}

/// Keep each lifecycle's latest acknowledged raise from this run's ledger rows.
///
/// These acknowledgements only change what the cockpit shows. If any attempt row
/// fails validation, all of the run's raise evidence is withdrawn rather than
/// failing the cohort view: each open lifecycle then keeps the checkpoint's own
/// stop attribution, which never shows more protection than was evidenced.
pub(crate) fn project_stop_raises(
    rows: &[&LedgerRow],
    enabled_symbols: &[String],
) -> Vec<CohortVenueStopRaise> {
    parse_stop_raises(rows, enabled_symbols).unwrap_or_default()
}

/// Validate every attempt row; only a raised stop, or one the engine found
/// already resting at the target, is evidence that the venue stop moved.
fn parse_stop_raises(
    rows: &[&LedgerRow],
    enabled_symbols: &[String],
) -> Result<Vec<CohortVenueStopRaise>, String> {
    let mut latest = BTreeMap::new();
    for row in rows.iter().filter(|row| row.action == RAISE_ATTEMPT_EVENT) {
        let payload = row
            .extra
            .get("payload")
            .cloned()
            .ok_or_else(|| "breakeven stop attempt is missing its payload".to_string())?;
        let raw: RawRaiseAttempt = serde_json::from_value(payload)
            .map_err(|error| format!("invalid breakeven stop attempt payload: {error}"))?;
        let invalid = !enabled_symbols.contains(&raw.symbol)
            || raw.entry_oid == 0
            || !raw.trigger_price.is_finite()
            || raw.trigger_price <= 0.0
            || (raw.raised && raw.already_at_target);
        if invalid {
            return Err("breakeven stop attempt is structurally invalid".into());
        }
        if !raw.raised && !raw.already_at_target {
            continue;
        }
        latest.insert(
            (raw.symbol.clone(), raw.entry_oid),
            CohortVenueStopRaise {
                symbol: raw.symbol,
                entry_oid: raw.entry_oid,
                trigger_price: raw.trigger_price,
                already_at_target: raw.already_at_target,
            },
        );
    }
    Ok(latest.into_values().collect())
}

struct BoundRaise {
    direction: f64,
    stop_oid: u64,
    trigger_price: f64,
    previous_oid: u64,
    previous_trigger_price: f64,
    already_at_target: bool,
}

/// Show each open lifecycle's acknowledged venue raise instead of its initial stop.
///
/// A lifecycle is rebound only when the checkpoint, the ledger's latest asset state
/// and the acknowledgement name the same symbol, side and entry order; the covering
/// venue stop has replaced the checkpoint's stop; and the acknowledged trigger is
/// strictly more protective than both that stop and the venue entry. Otherwise the
/// checkpoint's own attribution is left untouched.
pub(crate) fn apply_venue_stop_raises(
    cohort: &BackendCohortTelemetry,
    reflections: &mut [CohortOpenTradeReflection],
) {
    for trade in reflections {
        if let Some(bound) = bind_raise(cohort, trade) {
            rebind_stop(trade, &bound);
        }
    }
}

fn bind_raise(
    cohort: &BackendCohortTelemetry,
    trade: &CohortOpenTradeReflection,
) -> Option<BoundRaise> {
    let entry_oid = lifecycle_entry_oid(&trade.lifecycle_id, &trade.symbol)?;
    let direction = side_direction(&trade.side)?;
    let asset = cohort
        .assets
        .iter()
        .find(|asset| asset.symbol == trade.symbol)?;
    let stop_oid = covering_stop_oid(asset, entry_oid, &trade.side)?;
    let (previous_oid, previous_trigger_price) =
        (trade.protective_stop_oid?, trade.protective_stop_price?);
    if stop_oid == previous_oid {
        return None;
    }
    let raise = cohort
        .venue_stop_raises
        .iter()
        .find(|raise| raise.symbol == trade.symbol && raise.entry_oid == entry_oid)?;
    let entry_price = asset.entry_price?;
    let protective = direction * (raise.trigger_price - previous_trigger_price) > 0.0
        && direction * (raise.trigger_price - entry_price) > 0.0;
    protective.then_some(BoundRaise {
        direction,
        stop_oid,
        trigger_price: raise.trigger_price,
        previous_oid,
        previous_trigger_price,
        already_at_target: raise.already_at_target,
    })
}

fn rebind_stop(trade: &mut CohortOpenTradeReflection, bound: &BoundRaise) {
    let repriced = trade.entry_size.and_then(|entry_size| {
        trade.profit_protection.as_ref()?.repriced(&StopMove {
            direction: bound.direction,
            entry_size,
            mark_price: trade.mark_price,
            previous_trigger_price: bound.previous_trigger_price,
            trigger_price: bound.trigger_price,
        })
    });
    trade.profit_protection = repriced;
    trade.protective_stop_oid = Some(bound.stop_oid);
    trade.protective_stop_price = Some(bound.trigger_price);
    trade.protective_stop_raise = Some(CohortOpenStopRaise {
        previous_oid: bound.previous_oid,
        previous_trigger_price: bound.previous_trigger_price,
        already_at_target: bound.already_at_target,
    });
}

/// Entry oid of a `{symbol}:{entry_oid}` lifecycle id, in the backend's canonical form only.
fn lifecycle_entry_oid(lifecycle_id: &str, symbol: &str) -> Option<u64> {
    let (prefix, oid) = lifecycle_id.rsplit_once(':')?;
    if prefix != symbol || !oid.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    oid.parse::<u64>()
        .ok()
        .filter(|value| *value > 0 && value.to_string() == oid)
}

fn side_direction(side: &str) -> Option<f64> {
    match side {
        "long" => Some(1.0),
        "short" => Some(-1.0),
        _ => None,
    }
}

fn covering_stop_oid(asset: &CohortAssetSnapshot, entry_oid: u64, side: &str) -> Option<u64> {
    let bound = asset.state == "OPEN"
        && asset.entry_oid == Some(entry_oid)
        && asset.position_side.as_deref() == Some(side)
        && asset.stop_protection.as_deref() == Some("covering");
    asset.stop_oid.filter(|_| bound)
}

#[cfg(test)]
mod tests {
    use serde_json::{Value, json};

    use super::*;
    use crate::backend_cohort_open_profit_protection::CohortOpenProfitProtection;
    use crate::backend_live_projection::normalize_live_event;

    const SYMBOL: &str = "xyz:BRENTOIL";
    const ENTRY_OID: u64 = 555_018_656_094;
    const INITIAL_STOP_OID: u64 = 555_018_726_035;
    const RAISED_STOP_OID: u64 = 555_530_692_113;

    fn enabled() -> Vec<String> {
        vec!["BTC".into(), SYMBOL.into()]
    }

    fn attempt(payload: Value) -> LedgerRow {
        serde_json::from_value(normalize_live_event(json!({
            "event_type": "breakeven_stop_attempt",
            "observed_at_utc": "2026-09-24T16:56:43.632642+00:00",
            "run_id": "run-a",
            "payload": payload
        })))
        .expect("ledger row")
    }

    fn asset(overrides: Value) -> CohortAssetSnapshot {
        let mut value = json!({
            "symbol": SYMBOL,
            "state": "OPEN",
            "direction_capability": ["long", "short"],
            "position_size_signed": 5.84,
            "position_side": "long",
            "entry_oid": ENTRY_OID,
            "stop_oid": RAISED_STOP_OID,
            "target_oid": null,
            "target_price": null,
            "execution_plan": null,
            "last_fault": null,
            "mark_price": 99.9765,
            "entry_price": 99.05,
            "liquidation_price": 88.86,
            "liquidation_distance_pct": 11.1,
            "margin_used_usd": 78.0,
            "position_value_usd": 583.86,
            "unrealized_pnl_usd": 5.41,
            "leverage": 8,
            "fees_net_usd": 0.05,
            "funding_net_usd": -0.002567,
            "realized_pnl_usd": 0.0,
            "fill_count": 1,
            "opened_at_ms": 1_790_236_800_000_u64,
            "protective_exit_pending": false,
            "partial_exit_fill_count": 0,
            "partial_exit_size": 0.0,
            "stop_protection": "covering"
        });
        for (key, field) in overrides.as_object().expect("overrides") {
            value[key] = field.clone();
        }
        serde_json::from_value(value).expect("asset snapshot")
    }

    fn raise(trigger_price: f64, already_at_target: bool) -> CohortVenueStopRaise {
        CohortVenueStopRaise {
            symbol: SYMBOL.into(),
            entry_oid: ENTRY_OID,
            trigger_price,
            already_at_target,
        }
    }

    fn cohort(
        asset: CohortAssetSnapshot,
        raises: Vec<CohortVenueStopRaise>,
    ) -> BackendCohortTelemetry {
        BackendCohortTelemetry {
            enabled_symbols: enabled(),
            assets: vec![asset],
            venue_stop_raises: raises,
            ..BackendCohortTelemetry::default()
        }
    }

    /// Backend estimate for the initial stop at 97.554 (mark 99.9765, 5.84 @ 99.05).
    fn open_trade() -> CohortOpenTradeReflection {
        CohortOpenTradeReflection {
            lifecycle_id: format!("{SYMBOL}:{ENTRY_OID}"),
            symbol: SYMBOL.into(),
            side: "long".into(),
            entry_size: Some(5.84),
            protective_stop_oid: Some(INITIAL_STOP_OID),
            protective_stop_price: Some(97.554),
            profit_protection: Some(CohortOpenProfitProtection {
                status: "open_profit_unprotected".into(),
                estimated_exit_now_net_usd: 5.307769975257308,
                estimated_stop_net_usd: -8.838407701195626,
                marked_to_stop_giveback_usd: 14.146177676452934,
                protected_profit_fraction: Some(0.0),
                stop_distance_from_mark_bps: 242.30694213140083,
                measured_entry_fee_rate_bps: 0.8639916500992931,
                estimated_stop_exit_fee_usd: 0.049222931397331283,
            }),
            mark_price: 99.9765,
            active_lifecycle_marked_net_pnl_usd: 5.358215230201701,
            ..CohortOpenTradeReflection::default()
        }
    }

    fn rebound(cohort: &BackendCohortTelemetry) -> CohortOpenTradeReflection {
        let mut trades = [open_trade()];
        apply_venue_stop_raises(cohort, &mut trades);
        let [trade] = trades;
        trade
    }

    #[test]
    fn keeps_each_lifecycles_latest_acknowledged_raise() {
        let rows = [
            attempt(
                json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "attempt": 1, "trigger_price": 99.2, "raised": false}),
            ),
            attempt(
                json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "attempt": 2, "trigger_price": 99.297625, "raised": true}),
            ),
            attempt(
                json!({"symbol": "BTC", "entry_oid": 7, "attempt": 0, "trigger_price": 64_100.0, "raised": false, "already_at_target": true, "breakeven_stop_target": "floor", "executable_price": 64_400.0}),
            ),
            attempt(
                json!({"symbol": "BTC", "entry_oid": 8, "attempt": 3, "trigger_price": 64_000.0, "raised": false}),
            ),
        ];
        let rows = rows.iter().collect::<Vec<_>>();

        let raises = project_stop_raises(&rows, &enabled());

        assert_eq!(
            raises,
            vec![
                CohortVenueStopRaise {
                    symbol: "BTC".into(),
                    entry_oid: 7,
                    trigger_price: 64_100.0,
                    already_at_target: true,
                },
                raise(99.297625, false),
            ]
        );
    }

    #[test]
    fn invalid_raise_attempt_withdraws_the_runs_raise_evidence() {
        let valid = attempt(
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "attempt": 1, "trigger_price": 99.297625, "raised": true}),
        );
        for payload in [
            json!({"symbol": "ETH", "entry_oid": ENTRY_OID, "trigger_price": 99.3, "raised": true}),
            json!({"symbol": SYMBOL, "entry_oid": 0, "trigger_price": 99.3, "raised": true}),
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "trigger_price": 0.0, "raised": true}),
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "trigger_price": 99.3, "raised": true, "already_at_target": true}),
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "trigger_price": 99.3}),
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "trigger_price": 99.3, "raised": "ALREADY_AT_TARGET"}),
            json!({"symbol": SYMBOL, "entry_oid": ENTRY_OID, "trigger_price": null, "raised": true}),
            json!({"symbol": SYMBOL, "entry_oid": null, "trigger_price": 99.3, "raised": true}),
        ] {
            let invalid = attempt(payload.clone());

            let error = parse_stop_raises(&[&invalid], &enabled()).expect_err("invalid attempt");
            assert!(
                error.contains("breakeven stop attempt"),
                "{payload}: {error}"
            );
            for rows in [[&valid, &invalid], [&invalid, &valid]] {
                assert_eq!(
                    project_stop_raises(&rows, &enabled()),
                    Vec::new(),
                    "{payload}"
                );
            }
        }
    }

    #[test]
    fn acknowledged_raise_replaces_the_initial_stop_and_reprices_the_lock() {
        let trade = rebound(&cohort(asset(json!({})), vec![raise(99.297625, false)]));

        assert_eq!(trade.protective_stop_oid, Some(RAISED_STOP_OID));
        assert_eq!(trade.protective_stop_price, Some(99.297625));
        assert_eq!(
            trade.protective_stop_raise,
            Some(CohortOpenStopRaise {
                previous_oid: INITIAL_STOP_OID,
                previous_trigger_price: 97.554,
                already_at_target: false,
            })
        );
        let protection = trade.profit_protection.expect("repriced protection");
        assert_eq!(protection.status, "partial_profit_locked");
        assert!((protection.estimated_stop_net_usd - 1.3434825159788528).abs() < 1e-9);
        assert!(
            (protection.protected_profit_fraction.expect("lock") - 0.2531161904607074).abs() < 1e-9
        );
    }

    #[test]
    fn stop_found_at_target_after_restart_is_also_shown_as_raised() {
        let trade = rebound(&cohort(asset(json!({})), vec![raise(99.297625, true)]));

        assert_eq!(trade.protective_stop_oid, Some(RAISED_STOP_OID));
        assert!(
            trade
                .protective_stop_raise
                .expect("raise")
                .already_at_target
        );
    }

    #[test]
    fn unverifiable_reprice_basis_withholds_the_stale_lock_estimate() {
        let mut trades = [CohortOpenTradeReflection {
            entry_size: None,
            ..open_trade()
        }];

        apply_venue_stop_raises(
            &cohort(asset(json!({})), vec![raise(99.297625, false)]),
            &mut trades,
        );

        assert_eq!(trades[0].protective_stop_oid, Some(RAISED_STOP_OID));
        assert_eq!(trades[0].profit_protection, None);
    }

    #[test]
    fn mismatched_evidence_keeps_the_checkpoint_attribution() {
        let cases = [
            (
                "another lifecycle's entry",
                asset(json!({"entry_oid": 1})),
                raise(99.297625, false),
            ),
            (
                "uncovered venue stop",
                asset(json!({"stop_protection": "missing"})),
                raise(99.297625, false),
            ),
            (
                "exit in progress",
                asset(json!({"state": "EXIT_PENDING"})),
                raise(99.297625, false),
            ),
            (
                "opposite venue side",
                asset(json!({"position_side": "short", "position_size_signed": -5.84})),
                raise(99.297625, false),
            ),
            (
                "venue still shows the initial stop",
                asset(json!({"stop_oid": INITIAL_STOP_OID})),
                raise(99.297625, false),
            ),
            (
                "raise below the initial stop",
                asset(json!({})),
                raise(97.0, false),
            ),
            (
                "raise not beyond entry",
                asset(json!({})),
                raise(99.0, false),
            ),
            (
                "raise for another entry",
                asset(json!({})),
                CohortVenueStopRaise {
                    entry_oid: 1,
                    ..raise(99.297625, false)
                },
            ),
        ];
        for (label, venue, evidence) in cases {
            let trade = rebound(&cohort(venue, vec![evidence]));

            assert_eq!(trade, open_trade(), "{label}");
        }
        let mut foreign = [CohortOpenTradeReflection {
            lifecycle_id: format!("BTC:{ENTRY_OID}"),
            ..open_trade()
        }];
        apply_venue_stop_raises(
            &cohort(asset(json!({})), vec![raise(99.297625, false)]),
            &mut foreign,
        );
        assert_eq!(foreign[0].protective_stop_oid, Some(INITIAL_STOP_OID));
        assert_eq!(rebound(&cohort(asset(json!({})), Vec::new())), open_trade());
        for lifecycle_id in [
            format!("{SYMBOL}:0{ENTRY_OID}"),
            format!("{SYMBOL}:+{ENTRY_OID}"),
            format!("{SYMBOL}:"),
            format!("{SYMBOL}{ENTRY_OID}"),
        ] {
            let noncanonical = CohortOpenTradeReflection {
                lifecycle_id,
                ..open_trade()
            };
            let mut trades = [noncanonical.clone()];
            apply_venue_stop_raises(
                &cohort(asset(json!({})), vec![raise(99.297625, false)]),
                &mut trades,
            );
            assert_eq!(trades[0], noncanonical, "{}", noncanonical.lifecycle_id);
        }
    }
}
