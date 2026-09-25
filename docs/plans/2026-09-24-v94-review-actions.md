# V94: execute the approved V93 review actions (groups A–D)

Approved by the operator on 2026-09-24 ("yes the private page then plan and
execute options 1 through 4 im approving it now completely"). Source review:
`docs/reviews/2026-09-24-v93-full-review.md`. Operator choices recorded the same
day: phone alerts stay local-only for now (no webhook) and there is no dead-man.
The optional SNDK 0.75% variance sleeve is **not** part of this approval.

Work happens in the worktree `hypervector-v94-review-actions-20260924` on branch
`agent/v94-review-actions-20260924`. The live checkout and the armed V93 process
stay untouched until one drain-to-flat transition installs everything together.

## A. Host and operations (no backend restart)

| Item | Done by | Notes |
|---|---|---|
| A1 alert logic | scripts/ only; reload the watch agent only | New `backend_polls_degraded` problem (2+ consecutive degraded polls while positions are open, or 5 min degraded). New `free_disk_warning` at 14 GiB. Push-channel filter so that only backend-critical problems would page. No webhook is configured (operator choice). |
| A2 auto-update off | Operator runs two `sudo defaults write` commands | Keep downloads and XProtect data on. Patch inside planned drains. |
| A3 disk | Done 2026-09-24 | Deleted the 99 pre-09-09 prestart bundles not referenced by any tracked file (38.9 GiB). Kept the 39 referenced ones and everything from 09-09 on. Free space went from 17 to 47 GiB. |
| A4 reverse approvals | `scripts/cohort_rollback_profile.py` | Generates a rollback profile (target content plus its own approval path), writes the approval, and dry-runs `validate_profile_change_approval` offline. Produce V94→V93 at transition time. Fix HANDOFF's rollback text and the "240 polls ≈ 1 h" claim. |

## B. Config (the V94 profile)

`configs/multi_asset_growth_first_5000_review_actions_v94.toml`, derived from V93:

- SPCX band20 provider: `execution_symbols = []` (watch-only).
- HYPE provider: `execution_symbols = []` (watch-only). Remove its `execution_side_overrides`. Shrink the HYPE asset envelope to margin 0.013 and $500 so a single edit cannot re-arm a half-bankroll slot.
- Donchian provider: `stop_risk_budget = { maximum_loss_fraction_of_equity = 0.006, cost_buffer_bps = 20.0 }`. At $4,831 that is about $29 modeled, which realizes about $25 at measured SNDK friction. It compounds with equity.
- BTC asset `stop_bps` 80 → 60, matching the provider (the value is inert; this removes the confusion).
- The venue stop is raised to the software floor (+0.5R) on v2 providers (C2).
- `[runtime] transition_approval` points to `docs/live-approvals/v93-to-v94-review-actions-20260924-v1.json`.

## C. Code (one source transition, fully tested)

1. `StopRiskBudget.maximum_loss_fraction_of_equity`, evaluated against the account value used for entry sizing. It fails closed on a non-finite or non-positive value. A legacy payload that lacks it stays byte-identical, so the V93 fingerprint is unchanged.
2. Venue stop raise to `max(entry ± 25 bps, entry ± 0.5R)` when the v2 floor arms. It is opt-in per provider, so the default preserves V93. Emit a journaled, surfaced warning when the bounded raise attempts run out.
3. Reject unknown keys in the top-level, runtime, asset, provider and execution tables, with an error naming the key.
4. Restart hardening:
   - Express the degraded-blindness bound in wall-clock time.
   - A venue-metadata mismatch becomes a start refusal (exit 2 with a clear reason), not a crash loop.
   - Do not write a prestart bundle, and do not charge the restart budget, while the venue is unreachable.
   - Make safe replay and bundle speedups, proven equivalent by tests.
   - Ledger rotation is designed but deferred unless it is trivially safe.
5. Weak-short rule. It ships only if the pre-registered re-score below passes.

## Pre-registered bar: weak Donchian short breakdowns (written before the re-score)

Rule under test: skip a Donchian 20/10 **short** entry when
`(prior 20-bar low − signal close) / ATR20 < 1.0`, with ATR20 exactly as the
provider computes it at the signal. The threshold is fixed at 1.0 ATR (V92's
prior hypothesis) and is not tuned. Longs are unchanged.

Harness: the frozen matched-entry screens (recent 8-asset, one-year 4-crypto)
re-simulated with the **v2 exit overlay** and **V93 sizing** (stop-risk budget
applied), at **measured and adverse** costs. That gives 4 cells.

Pass requires all of:

1. Net delta (rule minus baseline) > 0 in all 4 cells.
2. The delta after excluding the 3 largest avoided losses is ≥ 0 in at least 3 of 4 cells.
3. On V93's live Donchian symbols (SOL, SNDK, BRENTOIL, TSLA), recent window: the aggregate delta is ≥ 0 at both costs.
4. At least 30 shorts are actually removed in each window (trigger count reported).

Reported but not gating: per-symbol deltas, per-time-block signs, winners
removed, and the delta at V94 sizing (fraction 0.006).

If any item fails, the rule is not shipped and the result is recorded as a failed
hypothesis. If it passes, it ships as a new provider identity
(`hourly_donchian_20_10_atr20_strong_short_v1`) at mechanism level on all
Donchian symbols, never SNDK-only.

## D. Size ladder (pre-registered; no size change today)

Written in full in `docs/plans/2026-09-24-v94-size-ladder.md`.

- **Rung 0** is V94.
- **Rung 1** extends the calibrated 0.006 equity-fraction budget to all four Donchian routes, raising margin fraction and caps so the budget binds. That is about 0.5% of equity realized at the stop. Never size by 1/stop.
- **Advance** after the next 30 closed Donchian lifecycles since V94 start show mean R > 0 and ex-top-3 net ≥ 0 at measured cost, with timer exits capped at the configured hold (outage holds capped).
- **Step down** to rung 0 on −12% from the rung high, or mean R < 0 over any 50 trades.
- A book-level config check in `scripts/cohort_runtime_validation_check.py`: total at-stop risk ≤ 3% and margin ≤ 25% of equity across executable routes. It is a config validation, not a trade gate.
- `scripts/cohort_ladder_evidence.py` (read-only) reports:
  - the advance and step-down statistics;
  - breakout extension on every live Donchian short;
  - the floor-armed 24h-timer counterfactual;
  - 240- and 1,440-minute post-exit marks;
  - time-scaled buy-and-hold.

## Transition

1. Build and full verification: Python non-network suite, Rust suite, ruff, offline runtime validation of V94, and an adversarial review of the diff.
2. Write and bind the V93→V94 approval. Activate the V93 transition drain through the operator command inbox. New entries are withheld; open positions exit on their own rules.
3. Wait for flat.
4. Archive the drain and verify flat and order-free with the unsigned preflight.
5. Deploy onto `main` and install the plists.
6. Start through the supervisor and verify fingerprint, identity, heartbeat, scopes and cockpit.
7. Pre-author the V94→V93 rollback.
