# Lean successor portfolio comparison

Date: 2026-08-09 EDT  
Status: inactive next-canary candidate  
Execution authority: none  
Automatic promotion: false

## Systems decision

Prepare a new source-bound successor generation around three exact executable
routes:

1. bidirectional SOL Range Onset;
2. bidirectional ETH Range Onset with the explicit
   `dual_mtf_not_opposed` context policy; and
3. bidirectional SPCX Swing/HA.

Do not revive v29 unchanged. Do not include ETH pullback in the lean candidate,
because dual-MTF Range Onset beat it in every measured nominal and stress
window. Do not change the running v25 process, its open positions, venue stops,
orders, sizing, or exit policies from this report.

Confidence is medium for choosing dual-MTF ETH over ETH pullback because the
comparison uses the same shared account, time windows, source outcomes, and
fixed route controls. Confidence is low-medium that the complete portfolio has
a durable future edge because the common windows remain winner-concentrated and
all evidence is opened and selection-contaminated.

## Verifiable contract

- Initial equity: `$500`.
- Maximum positions: three, one per asset.
- SOL: `$75` notional, `5x` isolated.
- ETH: `$25` notional, `5x` isolated.
- SPCX: `$75` notional, `5x` isolated.
- Long and short outcomes retained for every route.
- Crypto nominal friction: `13 bps` round trip.
- Crypto stress friction: `20 bps` round trip.
- SPCX: immutable venue-specific nominal and stress lifecycle rows.
- No parameter sweep, static side gate, leverage change, sealed holdout access,
  execution authority, or automatic promotion.

## Shared-account results

### Development common window

| Variant | Stress trades | Stress net | Stress PF | Max DD |
|---|---:|---:|---:|---:|
| SOL control | 2 | +$3.74 | 7.46 | 0.11% |
| SOL + SPCX | 39 | +$14.27 | 1.68 | 1.04% |
| SOL + SPCX + ETH pullback | 64 | +$12.56 | 1.51 | 1.24% |
| SOL + SPCX + ETH dual-MTF | 42 | +$14.06 | 1.66 | 1.08% |

ETH dual-MTF added `-$0.22` to SOL plus SPCX under development stress. ETH
pullback added `-$1.71`. The dual-MTF portfolio beat the pullback portfolio by
`+$1.49` while using 22 fewer trades.

### Opened final common window

| Variant | Stress trades | Stress net | Stress PF | Max DD |
|---|---:|---:|---:|---:|
| SOL control | 4 | +$0.38 | 1.23 | 0.22% |
| SOL + SPCX | 26 | +$1.55 | 1.13 | 1.80% |
| SOL + SPCX + ETH pullback | 39 | +$1.71 | 1.12 | 1.75% |
| SOL + SPCX + ETH dual-MTF | 30 | +$3.22 | 1.26 | 1.88% |

ETH dual-MTF added `+$1.67` under final stress. ETH pullback added only
`+$0.16`. Dual-MTF beat pullback by `+$1.51` with nine fewer trades.

### Full opened descriptive history

| Variant | Stress trades | Stress net | Stress PF | Max DD | Net excluding largest winner |
|---|---:|---:|---:|---:|---:|
| SOL control | 42 | +$40.56 | 3.47 | 0.75% | +$29.93 |
| SOL + SPCX | 101 | +$52.44 | 2.10 | 2.30% | +$37.11 |
| SOL + SPCX + ETH pullback | 439 | +$51.33 | 1.53 | 2.54% | +$36.01 |
| SOL + SPCX + ETH dual-MTF | 171 | +$58.62 | 2.02 | 2.35% | +$43.29 |

The lean dual-MTF candidate beat the pullback portfolio by `+$7.29` under
stress while taking 268 fewer trades. The result is not simply the largest
winner in the full history: after removing that lifecycle, stressed net remains
`+$43.29`.

## Route and direction attribution

Full opened nominal attribution for the selected candidate:

| Route | Trades | Net | PF |
|---|---:|---:|---:|
| SOL Range Onset | 42 | +$42.71 | 3.87 |
| ETH dual-MTF Range Onset | 70 | +$7.46 | 1.83 |
| SPCX Swing/HA | 57 | +$15.58 | 1.56 |

Both directions are positive in the full opened source union, but the common
windows show side rotation:

- SPCX development long was positive while short was negative; final long was
  negative while short was positive.
- ETH final long was positive while short was negative.
- SOL final long was negative while short was positive.

This contradicts adding a static long-only or short-only gate. The missing SOL
short in the development common window is reported rather than silently filled
or used to abort the experiment.

## Concentration and failure modes

The most important contradictory evidence is concentration. Under stress:

- development common dual-MTF net is `+$14.06`, but `-$1.12` after removing
  its largest winner;
- opened final common dual-MTF net is `+$3.22`, but `-$0.28` after removing
  its largest winner;
- full opened dual-MTF net remains `+$43.29` after removing its largest winner.

Therefore the evidence supports a bounded live-research candidate, not a claim
of established edge. A future live run could fail through route-side rotation,
SPCX winner concentration, IOC slippage, stop gaps, funding, maximum-hold path
risk, or source/runtime identity drift. Realized-equity drawdown also understates
concurrent intratrade mark-to-market drawdown.

## Recommendation and trade-offs

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| Continue broad v25 indefinitely | More live events | Retains many historically negative exact routes | Keep only until current protected lifecycles resolve |
| Revive v29 | Existing files and positive aggregate | Weak routes, stale implementation identity, concentration | Reject |
| Lean SOL + ETH dual-MTF + SPCX | Best measured stress aggregate, fewer trades than pullback, both sides | Common-window winner concentration | Prepare inactive next canary |
| Lean SOL + ETH pullback + SPCX | Higher frequency | Weaker in every window and negative full-history stress marginal contribution | Reject for this successor |
| Increase leverage now | Larger nominal PnL | Magnifies unresolved route and execution uncertainty | Do not combine with route change |

The candidate should preserve current 5x leverage, fixed notional caps, one
position per asset, venue-native stops, and provider-exit `ignore` semantics.
Transition requires a verified flat-and-order-free boundary, a current source
backup, profile and implementation fingerprints, passing contract tests,
rollback instructions, and renewed explicit live-risk authorization.

## Validation and falsifiers

The decision is invalidated by changed artifact bytes, incorrect source
friction, missing route outcomes, a timestamp or side mismatch, failure to
reconcile accepted PnL to shared equity, or any live mutation caused by the
report-only command. The candidate assessment should be revised if exact
prospective venue outcomes are negative after costs on represented sides, if
provider/runtime parity fails, or if repeated live outcomes remain dependent on
one large winner.

Focused validation completed:

- seven lean-successor tests passed;
- Ruff lint and formatting passed;
- all new source files remain below 500 lines and all functions below 50 lines;
- immutable artifact:
  `data/logs/research/lean_successor_portfolio_comparison_20260809T161609Z.json`;
- artifact SHA-256:
  `a507537566cacb1a256e61f5f70abc8a5f0212514787e93367a8ef5727127bee`;
- artifact size: `1,421,828` bytes;
- execution authority: none.
