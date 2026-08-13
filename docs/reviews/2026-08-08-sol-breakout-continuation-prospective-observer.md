# SOL breakout continuation prospective observer

Date: 2026-08-08

## Problem and success criteria

The active SOL breakout provider requires a fresh completed-five-minute
breakout onset. The current v25 opportunity matrix found two later evaluations
that satisfied the remaining source conditions, were blocked only by
`awaiting_new_5m_breakout_onset`, and had side-adjusted visible-book pressure
aligned with the proposed long side.

The hypothesis is that this exact class may represent a continuation after the
initial onset rather than indiscriminate same-episode re-entry. Success requires
prospective, non-overlapping, both-side, after-cost evidence that remains
positive without its largest winner. The observer must not change v25.

## Frozen contract

- Candidate identity:
  `sol_breakout_continuation_aligned_fixed60_bidirectional_v1`.
- Source: `hype_breakout_onset_bidirectional_v1|SOL`.
- Exact omitted blocker: `awaiting_new_5m_breakout_onset`.
- Prospective cutoff: 2026-08-08 22:50:00Z.
- Side policy: retain source long and short; require side-adjusted OPI aligned.
- Entry spacing: 75 minutes between accepted candidate observations.
- Execution estimate: adverse recorded BBO with current source delay bounds.
- Cost model: observed Hyperliquid funding plus 4.32-bps taker fee per side.
- Exit: fixed 60-minute BBO estimate, no target, with an 80-bps stop proxy.
- Notional: $75 for capacity measurement, not portfolio allocation authority.
- Authority: report-only; no entry, exit, sizing, gating, or promotion.

## Hypothesis-formation evidence

The immutable v25 matrix resolved two all-long paths:

| Resolved | W/L | Net bps | Net excluding largest winner | Largest absolute share |
|---:|---:|---:|---:|---:|
| 2 | 2/0 | +45.9418 | +16.3241 | 64.47% |

This is weak formation evidence. It covers one side, one market window, and two
paths. It justifies measurement, not execution.

The older HYPE cooldown result remains a separate control: repeated-onset HYPE
near misses were negative in their initial window. The older SOL aligned
`5m_not_breakout` experiment is also a different blocker and identity. None of
these samples are pooled.

## Validation and failure modes

The long-running observer is launchd job
`com.hypervector.v25.sol-breakout-continuation`. It refreshes every five
minutes, reads only the armed v25 ledgers and public funding, and writes:

- checkpoint:
  `data/runtime/bidirectional_cohort/latest_sol_breakout_continuation_challenger.json`;
- log:
  `data/runtime/bidirectional_cohort/sol_breakout_continuation.launchd.log`.

The initial end-to-end run reported
`awaiting_fresh_post_cutoff_candidate`, zero resolved paths, and
`execution_authority=none`, as expected before the cutoff.

Technical acceptance requires the exact run/profile identity, intact frozen
cutoff, complete funding coverage, fresh BBO context, no capacity failure, and
unchanged both-side source authority. Any mismatch fails the refresh and keeps
the previous complete checkpoint.

Economic assessment requires:

1. non-overlapping post-cutoff candidate episodes;
2. independently reported long and short results;
3. after-cost net return and profit factor;
4. positive net result after removing the largest winner;
5. adverse BBO capacity at the frozen notional; and
6. comparison with the deployed fresh-onset control without pooling identities.

The hypothesis is weakened by nonpositive ex-largest-winner economics,
one-sided dependence, repeated adverse shorts, stop-proxy concentration,
capacity failures, or a result confined to one episode. It is invalidated by
source, profile, cutoff, side, funding, or implementation identity drift.

## Recommendation

Keep v25 unchanged and collect the observer prospectively. Do not remove the
live fresh-onset requirement or stage a successor from the two formation paths.
If the frozen observer later produces repeatable both-side after-cost evidence,
the next step is shared-portfolio interaction replay under a new candidate
profile and a separate explicit live authorization.

Confidence is high that the observer is technically report-only and bound to a
future cutoff, but low that its economic hypothesis is true. A routed order,
runtime strategy change, pre-cutoff inclusion, or identity mismatch would
falsify the technical claim; the post-cutoff outcomes will update the economic
claim.
