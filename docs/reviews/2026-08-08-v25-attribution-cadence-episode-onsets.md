# V25 attribution cadence and episode-onset review

## Problem and acceptance criteria

The portfolio opportunity audit already removed same-minute duplication across
providers, but it could still count one persistent readiness condition at
hourly intervals as multiple independent entry opportunities. That would be
inconsistent with the live portfolio's one-position-per-coin constraint.

Acceptance requires the report-only audit to:

1. retain the exact source run, symbol, side, provider, and blocker set;
2. disclose minute coverage and interarrival cadence;
3. split consecutive annotations into distinct episodes;
4. evaluate causal episode onsets at the existing 5/15/30/60-minute horizons;
5. report sensitivity to the largest close outcome; and
6. retain zero execution, sizing, routing, filtering, exit, or promotion
   authority.

## Implementation and validation

`cohort_portfolio_opportunity_dedup.py` now partitions attribution by source
run as well as symbol, side, and exact provider/blocker membership. Each row
reports decision-minute coverage, interval statistics, episode count and
duration, and single-minute episode count. A missing minute terminates the
current episode. Each horizon retains the original raw and non-overlapping
path summaries and adds a separate episode-onset summary with exact independent
path evidence.

`summarize_path_opportunities` also reports the mean after the fixed friction
hurdle with the largest close removed. A one-sample result is null rather than
silently reusing the same observation.

The red-green tests covered missing source-run identity, one- and two-minute
cadence, discontinuity-based episode splitting, exact onset path evidence, and
largest-close sensitivity. Verification results:

- focused signal, candidate, metric, orderbook, opportunity, and delta tests:
  `46 passed`;
- complete non-network Python suite: `4,118 passed`, four deselected, 27 known
  warnings;
- Ruff and formatting: passed;
- diff whitespace: passed;
- affected production files: all below 500 lines;
- affected functions: none above 50 lines.

No Rust/TUI source changed in this increment, so Rust results would not verify
the Python audit behavior and were not rerun.

## Measured live-prefix evidence

The immutable report-only audit is:

`data/logs/research/bidirectional_cohort/v25_live_prefix_episode_onsets_bidirectional-live-1786182011216_20260808T183622Z.json`

SHA-256:
`d1d340ae3eec51bd86ebb43050cd1ebc72456ad43b705c2c950af793d8221c6f`

The 18:36:23 UTC prefix contains 3,374 one-blocker provider observations and
2,213 unique directional paths. It removes 1,161 duplicate provider
observations; 1,019 unique paths have cross-provider overlap, one timestamp has
opposing-direction competition, and no reference-price conflict was accepted.

Portfolio-wide independent five-minute evidence remains negative after the
fixed 13 bps hurdle: 23 of 502 closes clear the hurdle, 13 of 502 paths have
robust MFE, and mean close after hurdle is -12.85 bps. At 60 minutes, 14 of 57
independent closes clear the hurdle, but the mean is -6.10 bps and the
leave-largest mean is -10.36 bps.

### SOL HT-Breakout `5m_not_breakout`

- 519 annotation minutes span 534 minute boundaries: 97.19% coverage.
- Those minutes collapse to four episodes, with a 143.5-minute median duration
  and a 212-minute maximum duration.
- Three non-overlapping 60-minute episode onsets resolved. All three close
  returns clear the 13 bps hurdle.
- Mean after hurdle is +14.90 bps; excluding the largest result it is +4.71
  bps. The individual after-hurdle closes are approximately +2.77, +6.65, and
  +35.30 bps.

This is a cleaner positive hypothesis than the earlier eight hourly samples,
but three onsets from one intraday run do not establish a repeatable execution
edge. The deployed SOL HT-Breakout lifecycle is still open, so there is no
resolved exact-provider live lifecycle with which to reconcile the candidate.

### SPCX Swing/HA `pivot_break_state_missing`

- 20 annotations are 20 distinct episodes over 466 minute boundaries.
- Six non-overlapping 60-minute episode onsets resolved; three clear the fixed
  hurdle.
- Mean after hurdle is +37.24 bps, but excluding the largest close changes it
  to -1.74 bps.
- The exact deployed provider has one resolved live loss of -$0.656872 and one
  open provisional lifecycle.

The positive mean is therefore concentrated in one move and does not confirm
the candidate.

## Decision and trade-offs

| Option | Evidence | Decision |
|---|---|---|
| Remove SOL's 5m breakout blocker now | Three positive episode onsets; no resolved exact-provider live lifecycle | Do not promote; continue causal observation |
| Promote the SPCX pivot-state relaxation | Six independent paths, but leave-largest mean is negative and the only resolved live trade lost | Do not promote |
| Restart or alter v25 while four positions are protected | No technical need and open lifecycle evidence is provisional | Do not restart or mutate |
| Keep v25 running and accumulate episode-onset plus venue-lifecycle evidence | Preserves live friction data and falsifies both hypotheses directly | Selected |

This decision is evidence reporting, not an implicit strategy gate. Performance
continues to be recorded as a trial result under `SRS_HV1_NO_GATES`.

## Uncertainty, failure modes, and falsifiers

Infrastructure confidence is high because source-run partitioning, episode
splitting, evidence identity, and report-only authority have direct automated
coverage. Economic confidence is low because the strongest SOL result has
three independent episode onsets from one market window, while SPCX is
outlier-sensitive.

The assessment changes if future causal episode onsets materially expand the
sample while retaining positive after-friction and leave-largest results,
especially if resolved exact-provider venue lifecycles agree. It is falsified
technically by cross-run attribution mixing, a missed minute discontinuity,
changed immutable evidence, execution authority in the report, or any live
process/order/position mutation caused by the audit path.

