# SPCX hourly exit: independent candle reconstruction

## Finding and scope

High confidence for this recorded lifecycle: SPCX's 2026-09-16 09:00 UTC exit
matches the configured hourly mean-exit rule. Its completed hourly close was
**144.23**, above the independently reconstructed 20-hour mean of **143.8525**.
The preceding 13 hourly checks did not qualify for a long exit. All 42
intervening quarter-hour evaluations correctly carried no hourly exit flag.
The earlier `EXIT SHORT` indications applied to shorts, while this lifecycle
was long.

This closes the raw-band reconstruction limitation in the earlier
[cash and execution reconciliation](2026-09-16-v89-spcx-hourly-exit-reconciliation.md).
That earlier report and its evidence remain unchanged. Its verified net result
was **+$0.567607**, after fees and funding. One profitable lifecycle does not
establish positive expectancy or justify an exit-policy change.

The audited identity is run `bidirectional-live-1789497016143`, lifecycle
`xyz:SPCX:546010609566`, strategy
`hourly_band20_reentry_atr20_bidirectional_v1`. Entry decision: September 15
19:00 UTC. Exit decision: September 16 09:00 UTC.

## Source and arithmetic validation

The frozen native prefix contains 15,452 contiguous ledger records, sequences
605439–620890, occupying 150,894,794 original bytes. Each of the 4,301 selected
records was matched to its original byte offset, length, SHA256 and decoded
JSON inside the retained compressed prefix. The prefix hash is
`6fc3be5666d08f399f9d243dbe7c2fc41bb4895590f85f9ec8ac57ba21930058`.

The audit retained 1,219 completed native minute candles. The final exit's full
20-hour window, September 15 13:00 through September 16 09:00 UTC, contains
1,200 native minutes and needs no public warmup substitution.

Earlier holding decisions use the already saved public response only for
minutes preceding the first native candle at September 15 12:41 UTC. That
response was received at September 15 19:29:18.710561 UTC, before the first
tested hourly holding decision at 20:00 UTC. All 379 overlapping native/public
minutes agree across OHLCV within the fixed 1e-9 overlap tolerance. Missing
interior native minutes are rejected rather than filled from the public copy.

Each decision requires a complete 1,200-minute grid. The audit selects its 20
completed hourly closes, uses the previously pinned independent Decimal
population-variance reference for the mean and two-standard-deviation bands,
and separately evaluates `long exit = close >= mean`. The result retains each
20-close input list for inspection. Maximum absolute disagreement with the
recorded three band values over all 14 decisions was **2.2737367544323206e-12**,
below the predeclared 1e-10 tolerance.

| Hourly decision, UTC | Close | Reconstructed mean | Long exit |
| --- | ---: | ---: | --- |
| Sep 15 20:00 | 143.51 | 147.1095 | No |
| Sep 15 21:00 | 143.31 | 146.8375 | No |
| Sep 15 22:00 | 142.66 | 146.5270 | No |
| Sep 15 23:00 | 143.06 | 146.2355 | No |
| Sep 16 00:00 | 142.78 | 145.9380 | No |
| Sep 16 01:00 | 143.35 | 145.6850 | No |
| Sep 16 02:00 | 143.14 | 145.4330 | No |
| Sep 16 03:00 | 143.55 | 145.1905 | No |
| Sep 16 04:00 | 143.86 | 144.9730 | No |
| Sep 16 05:00 | 143.89 | 144.7595 | No |
| Sep 16 06:00 | 144.28 | 144.5585 | No |
| Sep 16 07:00 | 144.22 | 144.3310 | No |
| Sep 16 08:00 | 143.88 | 144.0800 | No |
| Sep 16 09:00 | 144.23 | 143.8525 | Yes |

For the final exit, input availability is checked against the actual
`provider_exit_decision` observation at **09:00:14.143730 UTC**, not the later
evaluation publication at 09:00:17.428879. The final minute candle was retained
at 09:00:14.142491. Earlier hourly inputs must precede their evaluation's
observation time and ledger sequence. This supports the recorded sequence;
it does not measure the exact CPU evaluation time.

## Qualification and reproducibility

The initial 17 arithmetic, cadence and corruption controls passed. Additional
controls exposed four omissions in the new offline audit validator: it ignored
the declared first sequence, selected-record count and byte-range length, and
accepted an exit observation later than its reporting event. These were
reproduced with failing tests and corrected within the audit code.

The final suite passed **29 tests**, including altered prices/bands, missing or
duplicated candles and evaluations, wrong sides and lifecycle, late inputs,
changed source bytes and inconsistent source metadata. Coverage measured
178/185 statements and 25/26 branches; the uncovered code is the command-line
writer/entry point, which was exercised separately by both actual audit runs.
Ruff and the 500-line/file, 50-line/function and function-annotation checks
passed.

Two separate audit processes ran with network access denied, a clean
environment, `.env` reads denied and file writes restricted to their named new
result files. They produced byte-identical 16,091-byte reports, SHA256
`65cd4d50e7ef87edb9f5ed379c4b64f455e426b9501d127f8709bfd9fa7eb498`.
All artifacts are in
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/spcx_exit_signal_v1/`.
The journal revision pins the inputs, validator, tests, results and policy.

## Decision, alternatives and remaining limits

**Recommendation:** accept this lifecycle's reconstructed exit predicate and
prior holding decisions as reconciled; retain the current rule while gathering
the separately declared complete-account evidence.

**Why now / observed problem:** the earlier execution audit left the raw
20-hour band calculation unverified. Rebuilding it distinguishes a late or
missed qualifying exit from a small outcome produced by the intended rule.

**Evidence reviewed:** native candle/evaluation/exit records, the existing
public warmup response, pinned independent Decimal arithmetic, production
rule semantics, and the already reconciled fill/funding records.

**Applicable market regime:** this tests the price-based exit across the
observed holding window. It adds no regime filter and makes no claim that the
strategy is suitable for every regime.

| Alternative | Benefit | Limitation / decision |
| --- | --- | --- |
| Keep the earlier audit alone | No additional work | Leaves the mean-exit predicate unverified; superseded by this evidence. |
| Reconstruct the fixed recorded decisions | Tests the actual rule and retained chronology | Selected; limited to one lifecycle and available native/public sources. |
| Optimize an earlier exit from this trade | Could fit a larger retrospective gain | Reject as a live recommendation: one selected path and candle extrema do not establish executable improvement. |

**Proposed live change / approval requested:** none. This is authorized
offline analysis and journal work. Financial processes, parameters, leverage,
sizing, execution and deployment settings were not changed.

**Expected upside:** more reliable diagnosis of exit logic and fewer
unsupported strategy changes. No numerical profit improvement is forecast.

**Main risks and failure modes:** native chart telemetry retains published
candles rather than every possible later revision. The public response is
earlier than the tested holding decisions but is not the original startup
input. Original ATR initialization remains unqualified. A matching signal does
not prove the strategy's economic merit. Earlier favorable candle extrema are
not executable fills.

**Validation completed:** 56 decision checks, 1,219 retained native candles,
379 overlap checks, 29 tests and byte-identical offline reproduction.
**Validation still required:** the full native account qualification remains
running; real prospective comparisons retain their original study seals.

**Success metrics:** complete causal input windows, exact decision cadence,
band errors within the fixed tolerance, matching exit sides and exactly one
qualifying long exit at the recorded exit decision.

**Failure / rollback triggers:** changed evidence hashes, missing or
late-arriving inputs, a contradictory hourly close/mean, an earlier qualifying
long exit, or inconsistent execution receipts reopen the diagnosis. Retain
both journal revisions; correcting this report requires no financial restart.

**Confidence:** high for the bounded signal reconstruction; unestablished for
future expectancy or a strategy change. **Next highest-value investigation:**
finish the original full native account job and its authenticated repeated
account comparisons, while the passive observers retain new native events.
