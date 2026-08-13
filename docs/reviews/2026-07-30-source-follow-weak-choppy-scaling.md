# Source-follow weak/choppy allocation scaling

Date: 2026-07-30

## Problem and experiment contract

The continuous 30x source-follow lead remained profitable, but twelve full
liquidations and a -51.14% marked drawdown were too severe for a live-capital
claim. Decision-time attribution showed that nine of those twelve
liquidations occurred under the pinned source classifier's explicit
`TD_WEAK_CHOPPY` subtype. That subtype was not a valid entry gate: it also
contained 58 targets and had slightly positive aggregate PnL.

The predeclared challenger therefore retained every minimum-range-12 source
decision and changed only signal-level allocation:

- normal source subtypes: 50% isolated margin at 30x;
- `TD_WEAK_CHOPPY`: 25% isolated margin at 30x;
- target: unchanged 8% gross margin return;
- entry/exit matcher, queue evidence, fees, funding, mark liquidation,
  maximum hold, source timestamps, and one-position policy: unchanged;
- execution authority: none; model authority: observe.

The implementation was introduced test-first. Missing exact source labels
fail rather than reusing a stale subtype, and the default uniform profile
remains unchanged.

## Continuous development comparison

Both paths used the same 285 source decisions, twelve ordered gap-free
Hyperliquid segments, one continuously carried $15,000 portfolio, production
post-only queue matcher, public trade-through fills, official funding, and
authentic mark/oracle liquidation context.

| Metric | Uniform 50% | Weak/choppy 25% | Difference |
|---|---:|---:|---:|
| Selected source signals | 285 | 285 | 0 |
| Completed trades | 114 | 116 | +2 |
| Targets | 100 | 105 | +5 |
| Time exits | 2 | 2 | 0 |
| Full liquidations | 12 | 9 | -3 |
| Partial liquidations | 43 | 26 | -17 |
| Final equity | $36,408.76 | $45,702.95 | +$9,294.19 |
| Profit factor | 1.428 | 2.193 | +0.765 |
| Maximum marked drawdown | -51.14% | -30.79% | +20.35 pp |
| Maker fees | $9,844.58 | $7,511.63 | -$2,332.95 |
| Taker fees | $1,326.85 | $769.21 | -$557.64 |
| Funding cashflow | +$737.16 | +$531.58 | -$205.58 |

All 285 signals remained present: 170 were half-sized and 115 were full-sized.
Both paths ended flat with zero missing or stale oracle settlements.

The scaled path had a higher segment return in only four of twelve blocks.
Its whole-path advantage came from reducing the worst loss clusters rather
than raising ordinary winning-block returns. This concentration lowers the
confidence that the final-equity difference is temporally stable.

## Causal execution mechanism

Three source signals that liquidated in the uniform path reached their target
in the scaled path. Their entry prices and isolated liquidation boundaries
were effectively identical. The smaller target quantity completed on an
earlier favorable public trade sequence; the larger target remained partially
open and later reversed into liquidation.

This is a modeled maker-capacity and queue-completion effect, not a claim that
smaller isolated positions have a wider liquidation price. The public tape
supports the counterfactual, but historical private queue cancellations remain
unobservable and could falsify its live relevance.

## Later April comparison

The April 18-28 block was already observed by earlier strategy research, so it
is a later out-of-sample comparison for this sizing rule but not a pristine
project-wide blind holdout. The minimum-range-12 rule retained nine source
signals and completed four trades in both variants.

| Metric | Uniform 50% | Weak/choppy 25% |
|---|---:|---:|
| Targets / liquidations | 4 / 0 | 4 / 0 |
| Final equity | $16,451.84 | $15,872.60 |
| Maximum marked drawdown | -18.87% | -9.49% |

Scaling reproduced lower drawdown but not higher return. With no losses in the
block, reducing seven of nine signal allocations only reduced profitable
exposure. The sample is four completed trades and cannot establish a stable
risk-adjusted edge.

## Decision, confidence, and falsifiers

The weak/choppy scaler becomes a report-only risk-adjusted challenger; it does
not replace the uniform source-follow shadow candidate and is not installed in
the active backend. The next valid comparison is a dual forward observer on
the same fresh source events, followed by an explicit flat-only shadow choice.
No further multiplier tuning is justified from this development path.

- High confidence in mechanical comparability: signal identities, source
  labels, risk contract, venue evidence, and default behavior are explicit and
  tested.
- Medium confidence that the subtype identifies historical tail exposure: it
  captured nine of twelve development liquidations and scaling reduced both
  full and partial liquidation counts.
- Low confidence that it improves forward return: the later April block made
  less money at half size, only four trades resolved, and private queue rank is
  unknown.

Fresh scaled PF at or below the uniform control, no repeated drawdown benefit,
worse queue conversion, source-label drift, or inability to reproduce target
completion from recorded forward tape would falsify the challenger.

## Immutable evidence

- Development uniform control:
  `db223085f8c0ff747373376b2a3d40869d56a2a1dd7cfa7a9ade426041d436e9`.
- Development scaled challenger:
  `0526e8df8c52666b609a90243c1aad24f2e70eab72bcf21fc17ff54fbbced2fe`.
- April uniform control:
  `5eebf704643d76da7e9cbfe06179eb6914796116c1f90b04cf625b03de6a5fc2`.
- April scaled challenger:
  `74bbdc2c2fa85b3b0bbdc0869e98e4642963f0465685a53eaef0f36b2a8f8221`.
- Pinned current-source labels:
  `de6beef5eed4caf29f595e0c04cb9d26b33b063b05847c7a1b66b0cba3138653`.

The active faithful no-submit backend was not stopped, reset, or changed. At
08:21 UTC it still held the older canonical short, so no cutover was attempted.

## Verification

The exact current Python tree passed 1,459 non-network tests with four
deselected. The Rust/TUI suite passed all 34 integration tests. Focused Ruff,
changed-file whitespace, the 500-line file limit, and the 50-line function
limit also passed. The 31 Python warnings are dependency, deprecation, and
single-class metric warnings; no test failed.
