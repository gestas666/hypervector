# V89 seven-asset shared accounting and cost sensitivity

The frozen seven-asset portfolio now has a complete shared cash, funding,
marking, exposure and margin path for all six declared scenarios. Under the
adverse cost model, 176 completed trades produced **+$119.85** over 48 explored
days, with **3.32% close-mark drawdown**. Applying the full HIP-3 fee scenario
changes the result to **−$9.46**. Removing the three largest winners changes
the adverse result to **−$108.38**.

Research implementation: `4cc8564` in the isolated portfolio worktree. The
installed trading checkout remains `a42afa8`.

Confidence is high in the conditional accounting: independent calculations
reconcile all 49 daily boundaries per scenario within $0.000000000002. This
does not establish future profitability or exact native execution. Source
prices, actual fill times, venue funding marks and realized fees remain
separate qualifications. No live sizing or strategy change follows from these
results alone.

## Scope and evidence

- Exact profile fingerprint:
  `39e334fc97f3cbe21bac30e53e91524d6a4cf9727370a0f69bc2d51039667f7a`.
- Window: July 21, 2026 00:00 UTC through September 7 00:00 exclusive.
  These 48 days have already been explored; they are not a sealed holdout.
- Initial reference equity: $4,857.58724349. Four existing crypto routes and
  the current SPCX, SNDK and Brent routes retain their configured sides,
  leverage, margin fractions and notional caps.
- Core extraction and source qualification are recorded in
  [the prior review](2026-09-07-v89-core-replay-source-fidelity.md).
  The isolated SPCX rolling-band fix is not included in this baseline.
- The previous operator-status turn did not advance research. This turn
  completes shared attribution, validation, visualization and durable records.

All result paths below are relative to the original checkout's
`data/logs/research/bidirectional_cohort/`:

- `v89_shared_marked_portfolio_20260907_v2/report.json` and six full paths.
- `v89_shared_portfolio_attribution_20260907_v3/report.json` and six daily paths.
- `v89_shared_portfolio_figures_20260907_v3/shared_portfolio.png` and manifest.
- `v89_shared_joint_commit_tests_20260907_v2.log`.
- `v89_shared_marking_publish_validation_20260907_v1.json`.

The hypothesis record fingerprints the final code, plans, source grids,
funding files, lifecycle inputs, reports and validation. Version 1 results are
preserved. A pure function extraction changed the marking script's source
hash; all six version 2 marked paths and all six daily paths were compared
exactly with version 1 and are unchanged. The original version 1 script bytes
remain in `v89_shared_first_pass_source_20260907_v1/`. Final attribution version 3
also retains all earlier numeric results and adds the UTC dates omitted from
the version 1/2 daily exports.

## Accounting correction and timing assumptions

The existing marking engine interpolated total funding between entry and exit
and required a positive lifecycle duration. That could not represent the
declared hourly funding clock or the three recorded same-bar SNDK lifecycles.
Research callers can now supply exact timestamped funding and reserved margin.
Legacy callers retain their explicitly labeled linear-funding default.

The new path charges entry fees at entry, applies funding at its actual hourly
timestamp, and reconciles final net cash at exit without double counting.
Unknown margin remains unavailable. Explicit funding must name every trade,
have ordered unique aware millisecond timestamps inside `(entry, exit]`, and
reconcile to that trade's total within $0.00000001.

Completed candle marks become available after one minute for core assets and
after fifteen minutes for additions. A new position initially uses its known
entry price. Later marks carry forward until the next completed observation;
future candle closes do not appear at their opening timestamps.

Both declared execution clocks retain every trade and its recorded prices,
quantity, fees and funding. The first uses recorded bar timestamps. The second
moves intrabar stop/target/liquidation exits to the last millisecond of their
source bar. Both produce the same aggregate results and daily totals in this
sample; their event paths and diagnostics are not identical.

Three SNDK trades have no interior completed mark in either interpretation.
They are classified as instant exits on the recorded clock and as missing-mark
lifecycles on the late-exit clock. The report preserves this limitation rather
than inventing an intrabar path. Same-symbol overlaps are technical failures.

## Joint results

Fees and slippage below are per side. Core fees are 4.5 bps throughout. Nominal
uses 0.9 bps HIP-3 fees and 2.5 bps slippage; adverse uses 0.9 and 5.5;
full-fee uses 9.0 and 5.5. Funding rates are native hourly records, with the
inherited source-bar opening price as the funding-mark proxy.

| Cost scenario | Net USD | Close-mark max drawdown | Wins / trades | Net excluding three largest trades |
| --- | ---: | ---: | ---: | ---: |
| Nominal | +172.61 | 2.95% | 73 / 176 | −56.55 |
| Adverse | +119.85 | 3.32% | 72 / 176 | −108.38 |
| Full HIP-3 fees | −9.46 | 4.21% | 66 / 176 | −235.22 |

The adverse win rate is **40.9%**. Sparse entries do not imply that most trades
will win. Removing winners is a concentration sensitivity, not an alternative
forecast or justification for removing those trades from the strategy.

| Asset | Trades | Wins | Adverse net USD |
| --- | ---: | ---: | ---: |
| BTC | 3 | 2 | +4.10 |
| ETH | 3 | 0 | −8.99 |
| SOL | 5 | 2 | +2.76 |
| HYPE | 5 | 1 | −75.53 |
| SPCX | 52 | 32 | +43.79 |
| SNDK | 47 | 15 | +120.85 |
| Brent | 61 | 20 | +32.86 |

SNDK contributes slightly more than the combined adverse net result. Its short
side has only +$1.99 aggregate net despite a $91.35 largest winner. HYPE's five
trades and ETH's three trades are insufficient to distinguish persistent
failure from variance by themselves. Route-side details remain in the report.

## Capacity, overlapping losses and correlation

All six scenarios reach at most four simultaneous positions and $400 reserved
entry margin. No frozen notional differs from the configured cap at its entry
check. The highest equity floor required for all caps to bind is $3,125; even
the lowest full-fee adverse price proxy remains $4,784.78. Thus the frozen
quantities are conditionally compatible with this shared account path.

Minimum modeled cash after reserved entry margin is $4,506.20 in the adverse
case and $4,468.89 in the full-fee case. Adverse maximum gross marked notional
is $4,072.12 and maximum absolute net marked notional is $3,508.89. These cash
and margin fields are research measures, not reconstructed venue withdrawable
balance, maintenance margin or liquidation guarantees.

The adverse path has 26 positive days out of 48. At least two assets have
negative daily contributions on 23 days, reaching four simultaneous losing
assets on one day. The worst day is August 7 UTC, ending August 8 00:00,
at −$65.62. July, August and September partial-window contributions are
+$52.00, +$12.14 and +$55.71 respectively.

The strongest absolute daily strategy-PnL correlations are BTC/HYPE 0.361,
BTC/Brent 0.314 and SNDK/SPCX 0.235. These are 48 descriptive daily observations,
including inactivity; they are not underlying-market return correlations or
proof of persistent diversification.

## Validation and failure modes

The final focused suite passes **35 tests**, with **94% combined statement
coverage** of the three accounting modules. Funding validation and independent
daily attribution each have 100% statement coverage. Tests cover real event
timing, entry/exit funding boundaries, no future marks, both directions,
same-bar exits, malformed schedules, mixed source cadence and cash/margin
disagreements. An additional regression reproduced dropped daily timestamps:
the immutable Parquet writer excludes DataFrame indices, so publication now
materializes `period_end_utc` as a column. This test failed before the correction
and passes with exact dates and PnL on reload. All six full daily exports retain
their 48 UTC boundaries and unchanged numeric values. Ruff and whitespace
checks pass; all changed Python files and
functions meet the 500/50-line limits.

Independent daily attribution computes cash and known-price contribution
directly from each lifecycle and its funding events, without using the marking
engine's mutable state. All six cases reconcile 49 boundaries; maximum error
is approximately $1.06e-12. This validates arithmetic and daily event ordering,
not shared source truth. The exported chart was visually inspected; its
currency annotations render literally and its negative asset results remain visible.

Remaining limitations include archive/native price disagreements, carried
gap prices, coarse addition marks, unknown intrabar ordering, funding-mark
proxies, venue rounding, liquidity and realized latency/slippage. A difference
in source hashes, future-price use, missing funding, irreconcilable cash or
capacity mismatch would invalidate the corresponding accounting acceptance.
Live economics require observed fills and contemporaneous fee evidence.

## Recommendation and next investigation

Accept the research accounting correction and retain all six outcomes. Its
upside is an auditable shared result; it does not establish a growth forecast.
It applies across the sampled regimes, but regime-specific generalization
still needs qualified source history and independent evaluation.

| Alternative | Benefit | Limitation / decision |
| --- | --- | --- |
| Keep the prior research engine | No code change | Cannot represent this investigation's funding clock or same-bar trades |
| Use independent asset PnL sums | Simple terminal check | Omits concurrent marks, cash, exposure and capacity |
| Use the corrected shared replay | Measures the declared account paths | Retain with explicit source and execution limitations |
| Increase size from spare margin | More exposure | Expected benefit unproven; fees and winner concentration dominate this sample |

The **single highest-value next investigation is execution-cost and native
source fidelity**, starting with the current HIP-3 fee assumption: its tested
alternative changes the portfolio result's sign. Capture contemporaneous fee
metadata and account fee evidence through read-only interfaces, then reconcile
actual natural fills when available. Separately quantify entry, exit and
prior-indicator-history differences using the retained matched native/archive
data; do not choose a feed because it has the better PnL.

This has high information value, medium implementation effort, and no required
trading mutation. Subsequent priority is chronological/regime and winner
concentration sensitivity on qualified inputs. Automatic risk scaling or
removing a route after three to five trades has low evidential support here.

Success criteria are exact source and route identity, reconciled observed
costs, and explicitly measured decision/lifecycle differences. Preserve this
revision and publish a superseding result if those assumptions fail; research
rollback must not erase prior evidence. No deployment or live configuration
change is proposed by this report, and no approval is requested for its
report-only correction.

The overall goal remains active. Native execution qualification, prospective
fills, independent strategy validation, the isolated SPCX fix disposition and
the old launcher's retired-reporter shutdown message remain unresolved.
