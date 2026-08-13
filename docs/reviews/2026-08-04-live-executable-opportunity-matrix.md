# Live executable opportunity matrix

## Problem restatement

The portfolio journal must measure not only accepted trades and realized PnL,
but also directional setups that were withheld by exactly one condition. A
missed move is useful evidence only if it was knowable at routing publication,
could be entered and exited against recorded Hyperliquid BBO, had visible
capacity for the configured canary notional, honored the deployed stop shape,
and remained positive after observed fees and official funding.

Confidence in the measurement implementation is high because causal timing,
capacity, funding bounds, stop exits, and one-position timing are covered by
tests and immutable inputs. Confidence in any trading edge is low because this
matrix covers less than ten hours, has no short examples, and several rows have
only two or three independent executions.

## Fixed contract and known facts

- Window: `2026-08-04T06:50:23Z` through `16:46:33Z`.
- Inputs: the current armed cohort run, per-asset L2 ledgers, deployed provider
  contracts, the account's observed `4.32 bps` taker rate per side, and complete
  official Hyperliquid hourly funding through `17:00Z`.
- Candidate: an ineligible directional evaluation with exactly one blocker.
- Entry: first recorded BBO at or after routing publication, within the
  configured 60-second provider delay.
- Exit: first adverse BBO that crosses the provider stop proxy, otherwise the
  first adverse BBO at or after 60 minutes.
- Capacity: the full configured notional must be visible at the top level.
- Cohorts: directionally aligned OPI, opposed OPI, and all OPI. Each cohort has
  its own non-overlapping selection path and the three results are not additive.
- Scope: nine provider-symbol-blocker hypotheses and 27 comparisons. Every
  result, including losses and sparse rows, is retained. All executions are
  long; no bidirectional claim is supported.

## Results

The most informative `all OPI` rows were:

| Provider / symbol / withheld condition | N | W/L | Net bps | PF | Largest contribution | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| HYPE breakout / HYPE / `5m_not_breakout` | 9 | 6/3 | `+149.99` | `1.93` | `23%` | Broadest and least concentrated positive row; both aligned and opposed cohorts were also positive. |
| Range onset / HYPE / hourly SMA cross | 3 | 3/0 | `+178.59` | no losses | `61%` | Strong but too sparse and concentrated for promotion. |
| Hulk / HYPE / squeeze armed | 5 | 3/2 | `+42.05` | `1.42` | `35%` | Positive after a stop-proxy exit freed a later opportunity; still small. |
| Range onset / BTC / hourly SMA cross | 6 | 4/2 | `+47.05` | `2.21` | `37%` | Positive without an OPI gate, but only six examples. |
| Range onset / SOL / hourly SMA cross | 4 | 3/1 | `+25.15` | `1.39` | `42%` | Modest positive result; aligned-only was stronger at N=5 and PF 1.76. |
| Range onset / ETH / hourly SMA cross | 6 | 2/4 | `-84.55` | `0.35` | `27%` | The existing hourly cross appears protective in this window. |
| Hypervelocity source / BTC / primary onset | 3 | 2/1 | `-30.23` | `0.13` | `89%` | One large loss dominates; relaxing primary onset is not supported. |

The leading HYPE `5m_not_breakout` row is the only current hypothesis with
nearly ten independent examples, positive aligned and opposed subcohorts, PF
above 1.5 in both, and no single trade contributing more than one quarter of
absolute outcomes. This weakens the case for adding an OPI sign gate and
supports a fresh forward challenger that relaxes only the 5m breakout blocker.
It does not establish that the current blocker should be removed from live
execution.

## Uncertainties and failure modes

- BBO snapshots do not prove the exact IOC fill between observations.
- The stop exit is an adverse-BBO proxy; Hyperliquid's trigger and realized
  market fill can differ during a cascade.
- Top-level-only capacity is conservative relative to a visible book walk but
  does not model hidden liquidity or impact beyond the recorded level.
- All examples are long and occurred in one intraday market episode.
- The 60-minute challenger exit differs from several providers' deployed
  maximum-hold policies; this evaluates a new small-edge contract, not the
  historical strategy unchanged.
- Evaluating nine hypotheses creates multiple-comparison risk. The HYPE row is
  selected for forward falsification because of sample breadth and
  concentration, not declared as discovered alpha.

## Validation plan and falsifiers

1. Freeze a report-only HYPE challenger after this cutoff: same causal entry,
   configured `$25` notional, `80 bps` stop proxy, 60-minute exit, no OPI gate,
   and only `5m_not_breakout` relaxed.
2. Journal every new long and short opportunity from live data. Do not seed the
   forward score with these nine retrospective executions.
3. Continue accepted-trade MFE/MAE and post-exit capture beside missed-entry
   outcomes so increased frequency cannot hide degraded exits.
4. Reject the challenger hypothesis if fresh net PF is at or below one, if its
   advantage is carried by a single observation, or if short-side evidence
   contradicts the direction contract.

## Recommendation trade-offs

| Option | Benefit | Failure mode | Recommendation |
|---|---|---|---|
| Remove HYPE 5m blocker from armed live execution now | Immediate frequency | Nine long examples can be one favorable episode | Do not do this yet. |
| Freeze a live-feed report-only challenger | Fresh causal evidence without order risk | Delays capital feedback | Recommended next step. |
| Add OPI alignment as another gate | Conventional confirmation | Both OPI signs were profitable and an extra gate reduces frequency | Not supported. |
| Relax ETH hourly cross | More ETH trades | Six executable examples lost `84.55 bps`, PF 0.35 | Reject for this window. |
| Leave all research telemetry unchanged | No implementation work | Missed-edge evidence remains retrospective and harder to falsify | Inferior to a frozen forward journal. |

No human clarification is required to start the report-only challenger. Live
capital authority remains unchanged unless the user explicitly authorizes a
future execution-contract modification.

## Evidence

- Authoritative matrix:
  `data/logs/research/cohort_execution_opportunity_matrix_20260804T1652Z_v2.json`
  (`3592361c9320e25bf54e6a4966abe158603d6428259bb2e4b1b4a631b30c3374`).
- Matrix `v1` retained later 60-minute prices after a stop proxy crossed. It is
  superseded by `v2`, which exits at the first adverse BBO stop crossing.
- Updated BTC single-hypothesis artifact:
  `data/logs/research/cohort_btc_range_one_blocker_execution_20260804T1627Z_v4.json`
  (`5651d43967f9ee38f140d1a19026242ec890e2b5a8493e998b57e044171296b6`).

The armed backend, orders, position sizing, provider gates, and exits were not
changed or restarted.

## Frozen forward status — 2026-08-04 13:22 EDT

The recommended challenger is now implemented as a separate report-only
contract with cutoff `2026-08-04T16:52:00Z`. It relaxes only
`5m_not_breakout` for the HYPE breakout provider, admits both long and short
directions, applies no OPI sign gate, and retains the fixed `$25` notional,
`4.32 bps` taker fee per side, `80 bps` stop proxy, and 60-minute horizon.

At the first post-cutoff snapshot, 31 repeated minute evaluations matched the
exact blocker. Non-overlapping selection admitted one candidate, and that
candidate remained unresolved because its 60-minute boundary had not arrived.
The forward score therefore remains exactly zero resolved, zero wins, zero
losses, and zero claimed PnL. Raw routing and BBO ledgers continue recording the
candidate path for later deterministic resolution.

The Rust checkpoint parser and Screen 6 now expose the immutable matrix and
frozen forward state independently. The forward status is explicitly labeled
no-execution-authority and cannot alter the armed backend. An actual 160x48
terminal render verified the current values: `CAND 31`, `SELECT 1`, `N0`, and
`L0/S0`.

A five-minute read-only refresher now replays the growing ledger and atomically
replaces only the runtime research attachment. It acquires at most one new
immutable official HYPE funding bundle per hourly window; retryable HTTP or
coverage failures retain the last good matrix. Its first funding-managed pass
advanced the repeated-candidate count to 41 while preserving one independent
selection and zero resolved outcomes. The live backend is not a dependency of
the refresher process and receives no calls or commands from it.

## Forward continuity and first resolution — 2026-08-04 13:53 EDT

The report-only refresher now treats exact-profile armed backend restarts as
one causal evidence stream. It retains the source run on every candidate,
applies each run's own activation boundary, admits only cohort identities with
the deployed profile fingerprint, validates that the matching HYPE asset
execution identity did not drift, and enforces a single non-overlapping
position timeline across run boundaries. A profile change starts a different
experiment rather than silently contaminating this one.

The migration was tested against the same live-ledger prefix before replacing
the old refresher. The old artifact contained 51 exact evaluations, one
selection, and zero resolutions. The new path, observed a few minutes later,
contained 54 exact evaluations, the same one selection, and zero resolutions;
the increase was only newly appended ledger data. It did not reset or reduce
existing evidence.

At `2026-08-04T17:52:47Z`, the first selected path resolved:

| Side | Entry / exit | Gross | Fees | Funding | Net | MFE / MAE | Exit |
|---|---|---:|---:|---:|---:|---:|---|
| Long | `55.317` / `55.476` | `+28.7434 bps` | `-8.6524 bps` | `-0.1250 bps` | `+19.9660 bps` | `+75.3837 / -23.6817 bps` | fixed 60m horizon |

The fixed `$25` notional maps the result to approximately `+$0.049915`; this
is simulated-execution research PnL, not portfolio PnL or proof of an IOC fill.
Coverage at that snapshot was 61 repeated exact evaluations, two independent
non-overlapping selections, and one resolved outcome. The second selection is
pending its own exit boundary.

This observation is favorable but insufficient for promotion: it is N=1,
long-only, has no loss denominator for profit factor, and necessarily has 100%
outcome concentration. Confidence in replay arithmetic is high because the
entry, exit, capacity, fee, funding, and non-overlap contract is directly
validated. Confidence in a repeatable edge remains low. A meaningful fresh
both-side batch with net PF at or below one, persistent single-observation
concentration, or adverse short-side evidence would falsify the challenger.

Screen 6 now projects the resolved-path economics directly from the backend
attachment: pending independent paths, latest side and entry/exit, gross bps,
fee drag, funding, net bps, MFE, MAE, exit reason, and source run. It remains a
read-only view; none of these fields grants order or strategy authority.

## Staged strategy adaptation — 2026-08-04 14:22 EDT

The forward hypothesis now has a separate live-capable candidate contract,
`hype_breakout_relaxed_60m_bidirectional_v1`, in
`configs/multi_asset_bidirectional_hype_relaxed_candidate.toml`. The running
profile and armed backend were not changed.

The candidate alters only the entry family and measured hold shape:

- HYPE long and short are both declared.
- Eligibility requires the canonical readiness blockers to equal exactly
  `("5m_not_breakout",)`. Canonical breakout onsets are not duplicated.
- OPI remains report-only and has no entry authority.
- HYPE retains `$25` maximum notional, `5x` isolated leverage, and an `80 bps`
  fixed stop. The candidate has no target and exits at a fixed 60-minute
  maximum hold.
- Priority `35` loses a same-cycle conflict to the canonical HYPE breakout at
  priority `40`.
- `flat_entry_only` prevents this entry challenger from closing or reversing
  any existing HYPE position. This is necessary because the shared router's
  legacy behavior otherwise treats an opposite provider intent as a close.

The cadence clock uses accepted entry actions rather than raw intent
publication. A withheld candidate is therefore offered again on the next fresh
bar instead of being incorrectly counted as a trade. Once accepted, its
60-minute re-arm is recovered incrementally from the append-only cohort ledger
and survives a process restart. Malformed, truncated, incomplete, or non-UTF-8
recovery state fails closed.

This staged profile is not active because BTC is currently open and activating
a different profile requires a backend restart. The current profile's computed
fingerprint still exactly matches the latest live configuration identity. The
candidate should be activated only after the cohort is flat, then evaluated by
the same accepted/withheld/missed journal. The next material falsifiers remain
fresh PF at or below one, outcome concentration that does not fall with added
examples, and adverse short-side evidence.

Confidence in contract fidelity is high because both-side eligibility,
freshness, accepted-action cadence, restart recovery, entry-only routing,
priority, protection, sizing, and fixed hold are covered by tests. Confidence
in profitability remains low because the independent forward evidence is one
resolved long and no resolved short.

## Shared-portfolio compatibility — 2026-08-04 14:46 EDT

Independent BBO replay alone cannot establish that a candidate could have
joined the live portfolio. The forward refresher now binds each selected
attempt to its exact source run and routing publication, then uses only the
latest strictly-prior cohort snapshot from that same run. It classifies symbol
position conflicts, portfolio-capacity conflicts, same-cycle HYPE actions, and
unavailable state separately. Ambiguous routing or malformed snapshots fail
closed.

Both selected post-cutoff attempts were `deployable_flat_entry`: HYPE was flat,
the account had one open position against a four-position maximum, three slots
were available, and the router emitted neither a HYPE action nor a HYPE
withheld route. The first resolved at `+19.9660 bps` net and the second remains
pending. This strengthens the claim that the first path was operationally
available, but it does not strengthen repeatability beyond N=1 and does not
convert simulated PnL into portfolio PnL.

The next staged profile also removes automatic execution authority from
`range_onset_bidirectional_v1`. The provider remains present for telemetry with
an empty execution-symbol set, allowing missed-opportunity analysis without
placing orders. This decision is based on the current compatible live sample:
one closed ETH range-onset trade, one loss, `-$0.17438` net, and PF `0.00`.
That sample is too small to prove the strategy is intrinsically unprofitable,
but it provides no evidence for continued canary authority. Fresh observation
evidence with repeatable after-friction PF above one would update that decision.

## V1 re-entry diagnosis and prospective V2 — 2026-08-04 15:01 EDT

The second V1 path resolved long at `55.478 -> 55.517`. Its
`+7.0298 bps` gross move did not clear two-sided taker friction and funding:
fees were `-8.6430 bps`, funding was `-0.0786 bps`, and net was
`-1.6918 bps` (`-$0.004229` at the fixed `$25` research notional). The entry
followed the first path's fixed-horizon exit by roughly 17 seconds. V1's
accepted-entry spacing equaled its 60-minute hold, so it admitted immediate
same-family re-entry.

At this diagnostic snapshot, V1 had two resolved deployable longs, 1W/1L,
`+18.2742 bps` total net, PF `11.80`, and `92.19%` largest absolute outcome
concentration. PF is numerically defined because the second path supplied a
small loss denominator, but it is not reliable evidence of repeatability at
N=2. The immutable snapshot is
`data/logs/research/cohort_hype_relaxed_v1_forward_resolution_20260804T1853Z.json`.

V2 is a prospective contract change rather than a post-hoc rewrite of V1:

- Strategy identity is `hype_breakout_relaxed_60m_bidirectional_v2`.
- Exact `5m_not_breakout` eligibility, long/short scope, no OPI gate, `$25`
  notional, `5x` leverage, `80 bps` stop, and the 60-minute fixed hold remain.
- Accepted entries must be at least 75 minutes apart. This creates a scheduled
  15-minute buffer after the fixed hold and a longer buffer after an early
  protective exit.
- Its evidence cutoff is `2026-08-04T18:58:00Z`. V1 outcomes are excluded.

The first V2 selection is portfolio-deployable and unresolved. Its current
score is therefore N0, 0W/0L, zero claimed PnL, and no short-side evidence.
Immediate-reentry recurrence, after-friction PF at or below one, or persistent
one-sided/concentrated outcomes would falsify the revised contract.

## V2 pending-path and stop-resolution correction — 2026-08-04 15:23 EDT

The forward replay originally deferred stop-proxy resolution until a book near
the full fixed horizon existed. That was causally wrong for an already-observed
stop crossing. The observer now resolves the first adverse BBO stop immediately
and classifies a genuinely open, non-stopped path as `exit_pending`. Pending
paths expose current after-fee/funding mark estimates, MFE, MAE, remaining time,
and BBO exit capacity, but remain excluded from wins, losses, and PnL.

At `2026-08-04T19:17:21Z`, the first V2 long remained pending at an estimated
`+9.4477 bps` net, with `+28.6838 bps` MFE, `-28.8642 bps` MAE, and about
41.2 minutes remaining. This is path telemetry, not a resolved outcome.

The compatible live canonical HYPE sample is favorable but small: five closes,
four wins, one loss, `+$1.234701` net, PF `6.5141`. It does not override the
negative 365-day deployed-shape result. A structure-support threshold of 0.75
would have removed two profitable live trades totaling about `$1.132` while
retaining only PF `1.4588`; the current evidence therefore contradicts adding
that gate. The fixed 60-minute V2 exit and 75-minute accepted-entry spacing are
the prospective changes under test.

## V2 resolution and target-first V3 selection — 2026-08-04 16:15 EDT

V2's first independent path resolved at the fixed 60-minute boundary. It was a
HYPE long from recorded ask `55.432` to adverse bid `55.529`: `+17.4989 bps`
gross, `-8.6476 bps` two-sided taker fees, `-0.1250 bps` funding, and
`+8.7264 bps` net. The fixed `$25` research notional maps this to
`+$0.021816`. Path MFE was `+28.6838 bps`, MAE was `-40.0491 bps`, and the
80 bps stop proxy did not cross. HYPE was flat at entry, one of four portfolio
slots was occupied, and no same-cycle HYPE action or withheld route competed.
The outcome was therefore operationally deployable under the journal model,
but it remains a simulated BBO estimate rather than proof of an IOC fill.

The V2 result is preserved at
`data/logs/research/cohort_hype_relaxed_v2_forward_resolution_20260804T2002Z.json`
(SHA-256
`15e77d12daedcda86eaadf255c7e6266621973bc2340136398b86f53c9afa336`).
Its honest evidence state is N1, 1W/0L, long-only, 100% contribution
concentration, and no defined profit factor.

The independently frozen V3 path reached its 20 bps target in about 6.76
minutes at `55.250 -> 55.376`: `+22.8054 bps` gross, `-8.6499 bps` fees,
zero funding settlement, and `+14.1556 bps` net. It was also portfolio
deployable. Its immutable snapshot is
`data/logs/research/cohort_hype_target20_v3_forward_resolution_20260804T2002Z.json`
(SHA-256
`7cb130fe4b9e1839a8a708ea0ab42d9237caeb642ac2c663d67756b6173fb81e`).
V3 is likewise N1, 1W/0L, long-only, and 100% concentrated.

These experiments are not additive: the V3 entry occurred while the separate
V2 experiment's fixed-horizon position was still open. They compare exit
policies, not a portfolio capable of holding both. V3 is selected for the next
flat-restart canary because the 20 bps target was generated from three earlier
paths and then independently crossed by the first post-cutoff V3 path. This is
a bounded canary decision under uncertainty, not a durable profitability
claim.

The staged live-capable contract is
`configs/multi_asset_bidirectional_hype_target20_candidate.toml`: exact
`5m_not_breakout`, long and short, no OPI entry gate, `$25` at `5x` isolated,
`80 bps` fixed stop, `20 bps` fixed target, 60-minute fallback, 75-minute
accepted-entry spacing, and `flat_entry_only` routing. It has an independent
strategy identity and cadence clock, so V2 accepted actions cannot consume V3
re-arm state. The running live backend remains unchanged while BTC is open.

Confidence in contract and replay mechanics is high from causal tests and
immutable ledger hashes. Confidence in repeatable profitability is low. Fresh
PF at or below one, persistent concentration, adverse short-side outcomes,
material target-fill degradation versus BBO, or portfolio incompatibility
would falsify or revise the V3 selection.

## Matched-entry exit-policy correction — 2026-08-04 18:45 EDT

Fresh V3 evidence falsified the target-first selection after two resolved
paths: one target win and one fixed-horizon loss produced `-33.3810 bps` net,
PF `0.2978`, and `77.05%` largest absolute-outcome concentration. Both paths
were long, so no short-side claim is available.

A report-only matched-entry replay now holds V3's cutoff, accepted-entry
spacing, entry BBO, stop, notional, fees, funding, and portfolio-compatibility
contract constant while removing only the 20-bps target. On the same two
resolved entries, fixed 60 minutes produced `-4.0098 bps` net and PF `0.9156`.
The first path improved from `+14.1556` to `+43.5268 bps`; the second remained
`-47.5366 bps` because it never reached the target. A third matched path is
pending and is excluded from both summaries.

This isolates the target as harmful in the observed pair, but it does not
establish the fixed-horizon contract as profitable: PF remains below one,
N=2, and all evidence is long-side. Neither candidate should receive execution
authority from this result. A later resolved third path updates the descriptive
statistics but does not retroactively change the frozen entry or exit rules.

Evidence:
`data/logs/research/cohort_hype_fixed60_matched_v4_20260804T2245Z.json`
(`d35a00abbf7abcade8189b81d35e3ad0a0bcd0db287817cc274eed4e6f7e3147`).

## Causal entry-context journal — 2026-08-04 18:57 EDT

Each forward attempt and resolved execution now retains a bounded set of
decision-time entry features rather than requiring a later join back to the raw
routing ledger. The payload includes feature provenance, 5-minute state,
structural direction, breakout volume and clearance, BBWP, regime strength,
directional returns, EMA gap, RSI distance, and 1-minute/15-minute alignment.
Unrelated provider internals are excluded.

The report derives an untuned 5-minute directional stance from the existing
regime taxonomy: `TREND_UP` is aligned with a long and opposed to a short;
`TREND_DOWN` is aligned with a short and opposed to a long; breakout, range,
and transition are neutral. It reports aligned, opposed, neutral, unavailable,
and exact-state outcome summaries with explicit coverage. The taxonomy has no
execution authority and no fitted threshold.

The first two resolved V3 paths were both neutral `RANGE` entries and together
remain `-33.3810 bps`, PF `0.2978`. The third pending long entered while the
5-minute state was `TREND_DOWN`; it is excluded until resolved. This is a
useful prospective distinction, not evidence for immediately adding a regime
gate. The prior 365-day entry-attribution analysis found no stable standalone
volume, BBWP, strength, or EMA-gap threshold, so selecting one from these three
paths would be post-hoc overfitting.

Hash-linked context snapshots:

- Target-first V3:
  `data/logs/research/cohort_hype_target20_v3_entry_context_20260804T2250Z.json`
  (`e02c821ac1c003604f11fc7be265af6d66d90f83144ec727c1bfdb357f14ed46`).
- Fixed-60 matched V4:
  `data/logs/research/cohort_hype_fixed60_v4_entry_context_20260804T2250Z.json`
  (`f1d97dba5175de0a1da272368295160301d54e98e71138f45db383b6a64b2956`).

The report-only refresher was restarted on the updated code and the runtime
attachment now carries this context. The armed backend and BTC orders were not
restarted or modified.

## N3 matched-exit resolution — 2026-08-04 19:20 EDT

The third V3 path reached its 20-bps target before the fixed 60-minute
boundary. It was a deployable HYPE long from `55.159` to `55.306`, producing
`+26.6502 bps` gross, `-8.6515 bps` fees, `-0.1250 bps` funding, and
`+17.8737 bps` net. V3 therefore finished the frozen three-entry batch 2W/1L,
but remained negative at `-15.5073 bps` total net with PF `0.6738`. The largest
absolute contribution fell to `59.74%`; all three paths remained long.

The target-free V4 control used the exact same cutoff, selected entries,
notional, stop, fees, funding, and portfolio-compatibility decisions. Its third
path exited at the fixed boundary at `55.279` for `+12.9809 bps` net. Across
all three matched entries it produced 2W/1L, `+8.9711 bps` total net, PF
`1.1887`, and `45.69%` largest absolute-outcome concentration.

| Exit policy | N | W/L | Net bps | PF | Largest contribution |
|---|---:|---:|---:|---:|---:|
| 20-bps target, 60m fallback | 3 | 2/1 | `-15.5073` | `0.6738` | `59.74%` |
| Fixed 60m, no target | 3 | 2/1 | `+8.9711` | `1.1887` | `45.69%` |

The fixed policy improved the matched batch by `+24.4784 bps`, isolating the
target-first exit as harmful in this sample. This does not establish a
promotable edge: N=3 is small, all observations are long, and one loss still
accounts for nearly half of absolute outcomes. The V3 candidate remains
falsified and unstaged. V4 remains report-only and now receives the rolling
forward attachment so additional long and short examples update the same
frozen hypothesis without changing live execution.

Evidence:

- Target-first V3 N3:
  `data/logs/research/cohort_hype_target20_v3_resolution_n3_20260804T2314Z.json`
  (`ce9cc7b888cc98a6b220676671dac691bb5e77c7dce7e44a27e77b8ceeecff76`).
- Matched fixed-60 V4 N3:
  `data/logs/research/cohort_hype_fixed60_matched_v4_resolution_n3_20260804T2318Z.json`
  (`0c1b3d1e8e67fa88eca7b83284e7022f0a454b8dd7adea21d956da79f81ccfd2`).

Confidence in the matched arithmetic and operational compatibility is high
because the entries and non-exit variables are identical and hash-frozen.
Confidence in repeatable profitability is low. A larger both-side batch with
PF at or below one, renewed outcome concentration, capacity failures, or
material BBO-to-fill degradation would falsify the remaining V4 hypothesis.

## Concurrent prospective observers — 2026-08-04 19:59 EDT

The rolling checkpoint now retains the HYPE V4 fixed-60 observer as its primary
frozen challenger and attaches the BTC structural fixed-60 observer as a
separate supplemental contract. Candidate strategy identities must be unique;
both nested contracts remain report-only with `execution_authority=none`, no
automatic promotion, and no portfolio-PnL claim. A named observer that is
missing or violates that boundary makes the checkpoint unavailable.

The live Rust projection was exercised against the current checkpoint at
165x48. Screen 6 rendered both independently: HYPE V4 at N3, 2W/1L,
`+8.9711 bps`, PF `1.1887`, plus one pending path; BTC structural at N0 with
one pending candidate classified as an existing-BTC-position conflict. The BTC
record carries only the decision-time features that were actually available;
the schema validates partial fields individually rather than fabricating the
HYPE feature set.

Confidence in the attribution and read-only boundary is high from the live
checkpoint and strict parser proof. Confidence in BTC profitability is low:
the prospective set has no resolved outcomes, the current candidate is long,
and it cannot be deployed while Hulk owns BTC. A resolved both-side sample
with PF at or below one, material BBO-to-fill degradation, or persistent
portfolio conflicts would falsify or revise the challenger.
