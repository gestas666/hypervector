use super::profit_lock_contract_valid;

#[test]
fn btc_hulk_component_floor_is_route_scoped_and_has_no_fixed_bps() {
    assert_specialized_policy("btc_hulk_delayed_component_floor_v1");
}

#[test]
fn btc_hulk_component_exit_v2_is_route_scoped_and_has_no_fixed_bps() {
    assert_specialized_policy("btc_hulk_delayed_component_exit_v2");
}

fn assert_specialized_policy(policy: &str) {
    assert!(profit_lock_contract_valid(
        Some("hulk_expansion_short_robust_v3"),
        policy,
        None,
        None,
        None,
    ));
    assert!(!profit_lock_contract_valid(
        Some("hulk_expansion_short_tuned_v2"),
        policy,
        None,
        None,
        None,
    ));
    assert!(!profit_lock_contract_valid(
        Some("hulk_expansion_short_robust_v3"),
        policy,
        Some(75.0),
        None,
        None,
    ));
}
