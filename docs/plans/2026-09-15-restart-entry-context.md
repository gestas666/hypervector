# Restore recorded entry context across checkpoint restarts

The same SNDK lifecycle `xyz:SNDK:545845583477` has full recorded entry indicators and 1m/5m/15m context in the prior-run checkpoint, but unavailable context after the user restart. `recover_cohort_execution_identities` currently restores only old configuration identities; `build_open_trade_reflections` therefore cannot find the exact source-run/provider/symbol/decision evaluation. Execution size, stop and costs remain intact.

1. Preserve the before/after checkpoint evidence and write a real-publisher failing regression using the existing restart fixture with prior provider and canonical rows.
2. Restore only recorded prior execution context using authenticated prior-run boundaries and exact lifecycle decision identities. Preserve current-run routing/readiness/health counts and causal cutoffs. Keep missing legacy context explicitly unavailable; reject conflicting evidence. Avoid a full historical JSON materialization or repeated unbounded scans.
3. Test restart context recovery, missing evidence, wrong run/provider/symbol/time, duplicate conflicts, cutoff behavior, source mutation and unchanged execution totals. Validate the real SNDK entry context byte-for-byte against its prior recorded evidence.
4. Measure actual-ledger cold and repeated publication cost and memory. Inspect all changed report sections, especially interpretation of sparse historical context in regime/opposition evidence. Do not represent selected entry annotations as a complete historical timeline.
5. Back up and install only the qualified reporting delta. Verify through an independently owned reporter/TUI; preserve user backend/supervisor/reporter/TUI processes. No financial process control or strategy changes.
6. Publish exact evidence, hypothesis decision, rollback and current handoff. No repeat approval is required for this authorized reporting repair. Broader continuous research remains active.
