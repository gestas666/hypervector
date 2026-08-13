# Forward challenger portfolio resolution

**Decision timestamp:** 2026-08-05 13:05 EDT  
**Run:** `bidirectional-live-1785826133777`  
**Execution authority:** report-only; no live route, order, position, active
profile, or staged profile was changed

## Question and comparison grain

Determine which frozen one-blocker challengers add plausible value to the
shared four-position portfolio after their prospective cutoffs. Discovery rows
remain excluded. Mechanism outcomes and portfolio-deployable outcomes are
reported separately because the account permits only one position per symbol.

Each observer uses the first recorded adverse Hyperliquid BBO after the routing
publication for entry, a fixed 60-minute adverse-BBO exit, taker fees, observed
funding, and a frozen stop proxy. These are execution-aware estimates, not
venue fills or a compounded portfolio path. Every candidate remains formally
bidirectional, but every resolved path in this review is long.

## Evidence identity

Each source report declared complete stable ledger prefixes with zero dropped
tail bytes. All eight asset/cohort prefix hashes below were independently
reproduced before this review was written.

| Candidate | Generated UTC | Asset bytes / SHA-256 | Cohort bytes / SHA-256 |
|---|---|---|---|
| BTC structural | `2026-08-05T17:01:28.524279Z` | `74727578` / `81f15e9d7bdc...` | `383410264` / `ea7abac92669...` |
| HYPE Hulk squeeze | `2026-08-05T17:01:34.361355Z` | `61431925` / `a7402d9755d1...` | `383441957` / `efb959463a1b...` |
| HYPE range absorption | `2026-08-05T16:57:36.619605Z` | `61361104` / `94aaeeb37c2c...` | `382859845` / `3c4787e6243c...` |
| SOL aligned range | `2026-08-05T17:02:44.680006Z` | `55682021` / `bcd688359c17...` | `383587180` / `7a220ff7edd9...` |

Complete hashes:

- BTC asset `81f15e9d7bdc56ffbbed3b89790b7ce827dd34e5ed5b9255488b1b2b7859e9e9`;
  cohort `ea7abac9266937d26ce35d4b1bb9a7fcb180e372afcb4c556821c66cc2aaea9b`.
- HYPE Hulk asset `a7402d9755d190a2c34913a2c91a16f3259bdb320ede93574e38a8505c0cda9b`;
  cohort `efb959463a1bd10e6b59a98bb53042dc546ce6adb0db92ff50c5bf44e92bad36`.
- HYPE absorption asset `94aaeeb37c2c9fb658a111823d09b9c85b88722374b00a7563b83f1775013f1d`;
  cohort `3c4787e6243c4fddac7a8033931c4aae003d1791c09fb29e450d322e737c1e1e`.
- SOL asset `bcd688359c175153c267b8989a857b2215adb52be12212a726a5658b3c63f7ff`;
  cohort `7a220ff7edd922683eab2cc938fd17a08b145700f75bed4b83091238ae8bcd60`.

## Prospective results

| Frozen candidate | Resolved | W/L | PF | Net bps | Deployable | Deployable result |
|---|---:|---:|---:|---:|---:|---|
| `btc_structural_continuation_fixed60_bidirectional_v1` | 11 | 4/7 | `0.4794` | `-77.3943` | 0 | all 11 overlapped an existing BTC position |
| `hype_hulk_squeeze_relaxed_fixed60_bidirectional_v1` | 6 | 3/3 | `0.3541` | `-133.1835` | 0 | all 6 overlapped an existing HYPE position |
| `hype_range_absorption_fixed60_bidirectional_v1` | 6 + 1 pending | 3/3 | `2.0847` | `+89.4632` | 1 resolved | 0W/1L, `-74.5464` bps; six overlapped HYPE |
| `sol_aligned_range_relaxed_fixed60_bidirectional_v1` | 9 | 4/5 | `0.3472` | `-113.0855` | 9 | identical to mechanism result |

The largest absolute contribution fractions were `22.25%`, `33.10%`,
`50.55%`, and `33.24%`, respectively. The HYPE absorption aggregate is the
only superficially positive mechanism row, but half of its absolute result is
concentrated in one path and its only resolved portfolio-available attempt
lost. Treating the six overlapping paths as portfolio profit would violate the
one-position-per-symbol contract.

The BTC Hulk money-flow observer remains a separate zero-sample hypothesis:
`10942` evaluations, `0` post-cutoff exact candidates, and `0` portfolio
attempts as of `2026-08-05T17:00:28.568665Z`. The older HYPE target-20 artifact
is not a continuously refreshed candidate and its one resolved forward path
does not overturn the previously falsified relaxed target-20 cohort.

## Decisions

### Reject BTC structural continuation v1

The exact hourly-cross relaxation is negative on eleven prospective paths and
adds no observed portfolio capacity because BTC was already occupied every
time. Keep its report-only measurements, but do not promote or combine it with
the current BTC provider.

**Confidence: medium.** Eleven long-only BBO estimates do not establish short
behavior or real fills. A causally changed mechanism must receive a new
identity and cutoff; additional observations of the unchanged rule remain
diagnostic rather than rescuing this revision.

### Reject HYPE Hulk squeeze v1

The exact squeeze relaxation is negative on six prospective paths and every
path overlaps the stronger canonical HYPE position. It currently supplies
neither standalone mechanism evidence nor portfolio diversification.

**Confidence: low-to-medium.** The sample is six and long-only. A new mechanism
or truly deployable non-overlapping paths would require a new decision, but the
current frozen rule is not an execution candidate.

### Continue HYPE range absorption as observe-only

The mechanism aggregate is positive, while the portfolio-compatible evidence
is one loss with one attempt still pending. Preserve the observer because this
disagreement is informative; do not call the overlapping winners missed
portfolio trades and do not grant order authority.

**Confidence: low.** More non-overlapping HYPE-flat paths, including shorts,
are required. Positive deployable PF and net return across multiple windows
would strengthen the hypothesis; additional deployable losses would reject it.

### Reject SOL aligned range v1 for execution

All nine paths were deployable and the candidate produced PF `0.3472` and
`-113.0855` bps. This strengthens the earlier N=5 falsification and supports
its removal from the staged profile. The unchanged observer may keep reporting
outcomes under the ungated-experiment charter.

**Confidence: medium.** Portfolio compatibility is complete, but every path is
long and uses BBO estimates. A materially changed rule requires a new identity
and prospective cutoff rather than retrospective parameter selection.

## Failure modes and next evidence

- A path before its declared cutoff, missing funding interval, incomplete
  ledger tail, stale context, or reproduced prefix-hash mismatch invalidates
  the affected decision.
- Estimated BBO outcomes must not be added to live portfolio PnL or called
  fills.
- Overlapping same-symbol paths must not be called deployable opportunities.
- Short-side evidence remains absent for all four candidates.
- The BTC Hulk flow observer remains active until a fresh exact candidate
  appears; zero samples are not losses or wins.
- The current canonical HYPE lifecycle remains the live priority and continues
  to generate actual fill, cost, exit, and missed-opportunity evidence.
