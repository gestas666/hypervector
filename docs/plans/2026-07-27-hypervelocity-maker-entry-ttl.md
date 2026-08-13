# Hypervelocity Maker Entry TTL Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine whether canceling unfilled Hypervelocity maker entries after 60 seconds improves the complete venue replay relative to the current 300-second research control.

**Architecture:** Keep the current research leader (`5m_bbwp_hard_range_25_recovery_6_cooldown_300s`) and every strategy/risk/exit parameter fixed. Expose maker-entry TTL as an explicit report-only script input, verify it is forwarded to `MakerReplayConfig`, then replay the single predeclared 60-second challenger across all checksum-verified Hyperliquid L2/trade bundles.

**Tech Stack:** Python 3.13, argparse, pytest, existing chunked 0xArchive public-trade-through maker replay.

---

## Frozen Evidence and Contract

- Current control: 300-second maker-entry TTL, 528 submissions, 407 fills,
  368 targets, 39 full liquidations, 24 partial liquidations, $4,123.47 final
  equity, and -94.38% maximum drawdown.
- Descriptive only: fills completed within 60 seconds resolved 223 targets and
  21 liquidations (91.39% target rate), versus 90.42% across all 407 fills.
  This is not causal because canceling earlier changes subsequent submissions.
- Test exactly one challenger: 60 seconds. Do not add a post-result TTL grid.
- Preserve the 8% target, 70% isolated allocation, 40x leverage, hard BBWP25,
  1m recovery age 6, 300-second post-exit cooldown, regime-reset re-entry,
  fees, liquidation model, and hold-through-RANGE policy.
- Runtime config and backend behavior remain unchanged. Metalabel remains
  observe-only with filtering/scaling disabled.

### Task 1: Expose and verify the report-only TTL

**Files:**
- Modify: `scripts/hypervelocity_bbwp_precedence.py`
- Create: `tests/test_hypervelocity_bbwp_script.py`

1. Write a failing test that parses `--event-entry-ttl-seconds 60` and proves
   the constructed `MakerReplayConfig.entry_ttl_seconds` is `60.0`.
2. Run the focused test and confirm it fails because the option/helper is
   absent.
3. Add the option with a `300.0` default and a typed helper that constructs the
   replay config. Let `MakerReplayConfig` reject zero, negative, or non-finite
   values.
4. Stamp the effective TTL in candidate identity and report metadata without
   changing the default candidate identity.
5. Run the focused test, existing BBWP tests, and Ruff.

### Task 2: Execute the single full venue replay

**Files:**
- Create: `data/logs/research/hypervelocity_bbwp_recovery6_ttl60_20260727.json`

1. Run hard BBWP25 plus recovery-6 with the explicit 60-second TTL over
   2026-04-28 through 2026-07-27 UTC.
2. Verify all 2,160 bundle checksums before accepting the artifact.
3. Compare submissions, fills, expirations, targets, full/partial
   liquidations, final equity, drawdown, and signal-path overlap with the
   300-second control.

### Task 3: Record the decision

**Files:**
- Modify: `docs/plans/2026-07-27-hypervelocity-maker-entry-ttl.md`

1. Retain the technically valid trial regardless of performance.
2. Reject if it merely substitutes later entries, reduces targets without
   enough liquidation improvement, or ends at or below the control.
3. Treat final equity above $10,000 after modeled costs as the minimum evidence
   of profitability; a smaller loss is not profitable.
4. Do not promote from this explored 90-day window without a fresh shadow
   confirmation.

## Verification

```bash
uv run pytest tests/test_hypervelocity_bbwp_script.py \
  tests/test_hypervelocity_bbwp_precedence.py -q
uv run ruff check scripts/hypervelocity_bbwp_precedence.py \
  tests/test_hypervelocity_bbwp_script.py
```

Confidence is low-to-medium. The actual fill-age slice is directionally
supportive but weak and selection-biased. A full 60-second replay that fails to
reduce liquidation damage or improve final equity falsifies the hypothesis.

## Measured Result

The complete 60-second public-trade-through replay verified all 2,160 archive
bundles and falsified the descriptive fill-age hypothesis:

| Metric | 300s control | 60s challenger |
|---|---:|---:|
| Submissions | 528 | 638 |
| Fills/resolved trades | 407 | 271 |
| Expirations | 114 | 365 |
| Targets | 368 | 240 |
| Full liquidations | 39 | 31 |
| Partial liquidations | 24 | 13 |
| Target rate | 90.42% | 88.56% |
| Final equity | $4,123.47 | $428.84 |
| Maximum drawdown | -94.38% | -98.87% |

The two paths shared only 215 resolved signal/direction identities. The shorter
TTL displaced 192 control outcomes (177 targets and 15 liquidations) and added
56 different outcomes (48 targets and 8 liquidations). It therefore increased
expiration/resubmission churn and selected a worse path rather than cleanly
removing late fills. The artifact is
`data/logs/research/hypervelocity_bbwp_recovery6_ttl60_20260727.json`.

## Decision

Keep the 300-second TTL unchanged. Do not add a TTL grid after observing this
result. Runtime configuration and metalabel observe policy were not modified.
A future venue window with materially different maker wait/outcome behavior
would update this result.
