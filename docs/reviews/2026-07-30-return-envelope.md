# Hypervelocity return envelope — 2026-07-30

## 1. Problem restatement

The working objective is now $15,000 starting capital and $15,000 net annual
profit. The purpose of this review is to distinguish an evidence-supported
planning range from an upside target. It does not convert historical replay
into a guaranteed income claim.

Success for the research phase means identifying a return objective consistent
with venue-matched evidence while reporting loss tails, uncertainty, and the
additional forward observations required before live capital.

## 2. Known facts and assumptions

- The strongest current short candidate uses source-authoritative completed-5m
  `TREND_DOWN` onsets, a 12-bps minimum completed-bar range, 35% isolated
  margin, 30x leverage, an 8% gross-margin target, and a 24-hour maximum hold.
- The older production-matcher block spans approximately 264 calendar days,
  starts at $15,000, and ends at $39,946.62: +$24,946.62, PF 1.817, and
  -34.22% maximum marked drawdown.
- The following April 18-28 block starts at $15,000 and ends at $16,103.05:
  +$1,103.05 from four targets, with -13.25% maximum marked drawdown.
- The recent April 28-July 28 exact maker replay starts at $15,000 and ends at
  $9,586.10: -$5,413.90, PF 0.558, two liquidations, and -60.74% drawdown.
- The recent shared short-plus-long challenger ends at $10,315.81. Its long arm
  has only five independent fills and remains annotation-only.

## 3. Return linkage

Because each artifact restarts at $15,000, the blocks cannot be added in
dollars. A transparent approximation links their observed equity multipliers:

`$15,000 × (39,946.62 / 15,000) × (16,103.05 / 15,000) × recent_multiplier`

| Recent arm | Approx. ending equity | Approx. annual profit | Return |
|---|---:|---:|---:|
| Short only | $27,406.14 | $12,406.14 | +82.71% |
| Short plus sparse long | $29,492.33 | $14,492.33 | +96.62% |

The short-only approximation is $2,593.86 below the $15,000 objective. The
shared approximation is $507.67 below it, but the long evidence is too sparse
to treat that difference as repeatable.

The older short block's realized 90-day slices returned approximately +64.7%,
+11.9%, and +44.4% on their carried starting equity. The recent 91-day block
returned -36.1%. This dispersion is direct evidence that daily or monthly
income will be irregular and that a one-year headline can hide severe interim
losses.

## 4. Uncertainties, risks, and failure modes

- This is a linked approximation, not one continuously replayed year. Public
  queue capacity can make position size and fill completion nonlinear as
  carried equity changes.
- The 12-bps short threshold was selected on development evidence.
- The older production replay crosses missing archive periods only while flat;
  the recent archive has empty-book hours but no active gap overlap.
- The long challenger has five fills, so its apparent contribution has high
  sampling uncertainty.
- Historical private queue cancellations and future regime distribution are
  unknown.
- A -34% to -61% drawdown is operationally and psychologically material even
  if the final year is profitable.

These limitations prevent estimating a reliable probability of reaching the
target. I do not have verified information that $15,000 annual profit will
repeat. Validation requires an unchanged forward shadow sample and, ideally,
one exact continuously carried year under a single execution implementation.

## 5. Evidence-supported range

| Objective | Current assessment | Reason |
|---|---|---|
| $10k-$15k annual profit | plausible working range | brackets the linked short result and sparse-long upside |
| $15k annual profit | reasonable research target | close to observed linked upper case, not yet forecastable |
| $20k-$25k | upside scenario | reached in the strongest selected block, not the linked year |
| $30k | aggressive stretch | requires materially better forward tail behavior |
| $40k or more | unsupported for planning | exceeds the present linked and independent evidence |

Confidence is medium that $10k-$15k is the most defensible current research
range, but low that any point in that range will be realized forward. A clean
forward PF at or below one, another clustered-liquidation quarter, or worse
queue conversion would lower the range. Twenty to thirty unchanged forward
trades with PF above one, controlled liquidation frequency, and accounting
parity would increase confidence.

## 6. Recommendation and trade-offs

Keep $15,000 profit as the objective, not a promise. Promote only the frozen
35%/30x source-follow short to no-submit shadow when the existing backend is
flat and the user authorizes the cutover. Keep the sparse long and ML model as
paired observers until their independent samples are adequate.

| Option | Benefit | Main risk | Decision |
|---|---|---|---|
| Plan around $10k-$15k | Grounded in current linked evidence | still high uncertainty | recommended range |
| Force $15k with more risk | May close the observed gap | amplifies already severe loss tail | reject |
| Add sparse long now | Recent linked result nearly reaches target | five fills only | observe, do not promote |
| Continue unchanged shadow | Produces forward falsification evidence | takes calendar time | required next step |

## 7. Validation checkpoints

1. Confirm backend/TUI identity and start the source-authoritative 35% shadow
   only from a flat lifecycle.
2. Preserve every entry, fill, fee, funding settlement, partial liquidation,
   maximum-hold exit, and excluded source/canonical disagreement.
3. Review after 20 completed trades; treat 30 as a stronger first estimate.
4. Compare uniform 35% against the paired weak/choppy scaler and sparse long
   without giving either execution authority.
5. Lower the planning range if PF is at or below one or liquidation/drawdown
   exceeds the historical envelope. Consider live canary capital only after
   accounting parity and the unchanged forward rule survive.
