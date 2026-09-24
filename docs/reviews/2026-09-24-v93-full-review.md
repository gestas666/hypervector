# V93 full review: technical setup, entries, exits and sizing against aggressive bankroll building

Date: 2026-09-24. Scope: the live profile
`configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml` (fingerprint
`33131f18…`, run `bidirectional-live-1790196314874`, LIVE ARMED since
2026-09-23 20:59 UTC). This is a read-only review: it changes no file, no process
and no approval. Every recommendation below needs Albert's explicit decision.

Method: eight independent review dimensions (live architecture, exits, entries,
sizing, evidence audit, realized-performance forensics, config/ops, measured
aggression levers). Each dimension's findings then went to an adversarial
verifier, and the verified set went to a two-judge panel (an aggression advocate
and a ruin skeptic). 102 findings were produced and checked. The numbers below
are the verified or corrected values. The reviewer independently re-checked
these load-bearing claims:

- The alert variables are absent from all three plists.
- macOS auto-install, FileVault and `autorestart=1` are on.
- The default route is `utun4`.
- The 09-24 degraded-poll window is as stated.
- The weak-short split.
- The 09-11 SNDK outage hold.

Scratch work (scripts and intermediate tables) is in the session scratchpad, not
the repo.

## 1. Verdict

**No. V93 is not yet smart, aggressive bankroll building. But the fix is not
"more size".** It is timid where timidity buys nothing, and it spends the risk it
does take in the wrong places. The evidence still cannot carry a large size-up.

- **Timid where aggression is free.**
  - About 94% of equity sits idle as withdrawable collateral.
  - Time-weighted gross exposure is 0.27x equity, with 3.35% posted as margin.
  - Routes that actually fire risk $4–11 per trade (0.1–0.2% of equity).
  - The fixed-dollar $25 budget plus fixed-dollar caps stop size from compounding.
  - Uptime is unprotected, and the repo counts it as its one measured multiplier.
    Nothing alerts off-host, and any reboot ends in a manual-only hold.
- **Risk in the wrong places.**
  - HYPE holds the book's largest slot ($2,495 at 10x, the venue maximum) on a
    route with 0 eligible signals in 1,008 V93 evaluations.
  - SPCX runs band20, the one mechanism this repo found significantly negative.
  - Donchian 20/10 takes weak short breakdowns at full risk. It is the most
    consistently losing entry group measured (t = −5.59 pooled).
  - The $25 budget labelled "per position" changes size on one route only. It cuts
    SNDK, the route where the tail lives, from $1,930 to $1,112.
- **Why not simply size up.**
  - At the mechanism level Kelly is about zero: recent 8-asset +0.049R
    (adverse, t = 0.66) and one-year crypto −0.083R (t = −1.79, day-clustered).
  - Since V89 the live record is 32 closes, −$46.29, PF 0.69.
  - One of the three famous SNDK "24h timer winners" was really a 96.7-hour outage
    hold. A working 24h timer would have closed it at about −9 bps.
  - Every uniform or SNDK-concentrated size-up fails the ex-top-3 test on at least
    one pool.

**The defensible aggressive path, in order:**

1. Protect uptime. This is free and changes nothing in the live identity.
2. Cut the negative-EV and unevidenced legs.
3. Make size compound, and calibrate the budget so the stated risk is actually
   taken.
4. Ship the one entry rule that survives the traps at the mechanism level (skip
   weak shorts).
5. Earn more size through a pre-registered ladder.

Anything beyond that is a variance bet Albert can buy knowingly. It should not be
called smart aggression.

## 2. Live state at review time

| Item | Value |
|---|---|
| Equity | $4,831.43 at 14:53 UTC, against $4,825.33 at V93 start. Intraday peak $4,846.85, trough $4,808.45 (0.79% drawdown). |
| Closed in V93 | 3 closes, all protective stops, about −$13.9 with fees: SPCX long −$5.48 (entered at regime alignment −0.83), TSLA short −$3.89 (stopped in 34 min), TSLA short about −$4.51 (stopped at 13:55, just after the US cash open, having peaked at 0.49997R, 0.002 bps short of v2 activation). |
| Open | SNDK short (budget-sized to $1,112) and BRENTOIL long ($578). |
| Exit policy v2 | Correct on live data: all 7,017 `adaptive_exit_observation` rows replay through `advance_retention_exit` with 0 mismatches. It has not yet acted. The venue break-even modify has never run live. |
| Outage | 10:37:46–11:46:05 UTC on 09-24: 68.3 min of `transport_connection_retry_exhausted` with 3 open positions. No software exit ran. Realized cost $0. |
| Since V89 (09-07) | 32 closes, net −$46.29, 34% wins, PF 0.69, mean −0.14R. Three SNDK timer exits make up 73.5% of gross profit. The bot polled only 46.4% of wall-clock time. |

## 3. Scorecard against aggressive bankroll building

| Area | V93 today | Verdict |
|---|---|---|
| Execution path | Stop resting a median 2.67 s after entry ack (max 6.78 s, n=144). Entry slippage median 0.17 bps; 1 IOC no-fill in 145. HIP-3 fee 0.864 bps. The 15 s poll costs about 1 bps per software exit. | **Supports aggression.** Execution is not the constraint. |
| Leverage / liquidation | Every configured venue max matches the live venue (BTC 40, ETH 25, SOL 20, HYPE 10, TSLA 20, SNDK 10, BRENT 20, SPCX 20). Stops sit 3.1–14.8x inside liquidation. Isolated margin caps a gap on all 8 positions at about 14.5% of equity. | **Sound.** Do not raise leverage (margin is not binding), and do not switch to cross. |
| Exit stack (v2) | Correct, tail-preserving and cheap insurance: about $0.21–0.27 per trade, 50–56% of it from SNDK, roughly neutral on the one-year window. | **Keep frozen.** It is not a growth lever. |
| Sizing | No compounding. The $25 budget binds on SNDK only (60 of 61 historical SNDK entries, 0 of 150 others). HYPE carries $25 of risk on no evidence. | **Aggression wasted and misallocated.** |
| Entries | One mechanism actually fires (D20/10). Three providers are near-dead. SPCX band20 has negative evidence. Weak D20 shorts lose everywhere. | **Risk placed against the evidence.** |
| Uptime / ops | No off-host alert. Reboot leads to a manual hold. The degraded bound is 8.2 h, not the documented 1 h. Restart time grows 0.62 min/day. About 7 GiB of disk above the refusal floor. The rollback fails closed. | **The largest free lever, unprotected.** |

## 4. Where aggression is wasted

1. **Uptime is unprotected** (verified, high).
   - Alerts are local only. `HYPERVECTOR_ALERT_WEBHOOK_URL` and
     `HYPERVECTOR_DEADMAN_URL` are absent from the supervise, watch and checkpoint
     plists, so `build_sinks` (`scripts/cohort_supervisor_alerts.py:171-179`)
     produces only a JSONL log and a macOS banner.
   - A reboot becomes an outage. `AutomaticallyInstallMacOSUpdates=1`,
     `CriticalUpdateInstall=1`, FileVault is on with no auto-login, and
     `pmset autorestart 1`. After any reboot or unclean supervisor exit, the
     restart journal holds (`cohort_supervisor_state.py:79-81,96-98`) until a
     human archives it.
   - Precedents: 68.5 h dark (09-08→09-11) and 95.1 h dark (09-11→09-15), plus
     degraded streaks of 199, 64 and 49 min.
   - The supervisor never reads heartbeat status. On 09-24 the first backend
     problem was raised 18 min into the outage, while a local roster alert with the
     same title had fired earlier.
2. **Size does not compound.**
   - The $25 is a fixed-dollar constant (`cohort_stop_risk_sizing.py:95-97`), not
     the "0.5% of equity" its rationale states.
   - ETH, HYPE and SPCX are capped today. BTC, SNDK, BRENT, SOL and TSLA hit their
     caps at about $6.4–6.7K equity.
   - SNDK is frozen near $1,112 at any equity above about $2.8K.
   - The near-term P&L effect is small (about +1% over 62 days in replay). The
     effect is structural: size does not grow after gains and does not shrink after
     losses.
3. **The budget under-delivers its own stated risk.** For structural stops it
   prices the full 20 bps IOC entry bound, while realized V93 entry slippage was
   −4 to +2 bps. A SNDK stop-out realizes about $21.8, or 87% of the $25.
4. **The $25 budget is not evidence-derived.**
   - It binds only on SNDK. On V93's own screen it costs more in-sample ($198–268)
     than exit v2 adds ($128–132).
   - The V91 −$44.95 loss that prompted it fell inside V90's approved envelope of
     about $48.75.
   - The panel still rejects restoring V90 size (section 7). Calibration, not
     restoration, is the defensible fix.
5. **The 24h timer is pinned** on every hourly route (`hourly_price_contract.py:32-33`).
   - It forces a close and a re-entry at a fresh −1R stop even when a +0.5R floor
     already protects the run.
   - Extend-while-floor-armed adds +$212/+$222 (recent, 8 assets) and +$366/+$379
     (year).
   - On V93's four routed symbols it adds only +$12/+$14, with ex-top-3 of
     −$26/−$24. **Forward-test it; do not deploy it.**
6. **BTC's fixed 60/60 bracket** (target = 1R) makes the v2 floor and the
   break-even raise unreachable. It caps a trade at about $4 gross. The dollar
   impact is low because the route rarely fires.

## 5. Where risk is unfunded or misplaced

1. **HYPE: $2,495 notional at 10x (venue maximum) on no evidence.**
   - Signals: 0 of 1,008 eligible evaluations in V93, 0 of 5,279 in V89, and 4
     intents in its lifetime.
   - Negative in all 9 V90 screen cells.
   - Liquidation sits about 5% away. HYPE had 4 hourly bars beyond that distance in
     63 days, and a 10.7% 15m wick on 08-22.
   - One gap costs the full $250 of isolated margin, 5.2% of equity and about 10x
     its budget.
   - **Fix notional, not leverage.** At the same notional, 5x doubles posted margin
     and the worst-case gap loss ($499).
2. **SPCX on band20.**
   - Mechanism in-sample −$512.85 (n=472, t=−3.07); out of sample −$322.55
     (n=123, 0 of 8 symbols).
   - It was re-armed in V91 as an operator scope choice with no new evidence.
   - Live SPCX: 10 trades, about −$14.2, 8 of them against the regime.
   - 38 of 41 band20 entries with coverage were regime-opposed; 0 of 28 D20 entries
     were.
3. **Weak D20 short breakdowns** (close less than 1 ATR beyond the prior 20-bar low).
   - Pooled: n=929, −$1,870.96, t=−5.59, negative in 26 of 29 symbol-window cells.
   - By screen: recent 146 trades −$386.54 (t=−3.88); one-year crypto 507 trades
     −$994.51 (t=−3.46), a falling market where trend shorts should have worked.
   - At measured cost: −33 bps per trade, t=−3.53.
   - All three V93 D20 shorts were weak (0.02, 0.91 and 0.95 ATR).
4. **The US-equity legs co-move exactly when stops fire.**
   - Off-hours hourly correlation: SNDK–TSLA 0.47, SNDK–SPCX 0.46, TSLA–SPCX 0.45
     (n=579 h), against 0.18–0.27 daily.
   - 7 of 14 since-V89 stops fell between 13:00 and 15:59 UTC. On 09-24 both V93
     US-equity shorts went adverse into the cash open.
   - Small today, but any uniform size-up scales it linearly.
5. **Operational ruin paths** (Section 8).

## 6. Strategy review by route

### Entries

| Route | Evidence | Signal rate | Verdict |
|---|---|---|---|
| D20/10 SNDK | Best live rank. Mechanism t 0.68–0.92; ex-top-3 negative at every size. | 61 in the 62-day screen | **Keep. Calibrate the budget. Drop weak shorts.** It is the tail sleeve but a selected cell (rank anti-predicts, Spearman −0.56). |
| D20/10 SOL | Recent positive; one year −$198.6 adverse, ex-top-3 −$376. | 47 in the 62-day screen (not dead) | **Keep at $500. Do not fund up.** |
| D20/10 BRENT | Modest. Standalone fails ex-top-3 at both costs. Negatively correlated with the equity legs. | Active | **Keep.** |
| D20/10 TSLA | Weakest D20 cell: PF 1.02 over 51 trades; failed its pre-declared bar. 2 of 2 V93 entries hit full stops. | Active | **Keep small. Never fund up.** |
| band20 SPCX | Mechanism retired at p=0.0019. | about 1.3/day | **Retire to observe-only.** |
| HYPE compression | None positive. | 0.16/day lifetime, 0 in V93 | **Observe-only, or $500 cap.** |
| ETH range onset | None. | 0 eligible ever (14,076 evaluations) | **Observe-only (optional; costs about $4 of risk).** |
| BTC sweep 60/60 | Thin. | about 0.15/day, 0 of 17 in V93 | **Keep as a small free option.** |

Other entry conclusions:

- Canonical regime alignment is telemetry only at entry. It is a tie-break between
  providers on the same symbol, and every V93 symbol has one provider.
- Regime filters flip sign between windows: aligned-only is +$103 recent vs −$113
  over the year. **Do not add regime or session filters.**
- V92's max-1-ATR extension cap pointed the wrong way (SNDK +$121 → −$21).
  Extended breakouts carry the tail.
- Not pyramiding on repeat signals is correct (add-on EV is about 0).
- Entry timing is clean: fills 8.7–21.6 s after the hour, and at most 27.7 s
  against the 30 s deadline.

### Exits

| Provider | Effective behavior | Assessment |
|---|---|---|
| D20/10 and band20 | R = structural stop (74–185 bps live). Ratchet after +0.5R when alignment ≤ −0.5. Floor at +0.5R once +2R. Break-even venue stop at entry +25 bps once the floor arms. Recipe channel exit. 24h timer. | Tail-preserving. The ratchet never fires on with-regime trades (0 of 2,108 armed rows had alignment ≤ −0.5). Between +0.5R and +2R only the initial stop protects. |
| BTC sweep | Fixed 60/60 target. v2 floor and break-even unreachable. | Upside capped at 1R. Low impact. |
| HYPE | 8h hold extendable to 24h while the regime supports. | Irrelevant while the route is dead. |
| ETH | 48h hold, 60 bps stop. | Irrelevant while the route is dead. |

- **Evidence quality of v2.** The composite reproduces to the cent, but it was
  chosen after about 125 variants were examined on the same data.
- **De-selection trap.** The floor component ranks 1st of 61 arms on the recent
  screen and 54th–60th on the one-year window.
- **The regime gate** is the small, broadly positive part.
- **The venue break-even after 2R** is the component that holds up best out of
  window.
- **The 09-24 SNDK swing** (+1.14R → −0.52R in 14 min around the US open, with
  alignment +0.33/+0.5) is the designed cost of catching the tail. Every tighter
  variant tested cut SNDK tail dollars. **Do not retune on it.**

## 7. Sizing: how much more aggression the evidence can carry

- **Where the book is today.**
  - With all 8 routes open, risk at the stops is about $90 (1.9% of equity). On
    the 5 routes that fire it is about $57 (1.2%).
  - Mean per-trade risk is 0.27% of equity.
- **Price of more aggression under zero edge** (day-block bootstrap, 90-day
  P(drawdown ≥ 20%)):

  | Risk per trade | P(drawdown ≥ 20%) |
  |---|---|
  | 0.27% (today) | 0.2% |
  | 0.5% | 12% |
  | 0.75% | 40% |
  | 1.0% | 65% |

- **Kelly** is 0 on the one-year and combined pools. It is 2.3% (adverse) to
  5.6% (measured) on the recent 8-asset pool, and higher only on the in-sample
  selected roster.
- **Rejected by the traps:**
  - Restoring SNDK to V90's $1,930, or a $45–52 budget. Ex-top-3 is −$190 adverse
    and −$30 measured. Part of SNDK's live tail is the outage artifact (+0.216R
    becomes +0.021R when capped at 24h). V90's SNDK winners were taken at $500, not
    $1,948.
  - 1/stop risk parity. Tight-stop trades (<80 bps) lose −0.28R.
  - Making the $25 bind on every route. BRENT and TSLA fail ex-top-3 at both costs,
    and year crypto loses more at every cost.
- **Supported:**
  - Calibrate the budget so its stated loss is the realized loss ($29 on the
    Donchian provider; only SNDK changes, about +16% notional).
  - Express the budget as a share of equity.
  - Move toward 0.5% of equity uniformly on the D20 routes, only as a
    pre-registered ladder rung earned by forward results.
- **Optional, and Albert's call:** a SNDK variance sleeve at 0.75% of equity
  (about $36). Label it a zero-Kelly bet and write the step-down rule first.

## 8. Technical and operational findings

1. **Degraded-blindness bound.** The bound is 240 polls × 123.5 s ≈ 8.2 h, not the
   documented 1 h (`multi_asset_live_runner.py:80`). An outage longer than that
   raises `CohortDegradedBlindnessError`, then up to 6 relaunches, then a
   restart-budget hold that launchd never clears.
2. **Restart time grows with ledger history.** Startup ≈ −2.4 + 1.39 × GB of
   ledger (n=33, residual sd 0.45). That was 14.1 min at V93 launch.
   - Ledgers are 11.8 GB and grow 0.45 GB/day, so restarts get 0.62 min/day
     slower. They pass the 30-min grace in about 25 days.
   - More than 99.9% of asset-ledger bytes are per-poll telemetry.
   - Each armed start writes a 1.2–1.28 GB bundle.
3. **Disk.** About 17 GiB free against the 10 GiB launch floor, which is also the
   only disk alert. 150 prestart bundles hold 64.1 GiB, of which 52.3 GiB predate
   09-09. The V93 go-live was already held once at 8.7 GiB.
4. **The documented rollback fails closed.** V93→V91 is refused with "previous
   profile id differs from approval" (reproduced offline). The refusal comes after
   the 1.2 GB bundle is written.
5. **The loader silently drops misspelled keys.** A typo in `adaptive_exit_policy`
   or `stop_risk_budget` turns off v2 and the budget on all five providers
   (reproduced), which puts SNDK back at $1,930.
6. **Venue metadata.** A max-leverage change on any single market turns every
   restart into a crash loop across all 8 routes (`hyperliquid_perp_reader.py:65-72`,
   exit 1 instead of a refusal).
7. **Break-even modify.** It has never run live, and 3 failed raise attempts produce
   no alert. The software +0.5R floor is not on the venue: the venue stop only rises
   to +25 bps, which leaves about 67.6 bps (about $7.5 on SNDK) exposed during an
   outage.
8. **Not audited deeply:**
   - HIP-3 deployer halts: there is no halted-market state in `src/hypervector/live`.
   - Earnings and event gaps through 24h holds.
   - Weekend oracle behavior.
   - Venue and custody concentration: about $4.6K idle on the venue.
   - Whether the VPN default route (`utun4`) caused the 09-24 outage.

## 9. Ranked actions

### A. Now: no live-identity change, no backend restart

1. **Off-host alerting.**
   - Set `HYPERVECTOR_ALERT_WEBHOOK_URL` (phone push) and `HYPERVECTOR_DEADMAN_URL`
     in the **watch** plist only, and reload only the watch agent.
   - Add a `backend_polls_degraded` problem to `scripts/cohort_supervisor_health.py`
     that fires after 2 or more consecutive degraded polls while positions are open.
   - Push only backend-critical problems. Keep roster and fee-probe flaps local.
   - Never print the URLs.
2. **Stop unattended reboots** (Albert's host setting).
   - Turn off automatic install of macOS and critical updates, keeping downloads on.
   - Patch by hand inside planned drain windows.
   - Write a one-page post-reboot resume runbook.
3. **Disk runway** (Albert's call).
   - Reclaim prestart bundles older than 09-09, keeping the rollback and approval
     chain.
   - Add a 14 GiB early-warning problem in the watch agent.
4. **Pre-author and dry-run the reverse approvals** (V93→V91 and V93→v2-off) so the
   rollback actually starts. Correct HANDOFF's rollback text and the "240 polls ≈ 1 h"
   claim.
5. **Forward-evidence tooling in `scripts/`** (read-only, no execution authority):
   - Breakout extension on every live D20 entry.
   - The floor-armed 24h-timer counterfactual.
   - 240- and 1,440-min post-exit marks.
   - Per-provider v2 deltas with ex-top-3.
   - Time-scaled buy-and-hold, at both cost models.

### B. Next planned config transition (batch into one drain, one fingerprint, one approval)

6. SPCX band20 → observe-only.
7. HYPE → observe-only. If it stays executable, set `margin_fraction` 0.013 and
   `max_notional_usd` 500 at 10x.
8. ETH → observe-only (optional).
9. Donchian `stop_risk_budget.maximum_loss_usd` 25 → 29. Only SNDK changes: the
   realized stop-out goes from about $21.8 to about $25, about +16% notional.
10. Before arming: clear every `*_overrides` table naming a demoted symbol, then run
    `scripts/cohort_runtime_validation_check.py --mode live` and a TUI render check.

### C. Next source transition (worktree, full tests, approval)

11. `StopRiskBudget.maximum_loss_fraction_of_equity`, evaluated at entry, to make
    risk compound. Price the entry bound from the measured p95 slip (about 13 bps)
    instead of the 20 bps IOC cap. Keep the 20 bps cost buffer.
12. Break-even raise to `max(entry ± 25 bps, entry ± 0.5R)`. Alert when a raise is
    exhausted.
13. Reject unknown keys in asset, provider and execution tables.
14. Restart-path engineering:
    - A wall-clock degraded bound.
    - A venue-reachability probe before writing a bundle or charging the restart
      budget.
    - Metadata mismatch treated as a start refusal.
    - Ledger rotation, with per-poll telemetry moved out of replay.
    - Incremental bundles.
15. **Weak-short rule** (new provider identity, e.g.
    `hourly_donchian_20_10_atr20_strong_short_v1`), applied at mechanism level on
    all D20 symbols:
    - Re-score it first under v2 and the budget at both costs, and write the pass
      bar down before running it.
    - The replay with V92 exits gave recent +$176.56 → +$535.44 and one-year
      −$1,183.93 → −$394.51.
    - On V93's four routes the gain is SNDK-concentrated (+$150 of +$177).
    - Caveat: the split was found after examining 5 split families.

### D. The aggression path: a pre-registered size ladder

16. **Rung 1** is 0.5% of equity at-stop risk, uniform across the D20 routes,
    implemented as `min(k × equity, 0.5% × equity / modeled stop loss)`. Never 1/stop.
    - **Advance condition:** the next 30 D20 closes after action 15 have mean R > 0
      and ex-top-3 ≥ 0 at measured cost, with timer exits capped at the configured
      hold.
    - **Step-down:** on −12% from the rung high, or mean R < 0 over any 50 trades.
    - **Book-level config assertion:** total at-stop risk ≤ 3% and total margin ≤ 25%
      of equity. This is a config validation, not a trade gate.
17. **Optional now:** a SNDK variance sleeve at 0.75% of equity (about $36), labelled
    a zero-Kelly bet in the approval, with the step-down rule written first.

## 10. Do not do

- Do not tighten the v2 constants after the 09-24 SNDK swing.
- Do not restore SNDK to $1,930 or a budget of $45–52 on an edge claim.
- Do not size by 1/stop, and do not make the $25 bind on every route.
- Do not size up SOL or TSLA.
- Do not raise leverage.
- Do not "fix" HYPE by cutting leverage at a fixed notional.
- Do not switch to cross margin.
- Do not pyramid on floor-armed winners. Over the year at adverse cost it is
  −$0.58 across 238 adds, with ex-top-3 −$184.60.
- Do not add regime-alignment, session or weekend entry filters (signs flip between
  windows).
- Do not cap breakout extension.
- Do not widen stops.
- Do not deploy a fixed longer hold (72h loses on the live-4 symbols).
- Do not move BTC, ETH or HYPE onto D20/10 (one-year: −$165, −$143, −$314 at
  measured cost).
- Do not re-propose refuted levers:
  - M15/M5 scalping
  - HIP-3 breadth expansion
  - unconditional ATR trailing
  - partial scale-outs
  - stale-peak timers
  - 100/25/50 locks
- Do not restart, re-arm or reload the **supervise** agent while positions are open.
  Only the watch agent is safe to reload live. Batch changes, because each restart
  costs about 15 min blind and 1.2 GB.
- Do not edit `src/hypervector` outside a planned transition, because it is hashed
  into the live identity.

## 11. Gaps

- No sealed holdout exists for any lever. HIP-3 names have about 62 days of
  history, and SOL is the only V93 D20 route inside the one-year window.
- The entry-side replays (weak shorts, extension) use V92 exits at a flat $500.
  They have not been re-scored under v2 and the budget.
- Albert has never stated a drawdown tolerance. The 0.5%, 0.75% and 1% levels and
  the P(drawdown ≥ 20%) thresholds are the reviewers' framing.
- These are unverified:
  - SNDK stop slippage at larger clips (n=5: median 9.3 bps, max 18.9).
  - Deployer-halt behavior.
  - The first live break-even modify.
  - The root causes of the 09-24 outage and of the earlier reboots.
- About 2.4 GiB/day of volume-wide disk burn is not attributed to anything.
