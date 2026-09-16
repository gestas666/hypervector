# Isolated native ETH/SOL decision reuse

The research candidate removes an exactly repeated ETH/SOL calculation within
one provider/canonical publication. All **252 sampled native outputs** match
the previously frozen baseline, including every serialized field. Median paired
time reductions are **43.62% for ETH** and **42.03% for SOL**. Confidence is high
for these fabricated inputs and declared implementations; full-period sequential
equivalence remains unqualified. No profitability improvement is established.

Candidate commit: `3d4de3cab712129353d2e4710846d7da475fbfde`, isolated at
`/Users/gestas/Prototypes/hypervector-v89-native-decision-reuse-20260916`.
It is not installed into the financial runtime. The original full source job,
independent regeneration and downstream account waiter retain their pinned code.

## Implementation and scope

The prior profile showed identical completed-bar calculations for the exact ETH
long and SOL short range-onset providers and their canonical telemetry. The
candidate uses the existing builder injection interfaces to share that result
within a single source window. It retains at most one detached frame and clears
it on both success and failure. Consumers receive separate native decisions and
readiness metrics. Frame values, structure, types, metadata and both clock
arguments participate in equality; differing evidence recomputes.

Only two existing research modules change and two research helpers are added.
Live strategy source, collector defaults and the dependency lock retain their
baseline bytes. HYPE keeps its original implementation because its two observed
calls use different cutoff arguments. BTC and all three XYZ assets also retain
default construction. There is no process-global patch or cross-window cache.

An initial isolation test found that copying nested object cells using `map`
coerced an object column containing `None` and an integer into floats. The
candidate was corrected to preserve the original dtype before benchmarking.
Unsupported metadata disables reuse and delegates computation; computation
failures propagate and cannot leave a successful cached result.

## Validation and timing

- The focused suite passed **65 tests**. Both new production helpers covered
  **91/91 statements and 18/18 branches**, measured by that suite.
- The broader candidate source, calendar, account-prefix, clock, provider and
  frame-isolation suite passed **158 tests in 433.64 seconds**. Two earlier
  invocations did not run this suite because of a nonexistent test path and a
  missing script import path; their logs remain preserved.
- Archive reproduction passed the same **158 tests in 441.13 seconds**.
- The benchmark uses seven assets, two receipt variants, three dates and three
  alternating baseline/candidate pairs per case: 126 pairs, 252 native calls.
  Every output also matches the preceding frozen 42-case native profile.
- Both benchmark modes execute declared candidate-checkout bytes; baseline mode
  uses unchanged default collectors. All **1,441 source/dependency files** are
  authenticated before and after computation. The separate archive reproduces
  **5,789 tracked file contents** and matches all 1,441 benchmark source pins.
- A further **16 cases** use actual, unmocked native computations on fabricated
  hourly onsets: ETH/SOL, entry/opposite-onset exit, inclusive/late entry deadline,
  and first/revised receipts. Complete baseline/candidate publications match,
  expected accepted or withheld entries and exits occur, and canonical evidence
  remains present. These checks execute from the authenticated archive.
- The same archive's source hashes are checked before and after those controls.
  Benchmark and behavioral runs deny network access, credential-file reads and
  writes outside their own evidence directory. No real prospective outcomes are
  opened by these fabricated correctness experiments.

| Asset | Pairs | Median time reduction | Observed pair range |
| --- | ---: | ---: | ---: |
| BTC | 18 | -0.17% | -25.19% to 18.37% |
| ETH | 18 | 43.62% | 25.59% to 51.06% |
| SOL | 18 | 42.03% | 25.10% to 48.22% |
| HYPE | 18 | 0.62% | -16.51% to 12.88% |
| SPCX | 18 | 0.44% | -7.35% to 7.24% |
| SNDK | 18 | -0.18% | -3.25% to 5.08% |
| BRENTOIL | 18 | -1.27% | -6.81% to 2.61% |

Reduction is `1 - candidate_seconds / baseline_seconds` for each pair; negative
values mean slower. Receipt loading finishes before each pair, while source-window
selection and native computation remain timed. Baseline runs first in two of
three repeats, so ordering is retained rather than described as randomized.
Timing variability in unchanged assets illustrates the limits of this small,
shared-machine sample. No reduced ETA applies to already-running experiments.

The mixed benchmark process reached **855,949,312 bytes maximum RSS** on macOS.
That is whole-process memory, including source data and both modes, not isolated
cache overhead. Retention checks establish zero retained frame rows after every
candidate publication; they do not attribute peak process memory to the cache.

The timed ETH/SOL samples were holds. The separate 16 unmocked entry/exit/receipt
controls and eight earlier injected-builder publication controls cover meaningful
nonempty behavior. They still do not establish full sequential account or lifecycle
equivalence across a fourteen-day experiment.

## Decision, alternatives and remaining work

Retain the isolated candidate for research qualification. The expected upside is
faster future native research calculations with unchanged outputs. The alternative
is to keep duplicate computation; the existing full experiments already do so and
remain the comparison evidence. This update has no market-regime preference and
proposes no live leverage, risk, sizing, route or execution change.

The archive test result is retained. Any full-window comparison must be registered separately,
with its own source and evidence pins, without replacing the original experiments.
The highest-value next investigation is whole-window source and downstream account
equivalence once the preserved baseline is available. This is not a promotion gate
based on performance; it tests semantic identity of the implementation.

Wrong outputs or exceptions, mutated consumer inputs, cross-window retention,
changed source identities or slower repeatable ETH/SOL results would reopen or
reject the candidate. Rollback retains baseline commit
`9a5c86145ca30dd1a975e29e03104eb371bc0128` and its immutable archive; no financial
process action is required. Research implementation is already authorized. Any
future financial deployment remains subject to explicit human approval.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/native_decision_reuse_candidate_v1/`.
The candidate archive SHA256 is
`9a4fe5a7e02ac9a3849ecd8f19f9447d2fe7d51713961a09cbe4ccbd48fe019c`.
