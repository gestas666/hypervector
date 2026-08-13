# Cross-Asset Impulse Propagation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether a completed BTC or ETH price impulse adds delayed,
tradable continuation information for ETH, SOL, or HYPE without reusing the
rejected residual-convergence contract.

**Architecture:** Build a causal one-minute event score from a leader's
standardized five-minute impulse and a follower's standardized catch-up gap.
Compare the primary signal with fixed, non-selectable ablation and placebo
controls in three exact chronological development blocks before constructing a
strategy replay. Retain every primary and control cell, source-quality mask,
fold, cadence diagnostic, and null result in immutable report-only evidence;
later historical segments are family-level confirmation only because they have
already been inspected by other project research.

**Tech Stack:** Python 3.13, pandas, NumPy, immutable JSON/Parquet evidence,
pytest, Ruff, existing Hyperliquid-native one-minute cache.

---

## Frozen research contract

### Window, source, and decision clock

- Development scoring window: `2025-07-28T00:00:00Z` through
  `2026-01-28T00:00:00Z`, half-open.
- Source warmup starts at `2025-07-20T23:55:00Z`. This provides five source
  minutes needed by the first five-minute return plus 10,080 complete prior
  one-minute return observations. Warmup rows may build features but may never
  create an event or label.
- Pre-outcome source amendment (`2026-08-02`): the four 365-day development
  caches begin at the development boundary and therefore cannot supply that
  warmup. Exact immutable 0xArchive candle bundles were acquired for
  `[2025-07-20T23:55:00Z, 2025-07-28T00:00:00Z)`. Those bundles exposed a
  common candle-dataset outage on `2025-07-27`; a bounded public-trade tape for
  `[2025-07-27T00:00:00Z, 2025-07-27T12:03:00Z)` reconstructs only missing
  candle minutes. Surviving native candles retain precedence, reconstructed
  public-trade candles count as authentic Hyperliquid rows, and complete-tape
  minutes with neither source remain `hl_gap_fill` and fail the source-quality
  mask. No return window, threshold, fold, control, cost, or eligibility rule
  changed, and no signal outcome was computed before this amendment.
- Directed leader/follower pairs, in deterministic order: BTC→ETH, BTC→SOL,
  BTC→HYPE, ETH→SOL, ETH→HYPE. A follower never predicts a declared
  leader in this version.
- A source candle timestamp is its one-minute bar-open time `t`. Its close is
  admissible only at `t + 1 minute`. The state row is attributed to
  `bar_open_at=t`, while both `decision_time_utc` and the primary next-open
  entry anchor equal `t + 1 minute`.
- The primary label enters at the follower candle open stamped
  `decision_time_utc` and exits at the follower open stamped
  `entry_time_utc + horizon`, for horizons of 5, 15, and 30 minutes. This is an
  ideal boundary-price association, not a claim that a live order fills with
  zero latency.
- A fixed delayed-anchor diagnostic enters one additional minute later and
  exits 5, 15, or 30 minutes after that delayed entry. It is reported for every
  primary cell and participates in candidate eligibility as specified below.

### Causal feature and source-quality mask

- For symbol `S`, the completed five-minute log return at source row `t` is
  `r_S(t) = log(close_S(t) / close_S(t - 5 minutes))`.
- Volatility is each symbol's own sample standard deviation of the 10,080
  five-minute returns strictly before `t`: `sigma_S(t) = std(r_S[t-10080:t])`
  with `ddof=1`. The current return cannot enter its own scale. The rolling
  window is a fixed seven-day calendar window, not an expanding two-to-seven
  day warmup.
- A five-minute return is source-valid only when every one-minute source row
  from `t - 5 minutes` through `t`, inclusive, is authentic `source="hl"`.
  Invalid returns become missing rather than zero.
- The fixed seven-day volatility window may contain labeled continuity gaps,
  but it must contain at least 99% source-valid returns: at least 9,980 of
  10,080. Volatility is calculated only over those valid returns, and the exact
  valid count is persisted. A current leader or follower return that is not
  source-valid cannot create an event.
- Both primary and delayed labels require authentic follower `hl` rows for the
  entry, exit, and every intervening minute. A path touching `hl_gap_fill` is
  retained with status `technical_gap` and cannot enter metrics or selection.
  A path extending beyond its fold or the development window is retained as
  `fold_boundary_purged` or `right_censored`, respectively.
- The loader must reject a missing timestamp, duplicate timestamp, unexpected
  source, non-finite price, or non-positive price. It must not silently treat an
  `hl_gap_fill` row as authentic. The artifact records authentic/gap row counts
  by symbol and excluded event/label counts by reason. It also binds the
  development cache, warmup candle, repair trade tape, and both immutable
  manifests by path, byte count, and SHA-256 for every symbol.
- Standardized returns are `z_L(t) = r_L(t) / sigma_L(t)` and
  `z_F(t) = r_F(t) / sigma_F(t)`. Let `d(t) = sign(z_L(t))`. The frozen catch-up
  gap is `gap(t) = abs(z_L(t)) - d(t) * z_F(t)`. The primary state qualifies
  only when `abs(z_L(t)) >= 2.5` and `gap(t) >= 0.75`; its proposed follower
  direction is long for `d=+1` and short for `d=-1`.

### Event sampling, folds, and overlap

- Sample only a false-to-true primary onset. After an accepted event, another
  onset for the same directed pair is accepted when its decision time is at
  least 30 minutes later. Equality is allowed: the earlier 30-minute label exit
  and later entry may share one boundary timestamp but their return intervals
  do not overlap. Tests must cover 29, 30, and 31-minute separations.
- Exact fold boundaries are:
  1. `fold_1`: `[2025-07-28T00:00:00Z, 2025-09-28T00:00:00Z)`
  2. `fold_2`: `[2025-09-28T00:00:00Z, 2025-11-28T00:00:00Z)`
  3. `fold_3`: `[2025-11-28T00:00:00Z, 2026-01-28T00:00:00Z)`
- Features are built once over warmup plus development and are never reset at a
  fold boundary. Each label belongs to the fold containing its decision, but
  it is resolved only when its complete entry-to-exit interval is strictly
  inside that fold. Events whose exit is at or beyond the fold end are boundary
  purged from that horizon.
- Thirty-minute cooldown prevents overlap only within one directed pair.
  Persist same-leader-time clusters, same-follower/time collisions,
  cross-pair overlaps, cluster-size distribution, and uniqueness-weighted
  effective count. Do not describe nominal row count as independent sample
  size.

### Fixed non-selectable controls

- `leader_only_ablation`: require `abs(z_L) >= 2.5`, use the leader direction,
  and omit the catch-up threshold. This tests whether the gap adds information.
- `follower_only_momentum`: require `abs(z_F) >= 2.5` and use the follower's own
  direction, independent of the leader. This is a generic continuation
  baseline; duplicated follower baselines across leader names remain explicit.
- `lagged_leader_placebo`: replace the contemporaneous leader z-score with its
  value exactly 1,440 minutes earlier, then apply the same catch-up formula and
  thresholds. This preserves a causal past-leader marginal distribution while
  testing temporal specificity.
- Controls use identical source masks, onset/cooldown semantics, anchors,
  horizons, folds, and reporting. They are never eligible for replay and may
  not change the primary thresholds. The artifact separates 15 selectable
  primary cells from 45 non-selectable control cells.

### Association, cost feasibility, direction robustness, and cadence

- Output labels are leader-direction signed follower simple returns in basis
  points. Report gross association, `gross - 13 bps` nominal proxy, and
  `gross - 20 bps` stress proxy. None is a fill, fee, funding, leverage, PnL, or
  profit-factor claim.
- Every pair/horizon/fold reports resolved and excluded counts; long and short
  counts; mean, median, trimmed mean, standard deviation, 10th/25th/75th/90th
  percentiles; fraction above 0/13/20/26 bps; base and delayed anchors; and each
  control result. Development-wide pooling is reporting-only and cannot replace
  a failed fold.
- The trimmed mean is deterministic: sort finite resolved returns and remove
  `floor(0.10 * n)` observations from each tail. Percentiles use NumPy's
  `method="linear"`; sample standard deviation uses `ddof=1` and is unavailable
  for fewer than two observations.
- Per primary pair/horizon cell, cadence uses resolved primary events only and
  de-duplicates by `(directed_pair, decision_time_utc)`. Report events per 184
  calendar days, active UTC-day fraction, median/p90/maximum interarrival,
  percentage of rolling three-day UTC windows containing an event, and longest
  eventless interval. Also report portfolio-level `(follower,
  decision_time_utc)` uniqueness without using it to rescue a sparse cell.
- Rolling three-day coverage uses UTC-midnight windows `[day, day+3d)` for each
  start day whose full window lies inside development. Longest eventless time
  includes the development-start-to-first-event and last-event-to-development-
  end edges. For simultaneous `(follower, decision_time_utc)` clusters, each
  nominal event receives weight `1 / cluster_size`; effective count is the sum
  of those weights and therefore equals the number of unique follower-time
  clusters. This is a dependence diagnostic, not an eligibility substitute.
- A primary pair/horizon is eligible for replay only when all conditions hold:
  1. At least 30 resolved primary events in each fold.
  2. At least 10 resolved long and 10 resolved short events in each fold.
  3. Base-anchor mean gross return is greater than 20 bps in every fold, its
     median fold mean is at least 26 bps, and each direction's development-wide
     mean is greater than 13 bps.
  4. Delayed-anchor mean gross return is greater than 13 bps in every fold and
     its median fold mean is at least 20 bps.
  5. Primary mean gross return exceeds the corresponding leader-only ablation
     and lagged-leader placebo mean in every fold. Follower-only momentum is a
     required diagnostic but not a dominance gate because it samples a
     different event population.
  6. The cell averages at least one resolved event per calendar day and its
     p90 interarrival is no more than three days.
- These are development-selection criteria, not runtime strategy gates. They
  intentionally require both directions and positive room beyond nominal cost;
  they do not establish executable edge.

### Search accounting, deterministic selection, and authority

- The selectable searched set is one primary signal definition × five directed
  pairs × three horizons = 15 cells. The 45 control cells are reported
  separately and cannot win selection. No threshold, warmup, fold, lag, cost,
  direction, or cadence surface is allowed in this family.
- The artifact must disclose that the same cross-asset development window was
  previously used by the 90-cell residual exit surface. Therefore 15 is the
  within-family selectable count, not the project's cumulative research count.
  Persist references to the prior residual artifact and the known cumulative
  count; do not compute or claim a Deflated Sharpe Ratio from an incomplete
  project-wide trial ledger.
- If multiple cells pass, select exactly one by descending lexicographic order:
  worst-fold delayed gross mean, worst-fold base gross mean, median-fold base
  gross mean, events per calendar day; then ascending declared pair order and
  ascending horizon. Control outcomes cannot alter this ranking beyond the
  fixed dominance requirement above.
- Validation and pseudo-holdout have been inspected by other strategy families.
  They may later challenge one frozen impulse candidate, but must be labeled
  family-level confirmation rather than globally untouched evidence. A fresh
  forward shadow/live-observer window remains the decisive independent test.
- Authority is immutable: `report_only=true`, `execution_authority=none`; no
  wallet, order adapter, live process, TUI route, automatic strategy mutation,
  or execution gate may be introduced by this experiment.

### Task 1: Freeze typed contracts

**Files:**
- Create: `src/hypervector/research/cross_asset_impulse_models.py`
- Test: `tests/test_cross_asset_impulse_models.py`

1. Write failing tests for exact warmup/development/fold bounds, five directed
   pairs, fixed horizons, 13/20-bps references, 1,440-minute placebo lag, full
   seven-day coverage, equality-allowed cooldown, controls, deterministic rank,
   and immutable no-execution authority.
2. Run `uv run pytest tests/test_cross_asset_impulse_models.py -q` and require
   RED for the absent or incomplete contract.
3. Implement typed frozen configuration, source-mask, event, label, fold-result,
   control-result, cadence, cluster, and candidate records with actionable
   validation errors.
4. Re-run the focused test and require PASS.

### Task 2: Construct append-invariant causal events and controls

**Files:**
- Create: `src/hypervector/research/cross_asset_impulse_signal.py`
- Test: `tests/test_cross_asset_impulse_signal.py`

1. Write failing numerical tests for `bar_open_at` versus decision/entry time,
   exact five-minute returns, full prior-only seven-day scales, the explicit
   catch-up equation, both directions, and all three fixed controls.
2. Add failing source-quality tests for authentic rows, current-window gaps,
   the 99% volatility-coverage floor, label-path gaps, right censoring, and fold
   boundary purging.
3. Add failing sampling tests at 29/30/31 minutes, exact primary and delayed
   entry/exit anchors, non-overlapping return intervals, and future-append
   invariance.
4. Run `uv run pytest tests/test_cross_asset_impulse_signal.py -q` and require
   RED.
5. Implement the smallest causal state builder, source mask, event sampler,
   controls, and labeler satisfying the frozen equations and statuses.
6. Re-run the focused test and require PASS.

### Task 3: Build fold-level association, controls, cadence, and selection

**Files:**
- Create: `src/hypervector/research/cross_asset_impulse_screen.py`
- Test: `tests/test_cross_asset_impulse_screen.py`

1. Write failing tests for exact fold boundaries and purges, no cross-fold
   substitution, all 15 primary plus 45 control cells, base/delayed metrics,
   direction robustness, nominal/stress proxies, and zero-event retention.
2. Add failing tests for per-cell cadence, active-day and interarrival metrics,
   same-follower collisions, cluster sizes, uniqueness weights, effective count,
   every eligibility condition, and exact lexicographic tie-breaking.
3. Run `uv run pytest tests/test_cross_asset_impulse_screen.py -q` and require
   RED.
4. Implement complete fold/control summaries and deterministic selection.
   Never emit fill, funding, leverage, liquidation, profit-factor, or PnL fields
   from this association screen.
5. Re-run the focused test and require PASS.

### Task 4: Publish one immutable development artifact

**Files:**
- Create: `scripts/cross_asset_impulse_development.py`
- Test: `tests/test_cross_asset_impulse_development_script.py`
- Reuse or extract from: `src/hypervector/research/cross_asset_residual_data.py`

1. Write failing parser and fixture tests requiring the exact warmup and scoring
   windows, four source hashes, per-symbol authentic/gap counts, fixed contract
   identity, 15/45 cell counts, event sidecar identity, prior residual-artifact
   reference, and fail-on-existing output behavior.
2. Run `uv run pytest tests/test_cross_asset_impulse_development_script.py -q`
   and require RED.
3. Implement a report-only runner using the native multi-asset loader. If the
   residual-specific name becomes misleading, extract a generic loader and keep
   residual callers behavior-identical. Do not load validation or
   pseudo-holdout rows.
4. Re-run all impulse tests, Ruff, formatting, structural limits, and
   `git diff --check`.

### Task 5: Execute once, decide, and preserve the search record

**Files:**
- Create: `data/logs/research/cross_asset_impulse_development_v1.json`
- Create: `data/logs/research/cross_asset_impulse_development_v1.events.parquet`
- Create: `docs/reviews/2026-08-02-cross-asset-impulse-development.md`
- Modify: `HANDOFF.md`

1. Run `uv run python scripts/cross_asset_impulse_development.py` once.
2. Recompute source and event hashes; reconcile every fold, mask, primary,
   control, direction, cadence, cluster, exclusion, and sidecar count.
3. If no exact pair/horizon clears every frozen criterion, reject this contract
   and do not tune thresholds. If one or more clear, freeze the one selected by
   the exact lexicographic rule before loading a later segment.
4. For a survivor, write a separate replay plan with measured fees, stressed
   slippage and latency, funding, liquidation, one-position-per-coin conflicts,
   shared-follower arbitration, portfolio sizing, and forward-observer parity.
5. Record confidence, implementation limitations, contradictory folds, known
   prior search exposure, and a precise falsifier. Keep live execution disarmed
   in either outcome.

## Execution note

The active goal requests continued autonomous progress, while the shared dirty
worktree prevents safely isolating per-task commits. Execute this plan locally
with TDD and verification checkpoints; do not commit unrelated worktree changes
or grant this report-only experiment execution authority.
