# SNDK hourly strategy exit, September 16

The SNDK short opened September 15 at 16:00:07.238 UTC and closed September 16 at
07:00:13.382 UTC through its configured hourly recipe exit. Independent Decimal
arithmetic reconciles a **$4.445448 net loss**. High confidence applies to the
17 authenticated native funding/fill records and the retained closing sequence;
it does not establish strategy expectancy or complete market-source correctness.

| Component | Native evidence |
| --- | --- |
| Entry | OID 545845583477; short 0.326 at 1531.7 |
| Exit | OID 546496662445; buy 0.326 at 1545.3 |
| Gross PnL | −$4.433600, matching venue closed PnL |
| Entry / exit fees | $0.043142 / $0.043525 |
| Funding | +$0.074819 across 15 distinct hourly receipts |
| Net PnL | −$4.445448 |
| Holding duration | 54,006,144 ms, approximately 15 hours |
| Recorded leverage | 10x |
| Exit reference / fill | 1544.8 / 1545.3; 3.236665 bps adverse reference slippage |

The recorded completed-hour close, 1544.8, exceeds the recorded prior ten-hour
exit-channel high, 1544.6. That satisfies the implemented strict short-exit
predicate. The strategy is `hourly_donchian_20_10_atr20_bidirectional_v1` and its
persisted policy honors provider recipe exits. This was not a stop-trigger or
maximum-hold exit. The actual preceding ten source candles have not been
independently recomputed in this review; confidence in the channel calculation
remains limited to the retained provider evidence and existing source logic.

Native SNDK sequences 350320–350330 record one close intent, one reduce-only
submission, an accepted filled acknowledgement, a verified-flat receipt, no
remaining venue open orders, zero position size, the fill and fee, then FLAT
state. A subsequent reconciliation also records no orders. There is no duplicate
close or transport recovery in that retained sequence. These observations are
not a universal execution guarantee.

The accounting capture selected the exact entry, exit and funding rows from a
read-only DuckDB snapshot and matched each to its original ledger byte offset
and SHA256 within a bounded 32 MiB tail. Funding ownership retains signed size
−0.326; all fifteen intervening hourly settlement identities are present.
It did not reconstruct native receipt amounts from rounded rates or infer UTC
by casting a timezone-free string. The frozen checkpoint net differs from the
Decimal value only by floating-point representation below 1e−9 dollars.

The recorded completed-hold analysis contains 899 completed minute candles,
129.921 bps favorable excursion and 218.711 bps peak giveback. This is descriptive
evidence of a favorable marked path ending in a loss. It is **not executable
profit**: the report explicitly marks the maximum net excursion non-executable.
Regime opposition has 691 unavailable observations among 741 decisions, so this
sample cannot support a reliable regime-performance attribution. Previously
rejected exit variants are not reopened solely because this trade lost money.

Recommendation: retain this completed lifecycle in the existing chronological
exit-quality and account-allocation study. Why now: the first newly completed
lifecycle since the preceding checkpoint adds actual cost and holding evidence.
Applicable regime: this observed SNDK short; generalization is unproven.

| Alternative | Evidence / trade-off |
| --- | --- |
| Preserve current settings while validating the declared comparison | Keeps a traceable baseline; additional losses remain possible. |
| Retune stops or add profit-taking from this one path | Fits a visible loss but has no demonstrated out-of-sample advantage; not recommended from this evidence. |
| Reopen a prior rejected challenger | Requires a separately documented changed assumption and new controlled evidence. |

Proposed live change: none. Expected upside of the current research work:
trustworthy attribution of realized losses, financing and marked carry before
comparing strategies. Main risks: single-trade selection, hindsight exit prices,
missing regime context and treating synthetic reporting controls as strategy
validation. Validation completed: exact native accounting reconciliation and
the retained dispatch/fill/flat chain. Validation remaining: full captured daily
and seven/seven attribution, complete declared case comparisons with realistic
costs, and independent source-channel reconstruction if a signal discrepancy
appears. The highest-value next investigation remains the complete captured
account attribution, including positions carried across period boundaries.

Success criteria: every receipt has its original identity; fees/funding/net
reconcile; carried equity and cash belong to their actual periods. Failure
triggers: missing/repeated funding, altered native bytes, wrong source clocks,
unexplained net differences or a channel-source disagreement. Such evidence
reopens the corresponding finding. No runtime change needs rollback; all source
captures and scripts are retained. Explicit live approval requested: none,
because this review proposes no live change.

Both passive observers ended on this event. Their actual `native_transition`
receipts were reviewed, retained and used to resume from the saved final offsets;
they were not relabeled as observation deadlines. Successor scripts authenticate
the reviewed accounting evidence, previous receipts and cursor snapshots, and
verify the unchanged backend identity before observing further appended rows.
No financial process was started, stopped, restarted or signalled.

Evidence: `data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/sndk_exit_20260916_v1/`
contains `capture.json`, bounded native tails, the frozen checkpoint/reflection,
`reconcile.py`, `accounting_source_records.json` and
`accounting_reconciliation.json`. The sibling lifecycle/diagnostic followup
directories retain their exact predecessor references and first scans.
