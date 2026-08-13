# v25 live continuation audit — 2026-08-08

## Problem restatement

The active v25 mainnet canary must continue producing attributable live evidence
without a duplicate owner, an unprotected position, a hidden execution gate, or
a strategy change inferred from an unresolved lifecycle. The immediate decision
is whether the post-rearm evidence supports changing entry or exit behavior.

## Authoritative evidence

- Run: `bidirectional-live-1786182011216`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- Profile fingerprint:
  `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`.
- Immutable audit:
  `data/logs/research/bidirectional_cohort/v25_live_continuation_20260808T1015Z.json`.
- Audit SHA-256:
  `501ebf7f966b3cf663a9f351bf835e3474cd47b3b2e9985b980880abdac5bfd9`.
- Audit size: `4,923,356` bytes.
- Covered interval: `2026-08-08T09:42:42.693627Z` through
  `2026-08-08T10:15:01.892245Z`.
- The audit is report-only, has no execution authority, reports complete
  coverage, and has no technical gaps.

## Observed runtime state

- Backend state was `running_consistent` with zero asset faults.
- ETH, SOL, and `xyz:GOLD` were open and each had exactly one owned protective
  stop. The remaining six configured assets were flat and order-free.
- The run had 76 routing cycles, zero selected actions, zero withheld actions,
  and zero post-rearm fills.
- All 24 executable provider-symbol mappings emitted readiness evidence. There
  were no missing mappings and no hidden route-coverage explanation for the
  absence of new entries.
- The two resolved trades and `+$0.024252` compatible-history net PnL were
  adopted lifecycle history. They are not post-rearm profit.

## Entry evidence

The audit resolved independent, non-overlapping forward paths for exact
one-blocker observations. Every resolved independent mean close return remained
negative after the predeclared 13-bps round-trip friction estimate. A few paths
crossed the cost hurdle intraperiod and then reversed, but none supplied a
positive independent mean close result.

Conclusion: the current prefix does not support removing or relaxing an entry
condition. This conclusion does not pause or gate v25; the configured routes
remain live and executable under the project charter.

## Exit evidence

The open SOL HT-Breakout long is the most informative unresolved lifecycle:

- Entry: `74.457`, size `1.0`, isolated `5x`.
- At the audit boundary its venue-synchronous mark was `74.8893` and its active
  lifecycle marked net PnL was `+$0.393597` after recorded entry costs and
  funding, before an estimated future exit cost.
- Its completed path reached `+88.24` bps MFE and had given back `30.18` bps.
- All three predeclared causal profit-lock challengers had already triggered
  before the audit boundary.
- The actual v25 exit contract remained unchanged: 8-hour soft deadline,
  extension while directionally supported, 24-hour hard deadline, and the
  existing venue stop.

Historical live-mechanism evidence does not justify switching the open
lifecycle mid-trade. Across prior HT-Breakout lifecycles, the profit-lock family
usually reduced realized winners. On the two resolved SOL HT-Breakout
lifecycles, the 25/15/10 and 40/15/20 variants improved the negative baseline
but still had normalized profit factors below one. The current profitable SOL
lifecycle is therefore a forward discriminator: its eventual actual exit can
show whether the existing hold adds value or gives back more than the
predeclared locks.

## Telemetry correction

The running code can report HIP-3 Swing readiness as `4/4` plus
`indicator_warmup` when all persistent confirmations align but a fresh entry
onset is absent. The staged correction makes onset an explicit fifth condition:
aligned without onset becomes `4/5` plus `fresh_entry_onset_absent`; missing
state-mode entry trigger becomes `entry_state_absent`. Execution eligibility is
unchanged.

Verification:

- Ruff passed for the modified provider and tests.
- 77 focused Python tests passed.
- The complete Rust unit/integration target set passed.

The correction is not loaded by the open-position backend. It should be loaded
at a verified flat restart boundary, or only through a separately proven
position-adoption recovery procedure.

## Decision and trade-offs

| Option | Evidence | Decision | Trade-off |
|---|---|---|---|
| Relax an entry blocker | Independent resolved paths remain negative after 13 bps | Reject for this prefix | Preserves current selectivity; may miss a future regime where the blocker is unnecessary |
| Hot-enable a SOL profit lock | Current SOL path would have triggered, but prior live mechanism evidence is mixed or adverse | Do not mutate the open lifecycle | Preserves a clean forward comparison; permits additional giveback before the existing exit |
| Continue unchanged v25 | Runtime is healthy, protected, and all routes are emitting | Continue | Accumulates real evidence without claiming edge from zero post-rearm fills |
| Restart for telemetry display fix | Fix is verified but positions are open | Defer to a safe boundary | Running cockpit retains one known misleading readiness label until restart |

## Validation and falsifiers

The next economic boundary is an actual resolution of ETH, SOL, or GOLD, with
SOL HT-Breakout the highest-value comparison. At resolution:

1. Reconcile venue fill, fees, funding, slippage, stop/exit identity, and final
   net PnL.
2. Compare the actual SOL exit with all three already-predeclared profit-lock
   paths without selecting a new threshold after seeing the result.
3. Append a new strategy research-journal revision only if resolved economic
   evidence changes a decision; do not create a duplicate revision for another
   zero-fill prefix.
4. At a flat and order-free boundary, load the verified telemetry correction
   and revalidate the profile identity, pre-start backup, route count, and TUI
   projection before treating the new process as accepted.

This assessment would be falsified by a stale execution heartbeat, a backend
exit, any faulted asset, a duplicate owner, a missing or mismatched protective
stop, a positive independent blocker path that clears the predeclared cost
screen in a later window, or an actual SOL exit that materially changes the
profit-lock comparison.

## Confidence

- High confidence in the process identity, complete route coverage, ledger
  arithmetic, and protection facts at the recorded timestamps.
- High confidence that this prefix contains zero post-rearm fills.
- Medium confidence that no entry relaxation is warranted; the forward window
  is short and most longer horizons remain right-censored.
- Low confidence in portfolio profitability. Two resolved compatible-history
  trades and three open lifecycles cannot establish a repeatable edge.
