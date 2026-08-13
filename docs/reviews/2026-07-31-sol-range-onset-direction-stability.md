# SOL range-onset direction and block-stability audit

Date: 2026-07-31

## 1. Problem restatement

The 60-bps, 0.15x SOL range-onset challenger has positive aggregate historical
economics, but an aggregate result can conceal a profitable side subsidizing a
negative side. This report decomposes the 42 fully resolved trades by direction
and asks whether either side becomes negative when any one clean evidence block
is removed.

The audit is report-only. It does not alter the running SOL observer, shared
portfolio, regime detector, model authority, or BTC source-follow shadow.

## 2. Evidence contract

- Inputs are the 12 non-overlapping clean block artifacts already used in the
  accepted 42-trade capacity result.
- Every input must contain exactly one complete 0.15x exposure, 5x leverage,
  3% isolated-margin, 60-bps-stop trial.
- Execution and model authority must both remain `none`.
- Failed replays, overlapping windows, unexpected trade counts, and
  `end_of_data` exits are rejected. The unresolved July 30 long is therefore
  absent rather than force-closed.
- Each source artifact is identified by byte count and SHA-256 in the output.

## 3. Direction result

| Direction | Trades | W/L | Net PnL | PF | Positive/active blocks | Minimum leave-one-block-out PnL |
|---|---:|---:|---:|---:|---:|---:|
| Long | 19 | 5/14 | +$391.64 | 2.959 | 3/8 | +$126.32 |
| Short | 23 | 7/16 | +$895.06 | 4.580 | 5/9 | +$344.55 |

Both sides remain positive after removing any one of the 12 blocks. The reset-
block trade PnL sums to $1,286.70, while product-of-block equity reproduces the
prior $16,326.30 result from $15,000 exactly. The difference between simple PnL
sum and product equity is expected block compounding, not an accounting
disagreement.

Short profit is less concentrated: its largest winner contributes 28.0% of
gross profit and its top three contribute 67.2%. Long profit is more fragile:
its largest winner contributes 49.2% and its top three contribute 92.3% of
gross profit. Leave-one-block-out positivity does not remove this dependence on
rare trend payoffs.

## 4. Uncertainties and failure modes

- Direction decomposition is diagnostic after strategy selection; it is not an
  independent discovery holdout.
- Only five long and seven short winners exist. Profit factor can change
  materially after a small number of forward trades.
- Five of eight active long blocks and four of nine active short blocks are
  negative. Positive expectancy depends on occasional large 48-hour moves.
- Historical block resets are not a continuously executable annual account.
- Public depth, mark sampling, latency, and provider-gap limitations from the
  parent replay remain in force.

Confidence is medium that both directions contributed positive economics on
the measured clean blocks, and low-to-medium that either side will retain the
same payoff distribution forward. A forward side-specific PF at or below one,
repeated finite-depth failures, or a newly resolved block that makes the
leave-one-block-out result negative would weaken or falsify the corresponding
side.

## 5. Recommendation

Keep both directions in the unchanged no-submit SOL observer at the same frozen
$2,250 notional cap. Do not promote a short-only rule or increase short sizing
from this retrospective decomposition. Preserve side-specific forward metrics
so the next completed trades can update long and short evidence separately.

The simpler alternative is short-only observation. It has stronger historical
PF and lower winner concentration, but it discards a positive long contribution
without independent forward evidence that longs have failed.

## 6. Verification and evidence identity

- Five direction-audit tests passed after test-first implementation.
- The broader focused SOL lifecycle set passed 24 tests.
- Ruff, whitespace, file-size, and function-size checks passed.
- Immutable report:
  `data/logs/research/sol_range_onset_direction_stability_12blocks_42trades_20260731.json`.
- Report SHA-256:
  `48b94f65ce97f52640ffb8d6fe00f81d15cd80d8a6e51b858a31048a1c795a37`.
