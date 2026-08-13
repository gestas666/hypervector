# Hypervelocity Compression Release Transition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether one completed 5m transition interval after BBWP compression release reduces false trend entries while retaining later entries in the same regime.

**Architecture:** Starting from hard BBWP25 plus the 1m recovery-6 annotation, track causal bars since the latest hard 5m compression state. For ages 1–5, expose a report-only `TRANSITION`, clear structural/entry direction, and then restore the unchanged underlying classifier output from age 6 onward. Replay the exact candidate with regime-reset re-entry, 300-second cooldown, and the unchanged 8% target.

**Tech Stack:** Python 3.12, pandas, pytest, existing serial portfolio and checksum-verified public-trade-through maker replay.

---

## Frozen Contract

- Base: `5m_bbwp_hard_range_25_recovery_6_cooldown_300s`.
- Exactly five 1m decision rows after a hard 5m BBWP range release are
  `TRANSITION`; entry becomes eligible on age 6 if the base decision remains
  directional.
- A window with no previously observed hard compression is not blocked.
- This modifies research decisions only. Runtime classifier/config and TUI do
  not change.
- No confirmation grid is allowed in this trial family.
- Open positions are unaffected and continue TP-only hold-through-RANGE.

Motivation is provisional: resolved liquidation rates were 16/181 (8.84%) at
release ages 0–4, 2/37 (5.41%) at ages 5–9, and 19/161 (11.80%) at 30+. The
test delays signals rather than statically dropping those historical rows, so
path-dependent replay is required.

### Task 1: Causal transition annotation

**Files:**
- Modify: `src/hypervector/research/hypervelocity_bbwp_precedence.py`
- Test: `tests/test_hypervelocity_bbwp_precedence.py`

1. Write a failing prefix-invariance test with compression, five release bars,
   and a later eligible trend.
2. Implement explicit positive integer validation and causal release age.
3. Preserve the input frame; annotate age/wait and change only waiting rows.
4. Verify canonical base values return unchanged after the wait.
5. Run focused tests and lint.

### Task 2: Reproducible serial/event command

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`

1. Add `--event-release-confirmation-bars` with no default behavior change.
2. Apply it after hard range and recovery delay.
3. Add the candidate to serial screening with original-log alignment.
4. Run the single value `5` in serial and full venue replay.

### Task 3: Interpret path evidence

1. Compare targets, full/partial liquidations, fills, final equity, drawdown,
   cadence, and original-log alignment with the base.
2. Reject if the delayed path substitutes equally bad later entries, reduces
   targets without reducing liquidations, or worsens source alignment without
   geometric improvement.
3. A favorable result remains report-only and requires fresh shadow evidence.

Confidence is low-to-medium. The transition has a causal state-machine
rationale, but age-bucket counts are small and were inspected on the same
window. Unchanged or worse event equity/drawdown falsifies it.

## Measured Result

The serial screen and complete checksum-verified public-trade-through replay
both falsified the five-bar release confirmation:

- Serial control: 488 completed trades, 450 targets, 38 liquidations,
  $444,855.97 final marked equity, and 17/35 exact original-entry direction
  matches.
- Serial release-confirmation candidate: 489 completed trades, 440 targets,
  49 liquidations, $2,034.55 final marked equity, and 16/35 exact matches.
- Event control: 407 fills, 368 targets, 39 liquidations, 24 partial
  liquidations, $4,123.47 final equity, and -94.38% maximum drawdown.
- Event release-confirmation candidate: 438 fills, 388 targets, 50
  liquidations, 4 partial liquidations, $78.45 final equity, and -99.96%
  maximum drawdown.

Only 163 resolved signal/direction identities were common to both event paths;
their outcomes did not change (147 targets remained targets and 16
liquidations remained liquidations). The delayed state machine removed 244
resolved control entries and substituted 275 different resolved entries. The
substituted path contained 34 liquidations versus 23 among the displaced
control entries. This is path substitution, not confirmation of safer entries.

The artifact is
`data/logs/research/hypervelocity_release_confirm5_20260727.json`. It verifies
all 2,160 archive bundles and retains all submissions, fills, expirations,
cancellations, partial liquidations, and resolved outcomes.

## Decision

Do not promote or extend the release-confirmation delay. The unchanged 8%
target, allocation/leverage, runtime classifier, and metalabel observe policy
remain in force. A later fresh shadow window in which delayed releases
consistently avoid rather than substitute liquidations would update this
conclusion.
