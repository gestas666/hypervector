# V25 live-prefix delta monitoring acceptance

**Observed:** 2026-08-08 13:29 EDT  
**Runtime:** `multi_asset_bidirectional_complete_portfolio_canary_v25`  
**Run:** `bidirectional-live-1786182011216`

## 1. Problem restatement

Continuous live review needs to distinguish three different classes of change:
resolved trade economics, provisional movement in open positions, and technical
telemetry coverage. The acceptance criterion is an immutable report that fails
on incomparable prefixes and has no execution authority.

## 2. Known facts and assumptions

- The compared inputs are immutable audits from the same run, profile, and
  profile fingerprint. Their last observations are 43.22 minutes apart.
- The later prefix contains 327 additional ledger rows and no additional
  close, fill, fee, funding, or resolved PnL event.
- Four open lifecycles match across both prefixes. Their marks and ignored-exit
  paths remain unresolved and can reverse before venue close.
- The known `provider_metric_telemetry_missing` identity did not change, while
  its null-value count increased by 20. The active process loaded implementation
  bundle `072653...`, before the staged HIP-3 pressure-clock repair.
- The compatible closed evidence remains three trades, two wins and one loss,
  after-cost net `+$0.035067`, profit factor `1.05338`. This sample is not enough
  to establish repeatable economic edge.

## 3. Implemented evidence boundary

`cohort-live-audit-delta` now publishes an immutable same-run comparison that:

- rejects run, profile, or fingerprint mismatch;
- rejects backward ledger rows or observation time;
- separates resolved, provisional-open, and technical-coverage changes;
- reports an open lifecycle disappearing without a matching close;
- refuses an existing output rather than overwriting it; and
- converts expected operator errors into exit code 2 with one actionable
  message and no traceback.

The command is report-only. It cannot start, stop, place, cancel, resize, or
close an order and cannot change strategy authority.

## 4. Measured delta

| Evidence class | Result | Interpretation |
|---|---:|---|
| Closed trades | `+0` | No new resolved economic evidence |
| Fills | `+0` | No new execution observation |
| Net PnL | `$0.00` | No resolved economic change |
| Metric-value gaps | `+20` | Existing technical defect accumulated |
| Right-censored observations | `-15` | Paths matured; not evidence of profit |
| Matched open lifecycles | `4` | Continuity preserved |
| Missing open lifecycle without close | `0` | No lifecycle-integrity break observed |

Provisional mark changes were BTC `-$0.004869`, SOL `-$0.020954`, GOLD
`-$0.043418`, and SPCX `+$0.032128`. These values are explicitly not resolved
trade outcomes.

## 5. Runtime validation

At 2026-08-08 17:27:55 UTC, the checkpoint reported:

- `running_consistent`, zero faults, and matching runtime/config fingerprint
  `ec7715f...7ecc`;
- BTC long `0.00038`, protected by target/stop orders
  `512826144316/512826131342`;
- SOL long `1.0`, protected by stop `512630736897`;
- GOLD long `0.0172`, protected by stop `512544517709`; and
- SPCX long `0.56`, protected by stop `512769547957`.

Launchd reported PID `37897`, run count one, and no exit. No live process,
route, position, order, stop, target, allocation, or exit policy was mutated.

## 6. Verification

- Full Python non-network suite: `4108 passed, 4 deselected`.
- Focused delta/CLI tests: 23 passed during red-green implementation.
- Ruff check and Ruff format check: pass on all touched Python files.
- `git diff --check`: pass.
- CLI status and help expose `cohort-live-audit-delta`.
- Journal revision 2 is current:
  `99d5729b49323a1e8b6238bd1ed1c2fbb8985c5bbcec76fabfd37c7a87c909b2`.
  Its eight evidence references match. The append-only two-revision history
  reports 15 matching, two changed, and zero missing references; both changed
  references belong to revision 1 and document the later error-boundary update.

Rust/TUI sources were not changed by this monitoring addition and the Rust
suite was not rerun for this acceptance. The complete Rust/TUI suite passed in
the immediately preceding v25/v29 contract acceptance.

## 7. Risks, falsifiers, and recommendation

Confidence is high that the delta tool preserves identity, arithmetic, and
execution isolation, based on unit/CLI tests and the real immutable artifacts.
Economic confidence remains low because only three compatible closes exist.

The monitoring assessment is falsified by accepting mismatched identities,
backward progress, overwritten evidence, an unexplained lifecycle disappearance,
arithmetic disagreement, current-revision evidence drift, or any execution side
effect. The economic decision changes with a newly resolved lifecycle,
materially corrected after-cost evidence, or a new technical-gap identity.

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| Retain v25 and continue immutable deltas | Preserves live evidence and protection | More time before economic inference | Selected |
| Restart to load staged repair now | Tests future pressure telemetry sooner | Mutates management of four open positions | Rejected at this boundary |
| Change exit/route from open marks | Reacts immediately | Treats provisional paths as resolved edge | Rejected |
| Do nothing beyond raw logs | No added code | Makes future comparisons non-reproducible | Rejected |

Next validation is another same-run prefix after a close or material technical
change. A successor load remains pending a separately authorized, verified
flat and order-free boundary.
