# Artifact-dependent test disposition — 2026-10-17

The default unit suite excludes `evidence`, `integration`, `network` and
`performance`. These are explicit selections, not xfails or substituted
successes. Selecting a group without its prerequisites still fails. Core
approval validation, corrupt-ledger refusal, paper zero-submit and live
authority checks remain ordinary offline tests with temporary fixtures.

The table counts decorated functions rather than parameterized test cases.
Historical source hashes were already inconsistent in the audited baseline;
the cleanup does not re-sign them. No production evidence was copied into
version control or fabricated to turn those checks green.

| File | Selection | Functions | Prerequisite |
| --- | --- | ---: | --- |
| `tests/test_btc_specialist_successor_risk.py` | `evidence` | 3 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_btc_specialist_successor_risk_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_cohort_family_concentration_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_cohort_improvement_monitor_hype_native.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_cohort_improvement_monitor_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_complete_portfolio_cockpit_v25_config.py` | `integration` | 2 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_complete_portfolio_v26_transition_runbook.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_complete_portfolio_v27_transition_runbook.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_complete_portfolio_v28_transition_runbook.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_eth_pullback_forward_observer_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_eth_pullback_forward_resolution.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_eth_pullback_routed_v17_candidate_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_eth_sol_canary_v23_transition_runbook.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_evidence_routed_candidate_v18_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_evidence_routed_eth25_canary_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_evidence_routed_eth_sol_candidate_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_evidence_routed_hype75_all_asset_observe_candidate_config.py` | `integration` | 2 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_evidence_routed_retest_observer_v21_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_evidence_selected_portfolio_v29_transition_runbook.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_fetchers.py` | `network` | 4 | Explicit venue/public API network access; never part of default units. |
| `tests/test_four_core_successor_candidate.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_growth_first_5000_eight_asset_incremental_v58_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_growth_first_5000_evidence_bound_successor_v52_config.py` | `integration` | 2 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_growth_first_5000_repaired_candidate_v47_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_growth_first_5000_repaired_candidate_v48_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_hype_relaxed_candidate_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_hype_retest_v13_config.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_hype_target20_candidate_config.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_hyperliquid_btc_factory.py` | `integration` | 2 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_hypervelocity_event_runtime.py` | `integration` | 2 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_hypervelocity_profile.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_install.py` | `integration` | 7 | Install integrations extra; Ray test also needs local service startup. |
| `tests/test_lean_successor_portfolio_v30_transition_runbook.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_multi_asset_evidence_candidate_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_multi_asset_intent_poller.py` | `integration` | 1 | Exact external provider/model or historical input named in this test; inspect its fixture paths before running. |
| `tests/test_multi_asset_live_runner_stop_latency.py` | `integration` | 2 | Local loopback HTTP fixture only; run separately with integration selection. |
| `tests/test_provider_stop_bps_overrides.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_retired_strategy_reexamination.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_source_follow_event_forward_script.py` | `integration` | 1 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_live_config.py` | `integration` | 5 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_live_engine.py` | `integration` | 20 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_live_shape_script.py` | `evidence` | 1 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_paper_session.py` | `evidence` | 1 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_paper_session.py` | `integration` | 6 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_profile.py` | `evidence` | 1 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_profile.py` | `integration` | 11 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_research_config.py` | `evidence` | 1 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_source_follow_runtime.py` | `integration` | 2 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_swing_pruned_candidate_v31_transition_runbook.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v33_acceptance_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v41_successor_readiness.py` | `evidence` | 4 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v41_successor_readiness_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v42_successor_design.py` | `evidence` | 3 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v42_successor_design_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v43_portfolio_friction_stress.py` | `evidence` | 6 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v45_growth_sizing_stress_script.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v47_strategy_regression_report.py` | `evidence` | 3 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v48_portfolio_readiness_report.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_cross_restart_filter_disposition.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_forward_opportunity_exit_review.py` | `evidence` | 3 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_growth_operating_delta.py` | `evidence` | 5 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_risk_balanced_sizing.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_sol_exit_snapshot_disposition.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v49_strategy_repair_disposition.py` | `evidence` | 14 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v51_index_lifecycle_contract.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v51_index_shadow_lifecycle.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v51_index_shadow_lifecycle_script.py` | `evidence` | 3 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v52_common_window_portfolio_script.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v52_continuous_improvement_profile.py` | `evidence` | 4 | Exact pinned Hypertrader vendor tree and associated profile artifacts. |
| `tests/test_v53_continuous_improvement_profile.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v55_btc_hype_sparsity_journal.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v55_continuous_improvement_profile.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v56_continuous_improvement_profile.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v57_continuous_improvement_profile.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v57_sp500_external_candidate_integration.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v58_btc_trend_pullback_failure_attribution_script.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v58_continuous_risk_context.py` | `evidence` | 6 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v58_current_funding_context.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v58_eight_asset_growth_stress_script.py` | `evidence` | 2 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v58_poststart_acceptance.py` | `evidence` | 5 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v59_poststart_acceptance.py` | `evidence` | 6 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v62_hype_alignment_profit_lock_candidate_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v63_bankroll_builder_candidate_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v64_gold_asset_removal_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v65_bleeding_asset_retirement_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v66_brentoil_retirement_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v67_continuous_improvement_monitoring.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v67_evidence_scope_repair_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v68_btc_ioc_hardening_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v76_continuous_improvement_monitoring.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v76_seven_asset_roster_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v77_btc_component_exit_repair_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v78_sndk_canary_sizing_repair_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v79_closed_lifecycle_acceptance.py` | `evidence` | 8 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v79_execution_quality_acceptance.py` | `evidence` | 6 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v79_open_lifecycle_acceptance.py` | `evidence` | 10 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v79_poststart_acceptance.py` | `evidence` | 14 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v79_restart_acceptance.py` | `evidence` | 4 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v80_entry_ioc_hardening_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v85_btc_tuned_retirement_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v86_failed_route_retirement_config.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v90_option_b_package.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |
| `tests/test_v90_transition_package.py` | `evidence` | 1 | Frozen profile exports, source hashes, model/baseline files or operator approval/accounting backup bundles referenced by this test. |

Reproduce units with `.venv/bin/python -m pytest tests/ -q -n 4 --dist loadfile`.
Use `-m evidence` for local immutable evidence and `-m integration` for
external dependencies. Do not run the whole integration selection against
an armed checkout. The bounded loopback check is
`tests/test_multi_asset_live_runner_stop_latency.py -m integration`.

VectorBT, Rust and TA-Lib execution checks in `tests/test_install.py` run by
default; only its broad adapters and Ray service checks are opt-in.
Network tests remain opt-in even when connectivity is available.
