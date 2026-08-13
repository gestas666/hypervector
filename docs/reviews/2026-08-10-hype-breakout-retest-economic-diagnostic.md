# HYPE breakout-retest economic diagnostic

## Decision

Do not route the breakout-retest challenger in v39 or v40. Preserve the policy
implementation for future research, but keep execution authority absent.

Confidence is medium for rejection of the tested formulation. The replay used
the same development market and v35 80 bps / 8h-to-24h exit contract as the
compression study, but its lifecycle rows were not published as an immutable
sidecar. The figures below are therefore diagnostic evidence, not a promotion
artifact.

## Development results after modeled friction

| Formulation | Signals | Trades | Wins/Losses | Net return | PF | Positive folds |
|---|---:|---:|---:|---:|---:|---:|
| All confirmed retests | 537 | 441 | 97/344 | -5,390.23 bps | 0.825 | 1/5 |
| Continuation confirmations only | 303 | 245 | not retained | -4,350.47 bps | 0.754 | 0/5 |
| Failed-breakout fades only | 234 | 216 | not retained | -1,752.37 bps | 0.880 | 2/5 |

The least-bad arm was the failed-breakout fade, but it remained negative in
aggregate and in most chronological folds. Confirmation reduced frequency
without overcoming the underlying loss distribution.

## Inputs and contract

- Development bars: `data/cache/HYPE_1m_365d.parquet`
- Funding: Hyperliquid hourly funding events used by the HYPE exit replay
- Protective stop: 80 bps
- Soft maximum hold: 480 minutes
- Extension: while regime-supported
- Hard maximum hold: 1,440 minutes
- Fees/slippage: the HYPE exit replay's venue-friction contract
- Execution authority: none

## Failure modes and update condition

This diagnostic can be wrong if the earlier entry builder, boundary logic, or
friction wiring differed from the current provider contract. A materially
different result would falsify the rejection only if a fresh immutable rerun:

1. publishes every entry and exit lifecycle with source hashes;
2. preserves the 20-bar breakout boundary and three-bar causal confirmation;
3. uses actual funding plus the v35 fee/slippage/stop/hold contract;
4. reports five chronological folds and largest-winner removal; and
5. produces positive, fold-stable net economics without selecting on holdout.

Until then, the simpler compression-filtered immediate breakout has stronger
development and later-window evidence and remains the staged HYPE challenger.
