# Historical report V3 and strict numerical validator installed

High confidence: the user-requested corrections are installed in the shared Hypervector root. The corrected [V3 report](../reports/2026-09-12-historic-trade-analysis-131-trades.md) replaces the prior V2 document after preserving its exact bytes. The [requested validation review](/Users/gestas/Prototypes/hypervector-v89-report-audit-20260912/docs/reviews/2026-09-12-v89-historic-report-validation.md) remains unchanged.

The current V2 was not the original V1 assessed by that review. V1 hash is `c5e2de7d8c7efadcb34c118fce3015c15edb5e9c548db0e644bbc83b3c7f964c`; V2 hash is `754a3361c6359977750f15770b81facac21f9cff9db48f3855c5c2f6b9d212f4`. V2 had corrected several earlier counts but retained unsupported causal and operational claims. The report now identifies these revisions correctly and attributes the review hash separately through its evidence manifest.

| Item | Applied correction |
| --- | --- |
| Directional attribution | Long gross/fees/funding are -$185.53 / $41.35 / -$1.54; short values are -$113.06 / $42.39 / +$4.78. Fees are consistently positive costs. |
| Numerical validation scope | The original 1,311 scalar checks cover total, strategy and strategy/asset projections. Direction rows now receive 24 separate printed-cell checks. |
| Validator command status | A mismatched strategy or direction cell now produces a nonzero command exit after retaining diagnostic files. Previously a wrong strategy-table cell was reported with exit zero and direction tables were unchecked. |
| Return and population interpretation | Net/summed entry margin is explicitly distinguished from account return; 131 trades across 20 fingerprints are separated from seven exact current-profile trades totaling -$49.11. |
| Causal and strategy claims | Negative observed gross PnL and positive selected subgroup totals are observations, not demonstrated expectancy. Unverified regime, early-reversal and exclusive hold-limit explanations are removed. |
| Slippage and latency | Three SNDK entry fills/two orders and zero SPCX entries remain explicit. The 1209.17 ms mean is over six fill-associated observations representing five orders. Separate latency causes are unidentified. |
| Other numerical wording | Hulk's losing-trade denominator is $0.184067; the 32-minute alternative-run attribution is removed as unsupported; annual simulations and 177 trades in one case retain their separate scopes. |
| Configuration instructions | The zero-shorts statement, blanket 15 bps recalibration, implicit regime qualification and unapproved PF/drawdown acceptance criteria are not selected actions. Exact already-absent legacy routes are distinguished from configured current routes. |
| Work status | Completed entry-context, gap, trade-source, TUI/recovery/session-reuse and importer work is linked. The next research question is fixed source-decision sensitivity, not a repeat of completed searches. |

The validator reuses the audited SQL, sign/precision handling and immutable writer. The new directional comparator accepts the older layout without funding and the corrected layout with funding, requiring every observed direction and total exactly once. It shares the numerical cell checker with strategy rows. Missing, duplicated or malformed rows fail explicitly; numerical mismatches retain both table-check artifacts before raising an actionable error. Shell callers no longer have to infer failure from a count inside otherwise successful output.

The source-bound evidence is at `/Users/gestas/Prototypes/hypervector/data/logs/research/bidirectional_cohort/v89_report_corrections_20260912_v1`. Fourteen original frozen source references authenticate. Additional archived analysis references, including all 131 lifecycle rows, were checked against the prior research journal. The exact current profile fingerprint and seven-row population were independently recomputed using the current configuration in observe mode; no account client was constructed.

Validation completed:

- Seven new tests first failed, including real subprocess demonstrations of exit zero on incorrect printed numbers. The completed suite has **23 passing offline tests** in the candidate, archived source and installed root.
- Combined measured statement/branch coverage of the metric operator and writer is **97%**. The mismatch failure branch is exercised in-process and by subprocess. Three uncovered lines include the script-entry branch, a nested-checkpoint skip and an unsupported direction population; no complete-package coverage claim is made.
- Actual V2 fails with **five** direction-cell mismatches. Its 238 strategy-table cells remain valid. V3 passes all **262** printed cells: 238 strategy/asset and 24 direction/total.
- All **1,311** checkpoint scalar comparisons and independent Decimal cash sums reconcile; maximum floating residual is **5.4569682106375694e-12**.
- An archive of six source/report/plan files reproduces all eight numerical artifacts byte for byte with socket networking disabled. The installed command produces the same eight artifacts.
- Ruff checks/formatting and the 500-line file, 50-line function and explicit-return checks pass for the four installed Python/test files.

The installed audit command remains deliberately scoped to a prepared frozen report bundle:

```bash
.venv/bin/python scripts/historic_report_metrics.py --out /absolute/path/to/new-audit-bundle
```

That bundle must contain `lifecycle_rows.json` plus `inputs/checkpoint.json`, `inputs/2026-09-12-historic-trade-analysis-131-trades.md`, and `inputs/multi_asset_growth_first_5000_noncrypto_live_v89.toml`. Use a fresh bundle: diagnostic files are immutable. `validate_reports.py` in the evidence directory documents the exact preparation used for V2/V3 checks. This command validates numbers and populations; human review of causal language remains necessary.

Installation copied only the report, two audit scripts, two test files and implementation plan, followed by this change review and its journal record. The tested source candidate is `7f21ef8`; six installed file hashes agree with its reproduction manifest. Eighty-nine other previously protected files retain their hashes. Existing handoff/index and source-propagation edits are preserved. No TUI rebuild is needed for this report/validator change.

The V2 backup is `backup/report-v2.md`; `before_source.tar.gz`, `installation_prepared.json` and `installed_source.patch` preserve restoration evidence. The reverse patch passes `git apply --reverse --check` at the installation boundary. Restoring V2 would recover a document containing known errors, not restore a validated analytical conclusion. Later modifications should be checked against the recorded hashes before using that recovery path.

Confidence is high in the bounded report and failure-status corrections. A changed source population, wrong current fingerprint, failed independent replay, altered installed hash or wrong-cell command returning success would falsify completion. The historical samples do not establish future profitability, justify speculative strategy changes or prove broad live readiness. Live configuration, strategy, sizing, risk, execution behavior and the prior runtime files are unchanged; no trading process is started by these tools. Prospective outcome seals remain unopened. No additional approval was needed because the user's latest instruction explicitly requested implementation of applicable corrections.
