# V94 review, fixes, and big-swing research (2026-09-26/27)

Operator ask (2026-09-26): review V94 for bugs, faulty logic and whether it is
aggressive bankroll building; fix issues; propose high-value changes; test
longer timeframes for big swing trades (perps or spot) and additional assets.
"Scraping pennies just doesn't work for me."

Method: three multi-agent passes with adversarial verification.
- V94 review: 7 reviewers, 35 findings, each checked by 1–2 verifiers (17 confirmed,
  3 disputed, 15 refuted), plus a synthesis and a completeness critic.
- Swing research, round 1: 3 data agents and 6 tracks, each replicated and trap-audited.
- Swing research, round 2: 3 tracks the round-1 critic said the question implies,
  each replicated and trap-audited.

All three passes ran with pre-registered bars.

Evidence (untracked): `data/logs/research/v94_review_swing_20260927/`. That directory holds
the syntheses, critics, per-finding verdicts, PREREG files, code and outputs.

## 0. Incident: reboot left the book dark for 38 min (2026-09-26)

- **22:47Z:** the operator restarted the Mac from the Apple menu.
- **22:49:37Z:** the supervisor received SIGTERM and latched a hold. The backend did
  not exit within the 30 s grace (`operator_stop_grace_expired`). After boot the
  supervisor logged `give_up` and exited 0 silently. launchd did not relaunch it.
- **During the gap:** the xyz:BRENTOIL long (5.79 @ 99.536) was protected only by its
  venue stop (97.823).
- **23:19:51Z:** re-armed on operator approval. The held journal was archived to
  `data/backups/bidirectional_cohort/reboot_hold_20260926T2249Z/` and the supervise
  agent was kickstarted.
- **After re-arm:**
  - First heartbeat about 6.5 min later.
  - Fingerprint `930117e9…` and source identity `db40d937…` unchanged.
  - Run `bidirectional-live-1790464795401`.
  - Brent was re-adopted on its original stop oid.
- **01:00:21Z:** Brent exited on its 24 h timer at 99.331, for −$1.19 before funding.
  The book was flat at $4,817.19.

## 1. V94 verdict

**No capital-safety bug.**
- Sizing reproduces the journaled `entry_stop_risk_sizing` exactly.
- The floor raise is correct: direction, +0.5R vs +25 bps, 5 significant figures,
  idempotency, the stop-fill race and recovery.
- Stops were resting on 100% of reconciliations while a position was open.
- The ledger matches venue fills 6/6.
- The strong-short rule matches its pre-registration.
- There is no look-ahead.
- Research and live parity: 0 mismatches in 2,857 signals.

**Confirmed defects (ranked):**

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Any SIGTERM (including a host restart) latches a durable hold; the post-boot supervisor gives up silently | High (uptime) | Fixed on branch (opt-in resume) |
| 2 | Size ladder has no statistical power: P(advance) 6% at zero edge and 18% at +0.34R; step-down fires 64–98% within 150 closes | Medium (logic) | Power tool built; re-registration needs operator sign-off before the 30th close (about Oct 9–20) |
| 3 | macOS auto-install still on (`AutomaticallyInstallMacOSUpdates=1`, `CriticalUpdateInstall=1`) | Medium | Operator (sudo) |
| 4 | Backend cannot honour SIGTERM within 30 s on a dead network. A longer grace cannot fix it: the host caps ExitTimeOut at 60 s | Medium | Fixed on branch |
| 5 | Venue max-leverage check is exact equality on all 8 markets, including watch-only ones. Any venue change refuses every start | Low (latent) | Fixed on branch |
| 6 | Checkpoint agent writes 0.27–0.67 TB/day and holds the `market.duckdb` lock about 15% of the time | Low | Fixed on branch |
| 7 | Cockpit STOP/LOCK ignores acknowledged stop raises | Low (display) | Fixed on branch |
| 8 | 30 s entry-deadline headroom is thin: worst case 27.7 s. The TOML cannot move it; `hourly_price_contract` pins 30 s | Low | Headroom now reported by the ladder tool |
| 9 | 429s: the backend itself uses about 640 of 1,200 weight/min, and research fetchers share the egress | Low | Operational rule: no research Hyperliquid pulls at :58–:03 |
| 10 | HANDOFF said the supervise plist has ExitTimeOut 180. Installed plists have 60 | Doc | Erratum below |

**Refuted (do not re-raise):**
- Floor-raise quote timing.
- "Longer holds lose" as first claimed. It was unresolved then; round 2 later settled it.
- The friction model overstating stops. It is a deliberate worst-case bound.
- v2 going blind on thin HIP-3.
- Removing the BTC sweep or the ETH route. Their replays are positive, and demoting
  ETH without its side override breaks the loader.
- Moving BTC/ETH budget to Donchian. There is no shared budget, so it frees $0.
- 1% or more risk per trade. That is over-Kelly and fails the 3%/25% book check.

## 2. Economics: why it feels like scraping pennies

| Metric | Value |
|---|---|
| Account since 2026-08-01 (venue fills) | −$372.21 on 169 closes (t = −1.78); ex-top-3 −$522.82 |
| Trades above $1.5K notional | n = 29, −$394.89 (106% of the loss) |
| Donchian on V94's strong-short identity | n = 14, mean R +0.161 (t = 0.38) |
| V94 time-weighted at-stop risk | 0.27% of equity; realized stop-outs $6.7–10.6 |
| Dollars per R, rung 0 / rung 1 | $12.95 / $22.2 |
| V94 uptime | 98.2% heartbeat-fresh (99.7% excluding the reboot) |

Small wins are what the arithmetic of a zero-measured-edge mechanism produces at
defensible size. Larger size would not change the expectancy. Size placed ahead of
evidence is what lost money here.

## 3. Big swing trades, perps vs spot, more assets

**Round 1 (multi-year Binance 2018–2026 including dead coins, Yahoo underlyings, venue census):**
- **Daily Donchian 20/10 on a broad liquid crypto basket** is the only family with
  multi-year evidence, and it is a mania bet:
  - 2021 alone is 41% of its R.
  - The 2024+ holdout t is 0.45–1.7.
  - On a point-in-time universe the holdout median is about 29%/yr with ZEC and about
    0%/yr without it, with a −56% drawdown.
  - It never beat BTC buy-and-hold or BTC above its 200-day SMA since 2024.
  - Full-period equity depends on same-day slot order, ranging $42K–$168K.
- **Rejected:**
  - 4 h on any universe (fails ex-top-3 at adverse cost and under stop stress).
  - Weekly TSMOM and cross-sectional rotation.
  - MA trend (the lifecycle ex-top-3 gives −81% drawdown).
  - Every HIP-3 swing cell: random entries reproduce 53–82% of the P&L, so it is beta
    on a survivor list.
- **Shorts** are a hedge, never an edge.
- **Perps vs spot:**
  - A swing sleeve uses perps at 2–3x isolated, with the liquidation price at least
    2.5x the stop distance away. Daily 2×ATR stops are 691–1,474 bps, inside 8x
    liquidation.
  - Spot only for a BTC core position.
  - Hyperliquid funding ran about 2x Binance on the overlap.
- **Assets:**
  - Add nothing to the hourly routes (breadth was already refuted).
  - Crypto perps are about one bet (mean ρ 0.57, N_EW 1.7).
  - GOLD, SILVER, COPPER, NATGAS, AAPL, MSFT and META are diversifiers with no
    evidence of their own.
  - SMSN and SKHX duplicate SNDK, and CL duplicates BRENTOIL.

**Round 2 (the three directly implied tests; each verdict upheld by both verifiers):**
- **Let hourly trades run past 24 h: no.**
  - On 2020–26 SOL/BTC/ETH with the v2 overlay: 48 h −$154, uncapped −$168, and
    extend-after-+2R −$30 versus the 24 h cap. SOL 120 h is −$368.
  - This is a null, not a refutation: the uncapped 95% CI is [−$848, +$510].
  - The cap pays by freeing the slot for fresh breakouts.
- **Daily-trend side filter: no.** SMA50 passes nominally but removes losers no better
  than random (holdout p 0.1–0.2). It is worth about $140/yr at live size and lost
  $472 in 2026. The strong-short rule is confirmed as the real short-side fix.
- **2–3x trend-filtered leveraged beta: no.**
  - 0 of 96 cells beat 1x BTC spot in 2024+.
  - Funding costs perps about 10 pts/yr versus spot even at 1x.
  - At 3x, 13 of 15 cells liquidated.
- **Research flag:** the v2 floor leg costs money over 2020–26 on majors. Pre-register
  a review of it before changing anything.

**The only positive-expectancy exposure found for 2024–26 is 1x crypto beta
held as spot.** It is beta, not edge.

## 4. Book options (single-author combination of verified streams; not independently replicated)

| Book | CAGR 2024–26 / max DD | CAGR 2020–26 / max DD | P(−50% in 12 m) |
|---|---|---|---|
| V94 only (today) | ≈0% | ≈0% | ≈0 |
| 50% BTC>SMA200 spot + V94 | 13.3% / −17% | 20.2% / −36% | 0.1% |
| 50% BTC>SMA200 + D1 sleeve at 0.5% | 16.9% / −29% | 45.5% / −48% | 0.7% |
| 80% BTC>SMA200 | 19.8% / −26% | 30.4% / −54% | 2.8% |
| 80% BTC>SMA200 + D1 at 0.5% (ceiling) | 22.6% / −36% | 55.6% / −63% | 6.8% |
| 100% BTC buy-and-hold (reference) | 26.7% / −53% | 44.1% / −77% | 27–44% |

The D1 sleeve and any spot sleeve must live on separate sub-accounts:
- Hyperliquid nets one position per coin per account.
- V94's transitions require the whole book to be flat.
- The engine refuses spot.

Still unverified:
- Sub-account eligibility.
- UBTC bridge custody risk.
- How the cohort ledger treats an external transfer. Do the transfer only while flat
  or inside a drain.

## 5. What was built (branch `agent/v95-review-fixes-20260926`, not merged, not deployed)

| Commit | Change | Live identity |
|---|---|---|
| f205493 | Supervisor: boot-session-stamped holds; **opt-in** resume after a host restart (plist env `HYPERVECTOR_SUPERVISOR_RESUME_AFTER_HOST_RESTART=1`; signal-class hold within 180 s of the previous boot's recorded shutdown, no STOP file, no live backend, enough disk); held-at-start alert instead of a silent exit; `scripts/cohort_resume_after_reboot.py` (dry run by default); informational alert debounce | scripts only |
| a35f399 | Backend stops within seconds (interruptible wait; stop-aware public candle reads with (5, 10) s timeouts; order and stop placement never interrupted). Venue max leverage refuses only below the requested leverage, wired through the start probe, envelope and adapter. Live-mode `stop_file` assertion. Stronger pre-arm gate. | yes |
| 9ea45bd | Cockpit follows acknowledged stop raises | TUI binary |
| dc53598 | Checkpoint: 2 GiB in-memory snapshot budget; research import gated on new fills or maximum age; no retry on deterministic errors | yes (`src/hypervector/research`) |
| 24bdd90 | `scripts/ladder_power_table.py`, ladder-tool headroom and stop-model sections, `scripts/strong_short_skip_audit.py` | scripts only |

**Validation:**
- Full non-network suite in the worktree: 10,729 passed and 277 failed. The same 277
  fail on pristine `5d78929` in a checkout without the untracked `data/` fixtures.
  No new failures.
- `cargo test -p hypervector-tui`: 681 passed. The 1 failure also fails on baseline.
- ruff check is clean.

A follow-up commit on the same branch also passes the requested leverage through the
unsigned read-only preflight and the retired-asset check. Without it, a venue
maximum-leverage change would block the V94→V95 transition preflight.

**Deploy note:** the start gate compares only the profile fingerprint. **Do not
merge this branch into the live checkout before the V95 transition**, or any V94
relaunch would run the new code without an approval.

**V95 package (on the branch, pending operator approval):**
- **Profile:** `configs/multi_asset_growth_first_5000_review_fixes_v95.toml`, profile id
  `multi_asset_growth_first_5000_review_fixes_v95`, fingerprint
  `dd779cce74568e4ba6963d1a19810a7fbcaa7f4279e40f45be83f12286339420`.
- **Content:** V94 values unchanged for SOL, SNDK, BRENTOIL and TSLA Donchian, the BTC
  sweep and ETH range-onset. HYPE and xyz:SPCX are removed from assets and providers;
  they had no executable scope, so there are no retirements.
- **Book check:** 1.66% at-stop and 10.89% margin at $4,810.
- **Approval:** `docs/live-approvals/v94-to-v95-review-fixes-20260927-v1.json` is
  `pending_operator_approval` and refuses until the operator's words are recorded. It
  cites only frozen evidence (never HANDOFF.md, which the armed start re-hashes).
- **Rollback:** `configs/v95-to-v94-rollback-20260927-v1.toml` with approval
  `docs/live-approvals/v95-to-v94-rollback-20260927-v1.json`, also pending. Its
  fingerprint is `5fe5a9de…`. It restores V94 profile values; the V95 source keeps
  running.
- **After go-live:** do not edit the V95 TOML, not even a comment, because the rollback
  approval pins its sha256.
- **Deploy steps:**
  1. Record approval.
  2. Merge the branch.
  3. Drain V94 to flat.
  4. Run the unsigned preflight.
  5. Rebuild the release cockpit binary.
  6. Install the supervise plist, with the auto-resume env var only if the operator
     opts in.
  7. Archive the journal.
  8. Bootstrap checkpoint, then supervise.
  9. Verify fingerprint, identity, heartbeat, scopes and cockpit.

**Observe-only daily-swing shadow runner:** `scripts/d1_shadow_runner.py`, with a plist
example that is not installed.
- **Hard limits:**
  - Constructs no execution client and reads no secrets.
  - Its HTTP guard allows only HTTPS GETs to data-api.binance.vision, with no redirects
    and no netrc.
  - Makes about 25 requests a day and never calls Hyperliquid.
- **Records** the pre-registered D1 20/10 sleeve's hypothetical entries, stops, exits
  and marks, plus the BTC-vs-SMA200 switch state.
- **Before installing:**
  - The operator places a census CSV at `data/research/d1_shadow/census_perps.csv`,
    refreshed within 7 days before each month.
  - Pre-register the rule choices listed in the runner's docstring.
- **Limits of what it proves:** forward data validates execution parity, not edge. A
  t of 2 needs about 3 years of trades.

## 6. Decisions for the operator

1. **Host:**
   - `sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false`.
   - Decide `CriticalUpdateInstall`.
   - Consider a UPS.
   - Planned restarts: `sudo fdesetup authrestart` still stops at the login window.
2. **V95 go-live:**
   - Content: the fixes plus the removal of the HYPE and SPCX assets.
   - Opt in to auto-resume after a host restart? This changes what a signal stop
     means; the durable stop becomes the STOP file or `launchctl disable`.
3. **Ladder re-registration** before the 30th V94 Donchian close. Proposed rule: looks
   at 30/60/90 on cumulative mean R > 0 and ex-top-3 in R ≥ 0; step down at cumulative
   t ≤ −1 at 50/100/150, or −12%. The alternative is the conservative t ≥ 1.6.
4. **Aggression:**
   - Rung 1 on the hourly book now is a labelled zero-Kelly bet: about 1.7x $/R, and
     P(DD ≥ 12% in 90 d) of 42–65%.
   - The honest growth lever is capital allocation to spot BTC beta with an SMA200
     switch (0%, 50% or 80% of the book).
   - Optionally add the D1 mania option at 0.5% after 4–8 weeks of observe-only
     shadow parity. Never 2%.
5. **Kill or drawdown rules for any new sleeve** must be declared explicitly, because
   the charter forbids implicit gates.
6. **Hourly routes:** accept "no change". Keep the 24 h cap and the strong-short rule,
   with no side filter.

## 7. HANDOFF errata

- The supervise plist `ExitTimeOut` is **60** (the host caps it), not 180. The child
  grace is 30 s. A host restart latches the hold through signal-stop semantics.
- The pre-authored V94→V93 rollback re-arms HYPE at $2,500/10x, band20 SPCX and weak
  shorts (2.38% / 17.14%). V95's own rollback target is V94, which is narrow.
- If a start is refused for a venue leverage mismatch under V94, recover with a
  source-only patch, never a TOML edit: an open position deadlocks the flat-boundary
  archive. V95 removes this failure mode.
- `v94-weak-short-rescore-20260924-v1.json` is sha-pinned in the V93→V94 approval. Put
  errata in new files, never in that file. Live ATR history after a restart is about
  83 h (the 5,000-candle cap), with a startup-bar ATR error of at most 1.8% and 0
  strong/weak flips.
