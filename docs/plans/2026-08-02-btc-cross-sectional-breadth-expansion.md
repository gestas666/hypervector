# BTC Cross-Sectional Breadth-Expansion Development Plan

**Status:** Frozen before outcome evaluation.

**Goal:** Test whether a fresh expansion in synchronized BTC/ETH/SOL/HYPE
participation predicts economically meaningful 60-minute BTC continuation in
both directions.

**Architecture:** Build point-in-time features from completed native
Hyperliquid 15-minute bars, emit one report-only event at the next one-minute
open, compare a one-minute delayed anchor, and preserve immutable event-level
evidence. The experiment has no order client, portfolio sizing, runtime adapter,
TUI strategy tile, or execution authority.

## Problem and success criteria

Previously tested low-timeframe mechanisms cover flow-exhaustion fades,
pair-residual convergence, leader/follower impulse catch-up, generic BTC L2
expected-return prediction, saved RANGE-fade ML, and single-coin expansion
stacks. None established a cost-qualified, bidirectional candidate. This test
changes the causal variable to simultaneous cross-market participation rather
than tuning any rejected family.

One primary contract qualifies for a separate execution replay only if:

1. Every chronological fold has at least 30 resolved events.
2. Both long and short have at least 10 resolved events in every fold.
3. Cadence is at least one resolved event per calendar day and the p90 event gap
   is no more than 72 hours.
4. Immediate and one-minute-delayed mean gross return both exceed 13 bps in
   every fold.
5. Immediate and delayed pooled medians are positive, and 10% trimmed pooled
   means exceed 13 bps.
6. Long and short pooled gross means each exceed 13 bps.
7. The primary delayed fold mean exceeds the corresponding one-minute-delayed
   mean of both the BTC-only momentum control and 24-hour-lagged breadth
   placebo in every fold.

These are experiment-selection criteria, not live risk gates. Failure remains a
reported result under `SRS_HV1_NO_GATES`.

## Explicit assumptions and known limits

- Source: frozen native Hyperliquid BTC/ETH/SOL/HYPE one-minute cache data plus
  the source-bound warmup repair already validated by the impulse artifact.
- Development scoring window: `2025-07-28T00:00:00Z` through
  `2026-01-28T00:00:00Z`.
- Folds: the same three fixed 61-day chronological folds used by the impulse
  development artifact.
- Price labels are bar-resolution diagnostics, not executable fills.
- Nominal 13 bps and stressed 20 bps round-trip costs remain reference values.
- The broad historical period has prior project exposure. This is development,
  not a globally sealed holdout or promotion result.
- Multiple-testing accounting must include the 105 prior selectable residual
  and impulse cells plus this one selectable primary contract. The two controls
  are nonselectable.

## Frozen feature contract

All features use completed 15-minute bars and information available at the
decision bar close.

1. Resample each symbol's one-minute OHLCV to 15 minutes. A bar is valid only
   when all 15 constituent minutes are valid source rows.
2. Compute each symbol's six-bar log return, representing 90 minutes.
3. Normalize that return by the symbol's trailing 672-bar realized standard
   deviation of 15-minute log returns. The volatility window ends at `t-1`,
   excluding the decision bar. Require at least 666 valid observations inside
   those 672 positions; invalid observations are skipped, never carried into
   returns.
4. Define the direction as the sign of BTC's normalized 90-minute return.
   Zero is not eligible.
5. Breadth is the count of the four normalized returns with the BTC direction.
   Require at least three of four.
6. Cross-sectional dispersion is the population standard deviation of the four
   normalized 90-minute returns.
7. The expansion threshold is the strictly prior 672-bar 75th percentile of
   dispersion, requiring at least 666 valid observations. Require a
   false-to-true cross: current dispersion is above the current strictly-prior
   threshold, while prior dispersion was at or below its own strictly-prior
   threshold.
8. Emit at most one event at a time and apply a 60-minute cooldown from the
   decision timestamp. No same-direction exception exists.

The primary event timestamp, direction, input values, threshold, breadth count,
source validity, and exclusion reason must be stored for every candidate bar.

## Frozen labels and controls

### Primary

- Entry anchor: first valid BTC one-minute open strictly after the completed
  15-minute decision bar.
- Delayed anchor: the following one-minute BTC open.
- Exit anchor: BTC one-minute open 60 minutes after the corresponding entry.
- Return: direction-signed gross basis points from entry to exit.
- Fold-boundary, technical-gap, and right-censored rows are explicit exclusions.

### BTC-only momentum control

Remove all peer breadth and cross-sectional-dispersion inputs. Emit a control
when the absolute BTC normalized 90-minute return freshly crosses above its own
strictly-prior 672-bar 75th percentile. Preserve the primary cooldown, direction,
entry anchors, horizon, folds, and exclusions.

### Lagged-breadth placebo

Keep current BTC inputs but shift the ETH/SOL/HYPE normalized returns and the
resulting peer breadth/dispersion inputs back exactly 96 completed 15-minute
bars (24 hours). Preserve all other logic. The placebo is never selectable.

No alternate return window, volatility lookback, breadth count, percentile,
cooldown, horizon, or direction filter may be evaluated in this artifact.

## Data and causality validation

The loader must fail closed on:

- absent or changed source manifests/hashes;
- non-monotonic or duplicate minutes;
- a missing symbol or unequal selected scoring grid;
- a 15-minute bar containing any invalid source minute;
- a standardization or percentile window touching invalid data;
- a label entry or exit crossing a fold boundary;
- any current-bar observation leaking into a strictly-prior threshold;
- any 24-hour placebo shift that is not exactly 96 valid 15-minute positions.

Fixture tests must perturb the current bar and demonstrate that prior
thresholds do not change. They must also inject gaps at the decision, entry,
delayed-entry, and exit anchors and verify explicit exclusions.

## Evidence schema and reconciliation

Create one immutable JSON report and Parquet event sidecar under
`data/logs/research/` with `report_only=true` and
`execution_authority=none`. Record:

- exact source and selected-frame hashes;
- exact hashes of every output-generating module;
- frozen contract identity and prior trial count;
- per-fold immediate/delayed distribution statistics;
- long/short counts and return distributions;
- primary/control cadence, collision, and exclusion counts;
- event-level decision inputs, anchor prices, returns, and authority;
- sidecar row count, byte count, and SHA-256;
- explicit selected candidate or `null`.

An independent validator must recompute source hashes, feature causality,
candidate masks, cooldown, labels, controls, aggregates, sidecar identity, and
authority. The runner must refuse to overwrite an existing artifact.

## Implementation sequence

1. Add typed contract and event models with unit tests.
2. Add source-bound 15-minute data construction and validity tests.
3. Add strictly-prior normalization, dispersion, breadth, and crossing features
   with leakage tests.
4. Add primary and two control event masks with cooldown and placebo tests.
5. Add immediate/delayed 60-minute labels, chronological folds, exclusions,
   metrics, and eligibility tests.
6. Add immutable artifact publication and independent reconciliation tests.
7. Run the development artifact exactly once.
8. If it fails any criterion, reject without a threshold surface. If it passes
   all criteria, write a separate venue-execution replay plan before any
   runtime, TUI, shadow, or live change.

## Operational follow-up

The already-running disarmed cohort observer continues independently. A future
breadth observer is warranted only after this development contract qualifies.
For any future observer, fewer than three independent onsets over five days
falsifies useful forward cadence, but three events cannot establish edge.

## Pre-outcome execution amendment

The first command attempt wrote no artifact or sidecar. It stopped after signal
construction because the lagged-placebo control emitted zero labels. A
signal-only diagnostic found that the original 672-of-672 minimum required two
consecutive perfect seven-day windows, while the immutable source contains
small explicit weekly archive gaps. Primary dispersion had only 990 finite
rows and the placebo threshold had none. No return, PnL, cell metric, or
selection result was inspected.

Before retrying, `minimum_valid_bars` was frozen at 666 inside each 672-position
window (99.1% coverage). The 672-position lookback, percentile, breadth count,
directions, horizon, cooldown, controls, costs, and economic criteria did not
change. Candidate bars and label anchors touching a gap remain invalid. This
amendment is falsified by a test showing current-bar leakage, admission with
fewer than 666 valid observations, or material sensitivity concentrated around
the omitted archive rows.

## Confidence and falsifier

**Confidence: medium that this is causally distinct and technically testable;
low that it is profitable before measurement.** The simultaneous breadth input
is structurally different from prior fades, pair convergence, leader catch-up,
generic L2 regression, and single-coin TA. Its main failure modes are generic
BTC momentum masquerading as breadth, excessive event dependence, sparse
expansion onsets, and sub-cost returns.

The hypothesis is falsified for this contract if cadence fails, any fold's
one-minute-delayed mean is at or below 13 bps, either direction lacks sample
support or positive economics, or the primary fails to dominate either control.
A later material source/causality defect would invalidate rather than merely
weaken the result.
