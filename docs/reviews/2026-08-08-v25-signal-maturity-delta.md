# V25 signal-maturity prefix delta acceptance

**Observed:** 2026-08-08 13:48 EDT  
**Run:** `bidirectional-live-1786182011216`  
**Profile:** `multi_asset_bidirectional_complete_portfolio_canary_v25`

## 1. Problem restatement

The existing immutable prefix delta proved resolved trade, open-lifecycle, and
technical changes, but it did not show what strategy signals matured between
prefixes. The missing output prevented direct review of captured opportunities,
blocked opportunities, and whether repeated observations represented distinct
market paths.

Success required a report-only, same-run extension that attributes causal
provider and exact one-blocker changes while separating raw overlapping counts
from independent/non-overlapping evidence. It could not alter live execution.

## 2. Known facts and assumptions

- Prefixes span 2026-08-08 17:07:51.789291 UTC through
  17:32:31.496931 UTC: 24.66 minutes and 187 new ledger rows.
- Run, profile, and fingerprint match exactly.
- No fill, close, fee, funding, or resolved PnL changed.
- Four open lifecycles remained matched. Their mark movement is provisional.
- Ten additional pressure-metric nulls accumulated under the already-known
  technical-gap identity. The active process still contains the older clock
  implementation, so this window does not test the staged repair.
- Provider forward paths are no-order diagnostics. They do not include capital
  contention, execution, fees, funding, liquidation, or realized PnL.

## 3. Implemented measurement

`cohort-live-audit-delta` now adds `signal_outcome_maturity` with:

- total, directional, and eligible evaluation deltas;
- explicit added/removed provider identities;
- changed provider-symbol mappings only;
- 5/15/30/60-minute resolved, non-overlapping, and censored deltas;
- raw cost-clearing close, MFE, reversal, robust-MFE, and failure changes;
- the same measures over independent opportunity capture;
- exact one-blocker near-miss attribution; and
- refusal when cumulative evaluation counts move backward.

The new logic is isolated in
`src/hypervector/research/cohort_live_audit_signal_delta.py`; both production
modules remain below 500 lines. The command remains immutable, report-only,
and has `execution_authority=none`.

## 4. Measured result

| Measure | Delta | Interpretation |
|---|---:|---|
| Provider evaluations | `+254` | New causal setup observations |
| Directional evaluations | `+246` | Direction was available |
| Eligible evaluations | `0` | No new executable provider signal |
| Closed trades | `0` | No new resolved trade evidence |
| Metric-value gaps | `+10` | Known old-process defect accumulated |
| Matched open lifecycles | `4` | Lifecycle continuity preserved |

For `hype_breakout_onset_bidirectional_v1|HYPE`, the exact
`5m_not_breakout` blocker added 25 observations and five non-overlapping
resolved five-minute paths. Only one independent path cleared estimated cost
on close, MFE, and robust MFE. The same underlying HYPE move also appears in
other provider mappings, so it cannot be pooled as multiple independent bets.

This is a useful lead, not sufficient evidence to remove the blocker. Revised
economic confidence remains low.

## 5. Validation

- Required red-green tests observed:
  - missing signal-maturity output failed before implementation;
  - missing independent evidence failed before implementation; and
  - backward cumulative evaluation counts were accepted before the strict
    monotonicity correction.
- Focused delta and CLI suite: `22 passed`.
- Full non-network Python suite: `4110 passed, 4 deselected`.
- Ruff check and format: pass.
- Production file sizes: 418 and 211 lines.
- `git diff --check`: pass.
- Immutable delta SHA-256:
  `9ea4e5c0e2f5e389b0df4bb2584dea56b4e477a5dd28d397895635c0e4f7a252`.
- Journal revision 3:
  `d2ff7bb4f35eefc81b9aeb95f856a26647affec7e1150bcfd913a9b85bd2f4d2`.
  Current revision evidence is 11/11 matching. Historical revisions remain
  append-only and honestly report seven changed mutable source references;
  none are missing.

At 17:47:31 UTC, launchd still reported PID `37897`, run count one, and no
exit. The checkpoint was `running_consistent` with zero faults. BTC, SOL, GOLD,
and SPCX remained open and protected by the same venue order identities. No
live process, route, order, position, stop, target, size, or policy changed.

## 6. Risks, falsifiers, and recommendation

Confidence is high that the measurement separates raw and independent path
counts and preserves execution isolation. Confidence is low that the observed
HYPE blocker result represents repeatable edge because it contains only one
new independent cost-clearing path.

The method is falsified by accepting identity mismatch, backward cumulative
evidence, overwrite, arithmetic disagreement, changed/missing current evidence,
cross-provider double counting, or any execution side effect. The economic
conclusion changes with materially more independent after-cost paths, newly
resolved venue lifecycles, or corrected execution evidence.

| Option | Benefit | Failure mode | Decision |
|---|---|---|---|
| Retain v25 and accumulate independent blocker paths | Preserves live truth | Requires more elapsed market paths | Selected |
| Remove `5m_not_breakout` now | Increases HYPE frequency | One path is likely noise; ignores execution | Rejected |
| Pool raw provider observations | Produces larger apparent sample | Double counts correlated minutes and strategies | Rejected |
| Restart to load staged telemetry repair | Tests future pressure values | Mutates management of four open positions | Deferred to flat boundary |

The next useful comparison is after a venue close or additional independent
HYPE blocker paths. The approved successor remains pending separate explicit
authorization at a verified flat and order-free boundary.
