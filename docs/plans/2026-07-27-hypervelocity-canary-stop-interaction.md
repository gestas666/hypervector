# Hypervelocity Canary Stop Interaction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether either previously declared liquidation-proximity emergency stop turns the planned $120 Hypervelocity canary path profitable without unacceptable stop churn.

**Architecture:** Reuse the existing optional stateful maker-replay stop implementation and the frozen $120 hard-BBWP25/recovery-6 candidate. Replay exactly the already declared 75% and 90% fractions of entry-to-liquidation distance across the complete checksum-verified archive; run source-window comparisons only for a full-window survivor.

**Tech Stack:** Python 3.13, existing chunked 0xArchive public-trade-through maker replay, immutable JSON research artifacts.

---

## Frozen Contract and Evidence

- $120 TP-only control: 447 fills, 406 targets, 41 full liquidations, no
  partial liquidations, $115.40 final equity (-3.83%), and -97.52% maximum
  drawdown.
- Stop definitions were declared before this capacity result: 75% and 90% of
  the directional distance from entry to the modeled isolated-liquidation
  boundary. They are frozen at entry and execute at adverse BBO with taker fee.
- The same stops were unprofitable at $10,000, where partial liquidation changes
  the loss path. This trial tests the distinct below-$100,000-notional full-
  liquidation regime, not a new threshold grid.
- Preserve hard 5m BBWP25, 1m recovery age 6, 300-second entry TTL/cooldown,
  regime-reset re-entry, 70% isolated allocation, 40x leverage, and 8% target.
- Open positions still hold through RANGE unless the explicit emergency stop
  price is crossed.
- Runtime config, shadow capital, live arming, and ML observe policy cannot
  change from this study.

### Task 1: Run both predeclared full-window interactions

**Files:**
- Create: `data/logs/research/hypervelocity_equity120_stop75_20260727.json`
- Create: `data/logs/research/hypervelocity_equity120_stop90_20260727.json`

1. Run both candidates from April 28 through July 27 using all 2,160 verified
   bundle pairs.
2. Retain every submission, fill, expiry, target, stop, liquidation, final
   equity, and maximum drawdown.
3. Compare returns as percentages of $120, not raw dollars.

### Task 2: Decide whether either survives

1. A survivor must finish above $120 after fees and improve maximum drawdown
   versus the TP-only $120 control.
2. Report target-to-stop substitution and path overlap; zero liquidation
   labels alone is not success.
3. If neither survives, do not add another stop fraction.
4. If one survives, replay only that exact candidate on the source window and
   compare source timing/cadence before any recommendation.

### Task 3: Preserve the runtime decision

1. Append measured results and limitations here.
2. Keep `stop_policy = "none_observed"` in the faithful runtime unless a
   separate promotion decision is supported by full and forward evidence.
3. Keep metalabel observe-only with filtering/scaling disabled.

## Validation

Each artifact must report `checksums_verified=true`, `bundle_count=2160`,
`event_initial_equity=120`, and the exact stop fraction in its candidate ID.
The faithful TOML checksum must remain unchanged.

Confidence is medium that the event replay measures the relative stop
interaction under its stated BBO proxy and low that it will generalize to venue
mark-price liquidation. A non-positive final return or worse drawdown falsifies
the candidate.

## Measured Result

- Both checksum-verified full-window runs completed across all 2,160 bundles.
- The TP-only $120 control finished at $115.40 with -97.52% maximum drawdown,
  406 targets, and 41 full liquidations.
- The 75% stop finished at $15.13 with -99.44% maximum drawdown, 413 targets,
  65 stops, and no liquidation labels. Of 487 signals shared with control, it
  changed 40 control liquidations into stops but also stopped 11 trades that
  reached target under control. Earlier exits created 64 new signals and
  removed 30 control signals, so this was not a label-only substitution.
- The 90% stop finished at $53.86 with -99.08% maximum drawdown, 409 targets,
  49 stops, and no liquidation labels. Of 497 shared signals, it changed 40
  control liquidations into stops but also stopped three control targets. It
  created 29 new signals and removed 20 control signals.
- Neither candidate met either survival requirement: both ended below $120 and
  both had worse drawdown than the TP-only control. Therefore no stop candidate
  advances to the source-window replay, and no additional stop fraction is
  authorized by this experiment.

## Decision

Keep `stop_policy = "none_observed"`. The result does not establish that a live
protective stop has no safety value; it falsifies these two fixed liquidation-
distance stops as profitable repairs under the current replay and re-entry
contract. A materially different result under authentic mark-price and depth-
aware stop execution would update this conclusion.
